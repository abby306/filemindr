"""Mandatory account scoping — the single tenancy boundary.

Every account-scoped query goes through an `AccountScope`, which auto-applies
`WHERE account_id = :active`. Querying a model that has no `account_id` raises,
so a cross-account (or unscoped) query is a programming error caught at the call
site rather than a silent data leak.

`get_current_account` is the FastAPI dependency that protected routes use; it
resolves the active account for the authenticated user and verifies membership.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.models import Account, AccountMember, User
from app.db.session import get_db


@dataclass(frozen=True)
class AccountScope:
    """A session bound to one active account.

    Use `scope.select(Model)` / `scope.query(Model)` for all reads and writes of
    account-scoped data; both refuse models that lack an `account_id` column.
    """

    db: Session
    user: User
    account: Account

    @property
    def account_id(self) -> uuid.UUID:
        return self.account.id

    def _require_scoped(self, model: type) -> None:
        if not hasattr(model, "account_id"):
            raise ValueError(
                f"{model.__name__} has no account_id; it cannot be account-scoped. "
                "Query it explicitly only when there is no tenancy boundary."
            )

    def select(self, model: type) -> Select:
        """A `SELECT` over `model` pre-filtered to the active account."""
        self._require_scoped(model)
        return select(model).where(model.account_id == self.account_id)

    def query(self, model: type):
        """Legacy-style `Query` over `model` pre-filtered to the active account."""
        self._require_scoped(model)
        return self.db.query(model).filter(model.account_id == self.account_id)

    def owns(self, obj: object) -> bool:
        """True if `obj` carries the active account_id."""
        return getattr(obj, "account_id", None) == self.account_id


def get_current_account(
    x_account_id: str | None = Header(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountScope:
    """Resolve the active `AccountScope` for the request.

    The account is chosen by the `X-Account-Id` header; if omitted and the user
    belongs to exactly one account, that account is used. Membership is always
    verified, so a user can never scope to an account they do not belong to.
    """
    memberships = db.scalars(
        select(AccountMember).where(AccountMember.user_id == user.id)
    ).all()
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "no_account", "message": "User belongs to no account."},
        )

    if x_account_id is not None:
        try:
            requested = uuid.UUID(x_account_id.strip())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "bad_account_id", "message": "X-Account-Id is not a valid UUID."},
            )
        if not any(m.account_id == requested for m in memberships):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "not_a_member", "message": "Not a member of the requested account."},
            )
        account_id = requested
    elif len(memberships) == 1:
        account_id = memberships[0].account_id
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "account_required",
                "message": "Multiple accounts; specify one via the X-Account-Id header.",
            },
        )

    account = db.get(Account, account_id)
    if account is None:  # membership referenced a deleted account — defensive
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "no_account", "message": "Active account not found."},
        )
    return AccountScope(db=db, user=user, account=account)
