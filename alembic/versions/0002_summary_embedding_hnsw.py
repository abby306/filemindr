"""summary_embedding HNSW index

Adds an HNSW (cosine) index on `documents.summary_embedding` to match the one
already on `document_facts.embedding`. This is the first stage of the two-stage
vector retrieval — `summary_embedding` picks candidate documents, then the
per-fact HNSW index ranks facts within them — so both stages are indexed.

Additive and idempotent (`IF NOT EXISTS`); the column already exists from 0001.

Revision ID: 0002_summary_embedding_hnsw
Revises: 0001_initial
Create Date: 2026-06-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002_summary_embedding_hnsw"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS documents_summary_embedding_hnsw "
        "ON documents USING hnsw (summary_embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS documents_summary_embedding_hnsw;")
