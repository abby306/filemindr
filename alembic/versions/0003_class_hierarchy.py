"""class hierarchy + document review_reason

Adds the two-level class taxonomy and the human-in-the-loop review signal:

  * `classes.parent_id` — self-referential FK so a class can nest under a parent
    category (leaves point to their parent; parents are NULL). `ON DELETE SET NULL`
    so deleting a parent orphans its children rather than cascading.
  * `documents.review_reason` — why a document landed in `needs_review`
    (`low_confidence` | `ambiguous` | `no_class`), so the UI can prompt the user
    to confirm or pick a class. NULL once resolved / never flagged.

Additive and idempotent (`IF NOT EXISTS` / guarded enum create).

Revision ID: 0003_class_hierarchy_review_reason
Revises: 0002_summary_embedding_hnsw
Create Date: 2026-07-01
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0003_class_hierarchy"
down_revision: Union[str, None] = "0002_summary_embedding_hnsw"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE classes ADD COLUMN IF NOT EXISTS parent_id uuid "
        "REFERENCES classes(id) ON DELETE SET NULL;"
    )
    op.execute("CREATE INDEX IF NOT EXISTS classes_parent_id_idx ON classes(parent_id);")
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE review_reason AS ENUM ('low_confidence', 'ambiguous', 'no_class'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$;"
    )
    op.execute(
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS review_reason review_reason;"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS review_reason;")
    op.execute("DROP TYPE IF EXISTS review_reason;")
    op.execute("DROP INDEX IF EXISTS classes_parent_id_idx;")
    op.execute("ALTER TABLE classes DROP COLUMN IF EXISTS parent_id;")
