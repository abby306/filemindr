"""Billing endpoints — plans, subscription + usage, checkout, invoices (Phase 7).

Thin wrappers over `services/billing` (the Stripe-shaped provider seam) and
`services/usage` (so the meters shown here are the same numbers quota
enforcement reads — they can never disagree). `POST /checkout/complete` is the
mock stand-in for the provider webhook; see `services/billing` for the swap.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.schemas import (
    CheckoutCompleteIn,
    CheckoutIn,
    CheckoutOut,
    InvoiceListOut,
    InvoiceOut,
    PlanOut,
    SubscriptionOut,
    SubscriptionUsageOut,
)
from app.core.scoping import AccountScope, get_current_account
from app.db.models import Invoice, Plan
from app.services import billing, usage

router = APIRouter(prefix="/api/v1", tags=["billing"])


@router.get("/billing/plans", response_model=list[PlanOut])
def list_plans(scope: AccountScope = Depends(get_current_account)) -> list[PlanOut]:
    """The plan catalog (global product configuration), cheapest first."""
    plans = scope.db.scalars(select(Plan).order_by(Plan.price_cents)).all()
    return [PlanOut.model_validate(p) for p in plans]


def _subscription_out(scope: AccountScope) -> SubscriptionOut:
    quota = usage.quota_status(scope.db, scope.account_id)
    active = billing.get_active_subscription(scope.db, scope.account_id)
    return SubscriptionOut(
        plan=PlanOut.model_validate(quota.plan),
        status=active.status if active else "active",  # implicit free is active
        period_end=active.period_end if active else None,
        usage=SubscriptionUsageOut(
            documents=quota.documents,
            queries=quota.queries_this_month,
            storage_bytes=quota.storage_bytes,
        ),
        limits=quota.limits,
    )


@router.get("/billing/subscription", response_model=SubscriptionOut)
def get_subscription(scope: AccountScope = Depends(get_current_account)) -> SubscriptionOut:
    """Current plan + usage against its limits (no subscription row = free plan)."""
    return _subscription_out(scope)


@router.post("/billing/checkout", response_model=CheckoutOut)
def create_checkout(
    body: CheckoutIn,
    scope: AccountScope = Depends(get_current_account),
) -> CheckoutOut:
    """Start a checkout for a paid plan; the client navigates to `checkout_url`."""
    plan = scope.db.get(Plan, body.plan_slug)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "unknown_plan", "message": f"No plan '{body.plan_slug}'."},
        )
    if plan.price_cents == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "free_plan_checkout",
                "message": "The free plan needs no checkout.",
            },
        )
    session = billing.create_checkout_session(scope.db, scope.account_id, plan)
    return CheckoutOut(**session)


@router.post("/billing/checkout/complete", response_model=SubscriptionOut)
def complete_checkout(
    body: CheckoutCompleteIn,
    scope: AccountScope = Depends(get_current_account),
) -> SubscriptionOut:
    """Confirm a mock checkout and activate the plan.

    Stand-in for the payment provider's webhook: with real Stripe this handler
    is replaced by a signature-verified `POST /billing/webhook` that calls the
    same `billing.activate_plan`.
    """
    try:
        plan = billing.parse_session(scope.db, body.session_id)
    except billing.InvalidSessionError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_session", "message": "Unknown checkout session."},
        )
    billing.activate_plan(scope.db, scope.account_id, plan, external_ref=body.session_id)
    scope.db.commit()
    return _subscription_out(scope)


@router.get("/billing/invoices", response_model=InvoiceListOut)
def list_invoices(scope: AccountScope = Depends(get_current_account)) -> InvoiceListOut:
    """The account's invoices, newest first."""
    invoices = scope.db.scalars(
        scope.select(Invoice).order_by(Invoice.created_at.desc())
    ).all()
    return InvoiceListOut(items=[InvoiceOut.model_validate(i) for i in invoices])
