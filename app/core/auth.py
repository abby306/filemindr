"""Minimal request authentication.

This is deliberately small but real enough to gate routes: the bearer token is
the user's UUID (a dev-grade API token), resolved against `users` and required
to be active. A production auth mechanism (sessions / JWT / OAuth) slots in here
later — `get_current_user` is the single seam every protected route depends on.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail={"code": "unauthenticated", "message": "Valid bearer token required."},
    headers={"WWW-Authenticate": "Bearer"},
)


def _parse_bearer(authorization: str | None) -> uuid.UUID:
    """Extract a user UUID from an `Authorization: Bearer <uuid>` header."""
    if not authorization:
        raise _UNAUTHENTICATED
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _UNAUTHENTICATED
    try:
        return uuid.UUID(token.strip())
    except ValueError:
        raise _UNAUTHENTICATED


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Resolve and return the authenticated, active user, or raise 401."""
    user_id = _parse_bearer(authorization)
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise _UNAUTHENTICATED
    return user
