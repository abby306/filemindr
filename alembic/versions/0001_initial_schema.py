"""initial schema (vector 768)

Applies the canonical DDL from schema.sql at the repo root. Kept as raw SQL
because it uses pgvector, generated tsvector columns, and an HNSW index that are
clearest expressed directly. Later migrations can autogenerate once ORM models exist.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-26
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "schema.sql"


def _statements(sql: str) -> list[str]:
    """Split a SQL script into statements, respecting $$ dollar-quoted bodies."""
    # drop full-line comments
    sql = "\n".join(ln for ln in sql.splitlines() if not ln.strip().startswith("--"))
    statements: list[str] = []
    buf: list[str] = []
    in_dollar = False
    i = 0
    while i < len(sql):
        if sql[i : i + 2] == "$$":
            in_dollar = not in_dollar
            buf.append("$$")
            i += 2
            continue
        ch = sql[i]
        if ch == ";" and not in_dollar:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def upgrade() -> None:
    sql = SCHEMA_SQL.read_text()
    for stmt in _statements(sql):
        op.execute(stmt)


def downgrade() -> None:
    # Baseline migration: tear the schema back down to empty.
    op.execute("DROP SCHEMA public CASCADE;")
    op.execute("CREATE SCHEMA public;")
