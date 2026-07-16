"""Class-taxonomy helpers shared by retrieval, catalog, and the API.

The class catalog is a two-level tree (parent category → subclass). Filtering by a
parent should include its subclasses, so a query scoped to ``financial`` also
returns invoices and receipts. `expand_class_slugs` resolves one slug to itself
plus its direct children (the tree is only two deep).
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Class


def slugify(name: str) -> str:
    """Derive a URL/prompt-safe slug from a class name (lowercase, `_`-joined)."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def get_or_create_class(
    db: Session,
    account_id: uuid.UUID,
    *,
    name: str,
    description: str | None = None,
    parent_id: uuid.UUID | None = None,
) -> Class:
    """Return the account's class with this name's slug, creating it if absent.

    Forgiving by design (used by the review flow's inline "create a class" path):
    an existing slug is reused rather than rejected. A `parent_id` that isn't a
    class in this account is ignored. Raises ``ValueError`` if the name yields an
    empty slug. The caller commits.
    """
    slug = slugify(name)
    if not slug:
        raise ValueError("Name must contain a letter or digit.")
    existing = db.scalar(
        select(Class).where(Class.account_id == account_id, Class.slug == slug)
    )
    if existing is not None:
        return existing
    if parent_id is not None:
        parent = db.scalar(
            select(Class).where(Class.account_id == account_id, Class.id == parent_id)
        )
        if parent is None:
            parent_id = None
    cls = Class(
        account_id=account_id,
        slug=slug,
        name=name.strip(),
        description=description,
        parent_id=parent_id,
        is_system=False,
    )
    db.add(cls)
    db.flush()
    return cls


def expand_class_slugs(db: Session, account_id: uuid.UUID, slug: str) -> list[str]:
    """Return `slug` plus the slugs of its child classes (account-scoped).

    An unknown slug (or a leaf with no children) yields just ``[slug]``, so callers
    can substitute the result into a `Class.slug.in_(...)` filter unconditionally.
    """
    cls = db.scalar(
        select(Class).where(Class.account_id == account_id, Class.slug == slug)
    )
    if cls is None:
        return [slug]
    children = db.scalars(
        select(Class.slug).where(
            Class.account_id == account_id, Class.parent_id == cls.id
        )
    ).all()
    return [slug, *children]
