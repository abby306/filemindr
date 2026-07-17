"""Database engine and session management.

A single SQLAlchemy `Engine` (psycopg 3 driver) backs a `sessionmaker`. Request
handlers depend on `get_db`, which yields a session and always closes it.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# `pool_pre_ping` recycles connections silently dropped by the server, which the
# native Postgres setup will do across idle periods. Overflow headroom covers
# request bursts (an upload storm) on top of the bounded pipeline workers —
# local Postgres allows 100 connections, so 5+25 stays comfortable.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    max_overflow=25,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a session and guarantee it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
