"""document_classes.is_primary — one primary class per document

A document can be labelled with several classes (the extractor often finds a
document plausibly fits more than one category). For the archive *browse* that
read as duplication — a document appeared under every folder it was labelled
with. `is_primary` marks the single class that owns a document's folder
placement (its highest-confidence label); the rest remain as secondary labels
for display, but no longer place the document in multiple folders.

  * `document_classes.is_primary boolean not null default false`.
  * Backfill: the top row per document (max confidence, then earliest) becomes
    primary — so existing corpora get a clean single-folder placement with no
    re-extraction.
  * Partial unique index enforces at most one primary per document.

Additive and idempotent (`IF NOT EXISTS` / guarded).

Revision ID: 0004_doc_class_primary
Revises: 0003_class_hierarchy
Create Date: 2026-07-02
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0004_doc_class_primary"
down_revision: Union[str, None] = "0003_class_hierarchy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE document_classes "
        "ADD COLUMN IF NOT EXISTS is_primary boolean NOT NULL DEFAULT false;"
    )
    # Backfill: pick one primary per document — highest confidence, ties broken
    # by earliest link then id (stable, deterministic).
    op.execute(
        """
        UPDATE document_classes dc SET is_primary = true
        WHERE dc.id IN (
            SELECT DISTINCT ON (document_id) id
            FROM document_classes
            ORDER BY document_id, confidence DESC NULLS LAST, created_at ASC, id ASC
        );
        """
    )
    # At most one primary per document.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS document_classes_one_primary_idx "
        "ON document_classes (document_id) WHERE is_primary;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS document_classes_one_primary_idx;")
    op.execute("ALTER TABLE document_classes DROP COLUMN IF EXISTS is_primary;")
