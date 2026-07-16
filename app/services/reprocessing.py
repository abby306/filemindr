"""Re-drive documents stuck in a non-terminal or failed state.

`BackgroundTasks` don't survive a process restart, so a document can be left
parked at any pipeline stage; a `failed` doc has no automatic retry. This module
re-invokes the existing (already idempotent) background entry points from the
correct point for each status, so a sweep brings everything to a terminal state.

Routing:
  * `received` / `failed`        → `ocr.run_ocr`         (re-OCR; chains forward)
  * `ocr_done`                   → `extraction.run_extraction` (chains embedding)
  * `extracted` / `needs_review` → `embeddings.run_embedding`
  * `indexed`                    → terminal, skipped

A `failed` document is re-driven from OCR because the stage at which it failed
isn't persisted; every entry point is idempotent, so a full re-run is safe.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable

from sqlalchemy import select

from app.db.models import Document
from app.db.session import SessionLocal
from app.services import embeddings, extraction, ocr

# `indexed` is terminal. `needs_review` is excluded from the default sweep — it
# is a human-review state whose embedding has already run (it is not "stuck") —
# but it can still be re-driven explicitly or via an override `statuses` set.
_TERMINAL = frozenset({"indexed"})
_DEFAULT_SWEEP = frozenset({"received", "ocr_done", "extracted", "failed"})


def _entry_for_status(status: str) -> Callable[[uuid.UUID, uuid.UUID], None] | None:
    """The background entry point that advances a doc at `status` (or None)."""
    if status in ("received", "failed"):
        return ocr.run_ocr
    if status == "ocr_done":
        return extraction.run_extraction
    if status in ("extracted", "needs_review"):
        return embeddings.run_embedding
    return None


def reprocess_document(document_id: uuid.UUID, account_id: uuid.UUID) -> str | None:
    """Re-drive one document from the correct point for its current status.

    Returns the name of the entry point invoked, or None if the document is
    missing, cross-account, or already terminal.
    """
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None or document.account_id != account_id:
            return None
        status = document.status
        entry = _entry_for_status(status)
        if entry is None:
            return None
        if status == "failed":  # start the re-run from a clean slate
            document.error = None
            db.commit()

    entry(document_id, account_id)  # opens its own session; chains forward
    return entry.__name__


def reprocess_stuck(
    *,
    account_id: uuid.UUID | None = None,
    statuses: Iterable[str] | None = None,
) -> dict[str, int]:
    """Sweep documents in non-terminal/failed states and re-drive each.

    Scans `statuses` (default: received/ocr_done/extracted/failed), optionally
    limited to one account, and re-drives each in creation order. Returns a count
    of documents per entry point used.
    """
    wanted = frozenset(statuses) if statuses is not None else _DEFAULT_SWEEP
    with SessionLocal() as db:
        query = (
            select(Document.id, Document.account_id)
            .where(Document.status.in_(wanted))
            .order_by(Document.created_at)
        )
        if account_id is not None:
            query = query.where(Document.account_id == account_id)
        rows = db.execute(query).all()

    summary: dict[str, int] = {}
    for doc_id, doc_account_id in rows:
        used = reprocess_document(doc_id, doc_account_id) or "skipped"
        summary[used] = summary.get(used, 0) + 1
    return summary
