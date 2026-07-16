"""Database engine connectivity and the get_db dependency."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import engine, get_db


def test_engine_connects() -> None:
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_pgvector_extension_present() -> None:
    with engine.connect() as conn:
        version = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
    assert version is not None


def test_get_db_yields_session() -> None:
    gen = get_db()
    session = next(gen)
    try:
        assert isinstance(session, Session)
        assert session.execute(text("SELECT 1")).scalar() == 1
    finally:
        gen.close()
