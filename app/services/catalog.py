"""Document catalog — corpus awareness the agent *queries* (not a context dump).

The agent needs to resolve human references ("the NDA", "that March invoice", "my
energy docs", "the contract I uploaded last week") to real documents. Rather than
stuffing every summary into the prompt (which doesn't scale past a few dozen docs),
this exposes the catalog as something the agent navigates:

  * `corpus_overview` — a bounded orientation at chat start (counts by class, date
    range, recent titles; full list only when the corpus is small).
  * `find_documents` — filter by class / name / upload window / semantic "about",
    returning compact doc cards.

Both are `account_id`-scoped and consider only **searchable** documents (indexed or
needs_review). All reference types map onto existing columns — no schema changes.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Class, Document, DocumentClass
from app.services.taxonomy import expand_class_slugs
from app.services.embeddings import embed_query

# Documents that have been embedded are searchable (indexed or flagged-for-review).
_SEARCHABLE = ("indexed", "needs_review")

# Inline the whole catalog into the prompt only below this size; above it, the
# agent orients from stats + `find_documents`.
SMALL_CORPUS = 30


@dataclass
class CatalogDoc:
    document_id: uuid.UUID
    title: str | None
    class_slugs: list[str] = field(default_factory=list)
    created_at: dt.datetime | None = None
    summary: str | None = None


def _attach_classes(db: Session, account_id: uuid.UUID, docs: list[CatalogDoc]) -> None:
    """Populate `class_slugs` for the given docs in one query (no N+1)."""
    if not docs:
        return
    ids = [d.document_id for d in docs]
    rows = db.execute(
        select(DocumentClass.document_id, Class.slug)
        .join(Class, Class.id == DocumentClass.class_id)
        .where(DocumentClass.account_id == account_id, DocumentClass.document_id.in_(ids))
    ).all()
    by_doc: dict[uuid.UUID, list[str]] = {}
    for doc_id, slug in rows:
        by_doc.setdefault(doc_id, []).append(slug)
    for d in docs:
        d.class_slugs = by_doc.get(d.document_id, [])


def find_documents(
    db: Session,
    account_id: uuid.UUID,
    *,
    class_slug: str | None = None,
    name: str | None = None,
    about: str | None = None,
    uploaded_after: dt.date | None = None,
    uploaded_before: dt.date | None = None,
    limit: int = 10,
) -> list[CatalogDoc]:
    """Find documents matching any combination of filters (account-scoped).

    `about` ranks by summary-embedding similarity; otherwise results are newest
    first. `name` matches the title or original filename.
    """
    stmt = select(Document).where(
        Document.account_id == account_id, Document.status.in_(_SEARCHABLE)
    )
    if name:
        like = f"%{name}%"
        stmt = stmt.where(Document.title.ilike(like) | Document.original_filename.ilike(like))
    if uploaded_after:
        stmt = stmt.where(Document.created_at >= uploaded_after)
    if uploaded_before:
        stmt = stmt.where(Document.created_at < uploaded_before + dt.timedelta(days=1))
    if class_slug:
        slugs = expand_class_slugs(db, account_id, class_slug)
        stmt = stmt.where(
            Document.id.in_(
                select(DocumentClass.document_id)
                .join(Class, Class.id == DocumentClass.class_id)
                .where(DocumentClass.account_id == account_id, Class.slug.in_(slugs))
            )
        )
    if about:
        qvec = embed_query(about)
        stmt = stmt.where(Document.summary_embedding.is_not(None)).order_by(
            Document.summary_embedding.cosine_distance(qvec)
        )
    else:
        stmt = stmt.order_by(Document.created_at.desc())

    docs = [
        CatalogDoc(
            document_id=d.id,
            title=d.title or d.original_filename,
            created_at=d.created_at,
            summary=d.summary,
        )
        for d in db.scalars(stmt.limit(limit)).all()
    ]
    _attach_classes(db, account_id, docs)
    return docs


def corpus_overview(db: Session, account_id: uuid.UUID) -> dict:
    """A bounded orientation of the account's corpus for the start of a chat.

    Always returns counts, per-class tallies and the upload date range. When the
    corpus is small (`<= SMALL_CORPUS`) it also inlines the full document list so
    the agent can reference any doc directly; otherwise it returns the most recent
    few and relies on `find_documents` for the rest.
    """
    total = db.scalar(
        select(func.count()).select_from(Document)
        .where(Document.account_id == account_id, Document.status.in_(_SEARCHABLE))
    ) or 0

    by_class = dict(db.execute(
        select(Class.slug, func.count(DocumentClass.document_id))
        .join(Class, Class.id == DocumentClass.class_id)
        .join(Document, Document.id == DocumentClass.document_id)
        .where(DocumentClass.account_id == account_id, Document.status.in_(_SEARCHABLE))
        .group_by(Class.slug)
        .order_by(func.count(DocumentClass.document_id).desc())
    ).all())

    span = db.execute(
        select(func.min(Document.created_at), func.max(Document.created_at))
        .where(Document.account_id == account_id, Document.status.in_(_SEARCHABLE))
    ).one()

    small = total <= SMALL_CORPUS
    docs = find_documents(db, account_id, limit=(SMALL_CORPUS if small else 5))
    return {
        "total_documents": total,
        "by_class": by_class,
        "uploaded_from": span[0].date().isoformat() if span[0] else None,
        "uploaded_to": span[1].date().isoformat() if span[1] else None,
        "complete_listing": small,  # True ⇒ `documents` below is the whole corpus
        "documents": docs,
    }
