"""Class-catalog endpoints — list, create, and delete document classes.

The class catalog is what extraction classifies against (each class's `description`
is the signal the model uses). System classes ship seeded and are immutable; users
add custom classes per account. A new class is picked up by the *next* extraction —
existing documents are not retroactively re-classified.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select

from app.api.schemas import ClassCreate, ClassOut, ClassRename
from app.core.scoping import AccountScope, get_current_account
from app.db.models import Class, DocumentClass
from app.services.taxonomy import slugify as _slugify

router = APIRouter(prefix="/api/v1", tags=["classes"])


def _document_counts(scope: AccountScope) -> dict[uuid.UUID, int]:
    """Primary-class document count per class for the active account.

    Counts only each document's *primary* class so the folder count matches what
    the archive shows (one document → one folder), rather than double-counting
    documents that also carry secondary labels.
    """
    rows = scope.db.execute(
        select(DocumentClass.class_id, func.count(func.distinct(DocumentClass.document_id)))
        .where(
            DocumentClass.account_id == scope.account_id,
            DocumentClass.is_primary,
        )
        .group_by(DocumentClass.class_id)
    ).all()
    return {class_id: n for class_id, n in rows}


@router.get("/classes", response_model=list[ClassOut])
def list_classes(scope: AccountScope = Depends(get_current_account)) -> list[ClassOut]:
    """List the account's classes (system first), each with its document count.

    Each class carries its `parent_id`/`parent_slug` so the client can render the
    two-level taxonomy tree.
    """
    counts = _document_counts(scope)
    classes = scope.db.scalars(
        scope.select(Class).order_by(Class.is_system.desc(), Class.name.asc())
    ).all()
    slug_by_id = {c.id: c.slug for c in classes}
    return [
        ClassOut(
            id=c.id, slug=c.slug, name=c.name, description=c.description,
            parent_id=c.parent_id,
            parent_slug=slug_by_id.get(c.parent_id) if c.parent_id else None,
            is_system=c.is_system, document_count=counts.get(c.id, 0),
        )
        for c in classes
    ]


@router.post("/classes", response_model=ClassOut, status_code=status.HTTP_201_CREATED)
def create_class(
    body: ClassCreate, scope: AccountScope = Depends(get_current_account)
) -> ClassOut:
    """Create a custom class for the active account.

    Slug is derived from the name; a good `description` drives classification quality.
    409 if the slug already exists (including collisions with a system class).
    """
    slug = _slugify(body.name)
    if not slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_name", "message": "Name must contain a letter or digit."},
        )
    if scope.db.scalar(scope.select(Class).where(Class.slug == slug)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "class_exists", "message": f"A class with slug '{slug}' already exists."},
        )
    parent_slug: str | None = None
    if body.parent_id is not None:
        parent = scope.db.scalar(scope.select(Class).where(Class.id == body.parent_id))
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "bad_parent", "message": "Parent class not found in this account."},
            )
        parent_slug = parent.slug
    cls = Class(
        account_id=scope.account_id, slug=slug, name=body.name.strip(),
        description=body.description, parent_id=body.parent_id, is_system=False,
    )
    scope.db.add(cls)
    scope.db.commit()
    scope.db.refresh(cls)
    return ClassOut(
        id=cls.id, slug=cls.slug, name=cls.name, description=cls.description,
        parent_id=cls.parent_id, parent_slug=parent_slug,
        is_system=cls.is_system, document_count=0,
    )


@router.patch("/classes/{class_id}", response_model=ClassOut)
def rename_class(
    class_id: uuid.UUID,
    body: ClassRename,
    scope: AccountScope = Depends(get_current_account),
) -> ClassOut:
    """Rename a custom folder (its `slug` stays stable so links/filters don't break).

    404 if the class isn't in the active account; 409 if it's a system class.
    """
    cls = scope.db.scalar(scope.select(Class).where(Class.id == class_id))
    if cls is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Class not found."},
        )
    if cls.is_system:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "system_immutable", "message": "System classes cannot be renamed."},
        )
    cls.name = body.name.strip()
    scope.db.commit()
    scope.db.refresh(cls)
    parent_slug = (
        scope.db.scalar(scope.select(Class.slug).where(Class.id == cls.parent_id))
        if cls.parent_id
        else None
    )
    return ClassOut(
        id=cls.id, slug=cls.slug, name=cls.name, description=cls.description,
        parent_id=cls.parent_id, parent_slug=parent_slug,
        is_system=cls.is_system,
        document_count=_document_counts(scope).get(cls.id, 0),
    )


@router.delete("/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(
    class_id: uuid.UUID, scope: AccountScope = Depends(get_current_account)
) -> Response:
    """Delete a custom class (system classes are immutable).

    404 if the class isn't in the active account; 409 if it's a system class. Deleting
    cascades its `document_classes` links (documents keep their other classes).
    """
    cls = scope.db.scalar(scope.select(Class).where(Class.id == class_id))
    if cls is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Class not found."},
        )
    if cls.is_system:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "system_immutable", "message": "System classes cannot be deleted."},
        )
    scope.db.delete(cls)
    scope.db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
