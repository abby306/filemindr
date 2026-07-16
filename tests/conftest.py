"""Shared test fixtures.

Tests run against the live local Postgres (the same DB the app uses). Each
fixture cleans up after itself so the suite is repeatable and never leaves stray
rows. The `db` fixture rolls back, so unit tests can create-and-inspect without
committing; route tests that need persistence use `seeded_account`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.db.models import Account, AccountMember, User
from app.db.session import SessionLocal


@pytest.fixture
def db() -> Iterator[Session]:
    """A session whose work is rolled back at the end of the test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def seeded_account() -> Iterator[dict]:
    """Persist a throwaway user + personal/company accounts; tidy up after.

    Yields the created ids so route tests can authenticate as the user and
    target either account. Deleting the accounts cascades to memberships.
    """
    session = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = User(email=f"test-{suffix}@example.com", name="Test User")
    personal = Account(type="personal", name=f"Personal {suffix}")
    company = Account(type="company", name=f"Company {suffix}")
    session.add_all([user, personal, company])
    session.flush()
    session.add_all(
        [
            AccountMember(account_id=personal.id, user_id=user.id, role="owner"),
            AccountMember(account_id=company.id, user_id=user.id, role="member"),
        ]
    )
    session.commit()
    ids = {
        "user_id": user.id,
        "personal_id": personal.id,
        "company_id": company.id,
    }
    try:
        yield ids
    finally:
        session.delete(session.get(Account, personal.id))
        session.delete(session.get(Account, company.id))
        session.delete(session.get(User, user.id))
        session.commit()
        session.close()
