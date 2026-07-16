"""Billing provider seam — a Stripe-shaped mock until real credentials arrive.

The flow deliberately mirrors Stripe Checkout so swapping the provider is a
drop-in change, not a redesign:

1. ``create_checkout_session`` — *mock:* mints an opaque session id and points
   ``checkout_url`` at the web app's hosted-checkout stand-in page.
   *Stripe swap:* call ``stripe.checkout.Session.create`` with
   ``metadata={"account_id", "plan_slug"}`` and return Stripe's hosted URL.
2. The user "pays" on the checkout page.
3. ``parse_session`` + ``activate_plan`` — *mock:* the page confirms via
   ``POST /billing/checkout/complete``. *Stripe swap:* a
   ``checkout.session.completed`` webhook (signature-verified) reads the
   metadata back and calls the **same** ``activate_plan``.

``activate_plan`` is provider-agnostic on purpose: it swaps the active
subscription and writes the invoice regardless of who collected the money.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Invoice, Plan, Subscription
from app.services.usage import current_period

_SESSION_PREFIX = "cs_mock"
_PERIOD_DAYS = 30


class InvalidSessionError(Exception):
    """The checkout session id is malformed or references an unknown plan."""


def create_checkout_session(db: Session, account_id: uuid.UUID, plan: Plan) -> dict:
    """Start a checkout for a paid plan; returns ``{session_id, checkout_url}``.

    Mock provider: the session id encodes the plan (the account comes from auth
    on completion — with Stripe both ride the session's ``metadata``), and the
    URL is the web app's checkout stand-in page, relative so it works behind
    the dev rewrite and in prod alike.
    """
    session_id = f"{_SESSION_PREFIX}_{plan.slug}_{uuid.uuid4().hex}"
    return {
        "session_id": session_id,
        "checkout_url": f"/billing/checkout?session_id={session_id}&plan={plan.slug}",
    }


def parse_session(db: Session, session_id: str) -> Plan:
    """Resolve a mock session id back to its plan (raises `InvalidSessionError`)."""
    parts = session_id.split("_")
    if len(parts) != 4 or "_".join(parts[:2]) != _SESSION_PREFIX:
        raise InvalidSessionError(session_id)
    plan = db.get(Plan, parts[2])
    if plan is None or plan.price_cents == 0:
        raise InvalidSessionError(session_id)
    return plan


def get_active_subscription(db: Session, account_id: uuid.UUID) -> Subscription | None:
    return db.scalar(
        select(Subscription).where(
            Subscription.account_id == account_id, Subscription.status == "active"
        )
    )


def activate_plan(
    db: Session, account_id: uuid.UUID, plan: Plan, *, external_ref: str | None = None
) -> Subscription:
    """Make `plan` the account's active subscription and record the invoice.

    Provider-agnostic: called by the mock complete endpoint today and by the
    Stripe webhook later. Cancels any previous active subscription first (the
    partial unique index allows one active row per account). Caller commits.
    """
    now = dt.datetime.now(dt.timezone.utc)
    previous = get_active_subscription(db, account_id)
    if previous is not None:
        previous.status = "canceled"
        db.flush()  # release the one-active-per-account unique index slot
    subscription = Subscription(
        account_id=account_id,
        plan_slug=plan.slug,
        status="active",
        period_start=now,
        period_end=now + dt.timedelta(days=_PERIOD_DAYS),
        external_ref=external_ref,
    )
    db.add(subscription)
    db.add(
        Invoice(
            account_id=account_id,
            amount_cents=plan.price_cents,
            currency=plan.currency,
            status="paid",
            period=current_period(now),
            external_ref=external_ref,
        )
    )
    db.flush()
    return subscription
