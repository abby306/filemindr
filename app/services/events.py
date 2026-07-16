"""Append-only pipeline event logging.

Every stage of the document pipeline records a `processing_events` row so a
document's history is a SELECT, not a re-run. Events are always account-scoped.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.models import ProcessingEvent


def record_event(
    db: Session,
    *,
    account_id: uuid.UUID,
    document_id: uuid.UUID,
    stage: str,
    status: str,
    detail: dict | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
) -> ProcessingEvent:
    """Append one pipeline event. Caller controls the transaction/commit."""
    event = ProcessingEvent(
        account_id=account_id,
        document_id=document_id,
        stage=stage,
        status=status,
        detail=detail,
        error=error,
        duration_ms=duration_ms,
    )
    db.add(event)
    return event
