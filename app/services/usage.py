"""Usage metering and plan-quota enforcement (Phase 7).

Two halves, kept together because they must agree:

- **Metering** (`record_usage`): appends an immutable `usage_events` row and
  upserts the account's monthly `usage_counters` rollup in the caller's
  transaction, so a billable action and its metering commit (or roll back)
  atomically. Called from the write paths — document upload and message
  creation.
- **Quota** (`check_quota` / `quota_status`): resolves the account's plan (its
  active subscription's, or the free plan when none) and compares usage to the
  plan's `limits` jsonb. Document and storage caps are **account totals** read
  live from `documents` (the source of truth); `queries_per_month` reads the
  current calendar-month counter. A `null` limit means unlimited.

The API layer converts `QuotaExceededError` into the contract's 402 with an
upgrade hint; `quota_status` also feeds `GET /billing/subscription`, so the
meters users see and the limits we enforce always come from the same numbers.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, Plan, Subscription, UsageCounter, UsageEvent

FREE_PLAN_SLUG = "free"

# usage_events.type values written by the app (analytics groups on these).
EVENT_DOCUMENT_UPLOADED = "document_uploaded"
EVENT_QUERY_ASKED = "query_asked"

_BYTES_PER_GB = 1024**3


class QuotaExceededError(Exception):
    """A write would exceed the account's plan limit.

    Carries everything the API layer needs to build the 402 payload: which
    limit tripped, the numbers, and the plan to upgrade from.
    """

    def __init__(self, *, kind: str, limit: int, current: int, plan: Plan) -> None:
        self.kind = kind
        self.limit = limit
        self.current = current
        self.plan = plan
        super().__init__(f"{kind} quota exceeded: {current}/{limit} on plan '{plan.slug}'")


@dataclass(frozen=True)
class QuotaStatus:
    """An account's plan, current usage, and limits — one consistent snapshot."""

    plan: Plan
    documents: int
    storage_bytes: int
    queries_this_month: int

    @property
    def limits(self) -> dict:
        return self.plan.limits or {}


def current_period(now: dt.datetime | None = None) -> str:
    """The `usage_counters.period` key for a moment in time (UTC calendar month)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def record_usage(
    db: Session,
    account_id: uuid.UUID,
    *,
    type: str,
    user_id: uuid.UUID | None = None,
    meta: dict | None = None,
    documents: int = 0,
    queries: int = 0,
    storage_bytes: int = 0,
) -> None:
    """Meter one billable action: append a `usage_events` row + bump the counters.

    Runs in the caller's transaction (no commit here) so metering is atomic with
    the action it measures. The counter upsert is `ON CONFLICT` so concurrent
    writers increment rather than race.
    """
    db.add(UsageEvent(account_id=account_id, user_id=user_id, type=type, meta=meta))
    stmt = pg_insert(UsageCounter).values(
        account_id=account_id,
        period=current_period(),
        documents=documents,
        queries=queries,
        storage_bytes=storage_bytes,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[UsageCounter.account_id, UsageCounter.period],
        set_={
            "documents": UsageCounter.documents + documents,
            "queries": UsageCounter.queries + queries,
            "storage_bytes": UsageCounter.storage_bytes + storage_bytes,
            "updated_at": func.now(),
        },
    )
    db.execute(stmt)


def get_plan(db: Session, account_id: uuid.UUID) -> Plan:
    """The account's effective plan: its active subscription's, else free.

    `plans` is global product configuration (no `account_id`), so this is the
    one deliberate read outside `AccountScope`; the subscription lookup itself
    is account-filtered.
    """
    plan = db.scalar(
        select(Plan)
        .join(Subscription, Subscription.plan_slug == Plan.slug)
        .where(Subscription.account_id == account_id, Subscription.status == "active")
    )
    if plan is not None:
        return plan
    free = db.get(Plan, FREE_PLAN_SLUG)
    if free is None:  # seed missing — misconfiguration, not a user error
        raise RuntimeError("plans table is not seeded (missing 'free' plan)")
    return free


def quota_status(db: Session, account_id: uuid.UUID) -> QuotaStatus:
    """One consistent snapshot of plan + usage, shared by enforcement and billing.

    Document/storage usage comes from the `documents` table (account totals —
    deleting a document frees quota); queries from this month's counter.
    """
    doc_count, byte_sum = db.execute(
        select(func.count(Document.id), func.coalesce(func.sum(Document.byte_size), 0)).where(
            Document.account_id == account_id
        )
    ).one()
    queries = (
        db.scalar(
            select(UsageCounter.queries).where(
                UsageCounter.account_id == account_id,
                UsageCounter.period == current_period(),
            )
        )
        or 0
    )
    return QuotaStatus(
        plan=get_plan(db, account_id),
        documents=doc_count,
        storage_bytes=int(byte_sum),
        queries_this_month=queries,
    )


def _quotas_enabled() -> bool:
    """Whether plan limits are enforced (`ENFORCE_QUOTAS`). Metering always runs;
    this only gates the 402s — self-hosted installs default to unlimited."""
    return get_settings().enforce_quotas


def check_document_quota(db: Session, account_id: uuid.UUID, *, incoming_bytes: int = 0) -> None:
    """Raise `QuotaExceededError` if adding one document (of `incoming_bytes`)
    would exceed the plan's document-count or storage cap."""
    if not _quotas_enabled():
        return
    status = quota_status(db, account_id)
    doc_limit = status.limits.get("documents")
    if doc_limit is not None and status.documents >= doc_limit:
        raise QuotaExceededError(
            kind="documents", limit=doc_limit, current=status.documents, plan=status.plan
        )
    storage_gb = status.limits.get("storage_gb")
    if storage_gb is not None and status.storage_bytes + incoming_bytes > storage_gb * _BYTES_PER_GB:
        raise QuotaExceededError(
            kind="storage",
            limit=storage_gb * _BYTES_PER_GB,
            current=status.storage_bytes,
            plan=status.plan,
        )


def check_query_quota(db: Session, account_id: uuid.UUID) -> None:
    """Raise `QuotaExceededError` if the account has used this month's queries."""
    if not _quotas_enabled():
        return
    status = quota_status(db, account_id)
    limit = status.limits.get("queries_per_month")
    if limit is not None and status.queries_this_month >= limit:
        raise QuotaExceededError(
            kind="queries", limit=limit, current=status.queries_this_month, plan=status.plan
        )


def quota_http_detail(exc: QuotaExceededError) -> dict:
    """The 402 error payload: contract `{code, message}` plus structured extras
    so clients can render meters and the upgrade hint without parsing prose."""
    nouns = {
        "documents": "document limit",
        "storage": "storage limit",
        "queries": "monthly query limit",
    }
    return {
        "code": "quota_exceeded",
        "message": (
            f"Your {exc.plan.name} plan's {nouns.get(exc.kind, exc.kind)} has been reached. "
            "Upgrade your plan to continue."
        ),
        "kind": exc.kind,
        "limit": exc.limit,
        "current": exc.current,
        "plan": exc.plan.slug,
        "upgrade_hint": "/billing",
    }
