"""The account-scoping boundary actually isolates accounts."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.scoping import AccountScope
from app.db.models import Account, Document, User


def _make_document(db: Session, account: Account, name: str) -> Document:
    doc = Document(
        account_id=account.id,
        source="web_upload",
        original_filename=name,
        file_hash=f"hash-{name}",
        storage_path=f"/storage/{name}",
    )
    db.add(doc)
    db.flush()
    return doc


@pytest.fixture
def two_accounts(db: Session):
    """Two accounts, each owning one document; rolled back by the `db` fixture."""
    user = User(email="scope-test@example.com", name="Scope")
    acct_a = Account(type="personal", name="A")
    acct_b = Account(type="company", name="B")
    db.add_all([user, acct_a, acct_b])
    db.flush()
    doc_a = _make_document(db, acct_a, "a.pdf")
    doc_b = _make_document(db, acct_b, "b.pdf")
    return {"user": user, "a": acct_a, "b": acct_b, "doc_a": doc_a, "doc_b": doc_b}


def test_scope_only_sees_own_documents(db: Session, two_accounts) -> None:
    scope = AccountScope(db=db, user=two_accounts["user"], account=two_accounts["a"])
    docs = db.scalars(scope.select(Document)).all()
    ids = {d.id for d in docs}
    assert two_accounts["doc_a"].id in ids
    assert two_accounts["doc_b"].id not in ids


def test_query_helper_is_also_scoped(db: Session, two_accounts) -> None:
    scope = AccountScope(db=db, user=two_accounts["user"], account=two_accounts["b"])
    docs = scope.query(Document).all()
    assert [d.id for d in docs] == [two_accounts["doc_b"].id]


def test_owns_reflects_active_account(db: Session, two_accounts) -> None:
    scope = AccountScope(db=db, user=two_accounts["user"], account=two_accounts["a"])
    assert scope.owns(two_accounts["doc_a"]) is True
    assert scope.owns(two_accounts["doc_b"]) is False


def test_unscoped_model_is_rejected(db: Session, two_accounts) -> None:
    scope = AccountScope(db=db, user=two_accounts["user"], account=two_accounts["a"])
    # User has no account_id — scoping it is a programming error, not a silent leak.
    with pytest.raises(ValueError, match="account_id"):
        scope.select(User)
    with pytest.raises(ValueError, match="account_id"):
        scope.query(User)
