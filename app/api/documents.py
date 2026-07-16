"""Document ingest + listing endpoints.

`POST /documents` is the web-upload path: validate, content-address, dedup, and
persist at status `received`, then kick OCR off as a background task. Reads are
account-scoped through `AccountScope`, so no endpoint can see another account's
documents.
"""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import json
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, tuple_, update
from sqlalchemy.orm import aliased
from starlette.concurrency import run_in_threadpool

from app.api.schemas import (
    ClassCardOut,
    DateCardOut,
    DocumentCardOut,
    DocumentClassAssignIn,
    DocumentListOut,
    DocumentOut,
    EntitiesCardOut,
    FactRegionOut,
    PrimaryClassOut,
    TypedFactCardOut,
)
from app.core.config import get_settings
from app.core.scoping import AccountScope, get_current_account
from app.db.models import (
    Class,
    Document,
    DocumentClass,
    DocumentDate,
    DocumentEntity,
    DocumentFact,
    Entity,
    TypedFact,
)
from app.services import ocr, rendering, usage
from app.services.events import record_event
from app.services.storage import FileTooLargeError, save_stream
from app.services.taxonomy import expand_class_slugs, get_or_create_class

router = APIRouter(prefix="/api/v1", tags=["documents"])

# Map extensions to MIME for clients that send a blank/generic content type.
_MIME_BY_EXT = {
    ".pdf": ocr.PDF_MIME,
    ".docx": ocr.DOCX_MIME,
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _resolve_mime(content_type: str | None, filename: str | None) -> str | None:
    """Pick a supported MIME type from the header, falling back to the extension."""
    if content_type in ocr.ALLOWED_MIME_TYPES:
        return content_type
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[1].lower()
        return _MIME_BY_EXT.get(ext)
    return None


def _encode_cursor(document: Document) -> str:
    payload = json.dumps([document.created_at.isoformat(), str(document.id)])
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[dt.datetime, uuid.UUID]:
    try:
        created_iso, doc_id = json.loads(base64.urlsafe_b64decode(cursor).decode())
        return dt.datetime.fromisoformat(created_iso), uuid.UUID(doc_id)
    except (ValueError, binascii.Error, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "bad_cursor", "message": "Invalid pagination cursor."},
        )


@router.post("/documents", response_model=DocumentOut)
async def upload_document(
    response: Response,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    scope: AccountScope = Depends(get_current_account),
) -> DocumentOut:
    """Accept a file, dedup by content hash, and start OCR in the background."""
    mime_type = _resolve_mime(file.content_type, file.filename)
    if mime_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "unsupported_media_type",
                "message": "Only PDF, PNG, JPEG, and DOCX files are accepted.",
            },
        )

    ext = ocr.extension_for(mime_type, file.filename)
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    file.file.seek(0)
    try:
        stored = await run_in_threadpool(
            save_stream, file.file, scope.account_id, ext, max_bytes=max_bytes
        )
    except FileTooLargeError:
        raise HTTPException(
            status_code=413,  # Content Too Large
            detail={
                "code": "file_too_large",
                "message": f"File exceeds the {settings.max_upload_mb} MB limit.",
            },
        )

    if stored.byte_size == 0:
        Path(stored.storage_path).unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_file", "message": "Uploaded file is empty."},
        )

    # Dedup: identical (account, file_hash) returns the existing document.
    # Checked before quota — a re-upload consumes nothing new.
    existing = scope.db.scalar(
        scope.select(Document).where(Document.file_hash == stored.file_hash)
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return DocumentOut.model_validate(existing)

    try:
        usage.check_document_quota(
            scope.db, scope.account_id, incoming_bytes=stored.byte_size
        )
    except usage.QuotaExceededError as exc:
        # Content-addressed and past dedup, so no document row references this
        # file — safe to remove the just-stored bytes.
        Path(stored.storage_path).unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=usage.quota_http_detail(exc),
        )

    document = Document(
        account_id=scope.account_id,
        uploaded_by=scope.user.id,
        source="web_upload",
        original_filename=file.filename or f"upload{ext}",
        mime_type=mime_type,
        byte_size=stored.byte_size,
        file_hash=stored.file_hash,
        storage_path=stored.storage_path,
        status="received",
    )
    scope.db.add(document)
    scope.db.flush()
    record_event(
        scope.db,
        account_id=scope.account_id,
        document_id=document.id,
        stage="received",
        status="succeeded",
        detail={"source": "web_upload", "byte_size": stored.byte_size},
    )
    usage.record_usage(
        scope.db,
        scope.account_id,
        type=usage.EVENT_DOCUMENT_UPLOADED,
        user_id=scope.user.id,
        meta={
            "document_id": str(document.id),
            "byte_size": stored.byte_size,
            "mime_type": mime_type,
        },
        documents=1,
        storage_bytes=stored.byte_size,
    )
    scope.db.commit()
    scope.db.refresh(document)

    background_tasks.add_task(ocr.run_ocr, document.id, scope.account_id)

    response.status_code = status.HTTP_201_CREATED
    return DocumentOut.model_validate(document)


@router.get("/documents", response_model=DocumentListOut)
def list_documents(
    scope: AccountScope = Depends(get_current_account),
    status_filter: str | None = Query(default=None, alias="status"),
    class_filter: str | None = Query(default=None, alias="class"),
    primary_only: bool = Query(default=False, alias="primary"),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
) -> DocumentListOut:
    """List the active account's documents, newest first (keyset paginated).

    Optional `status` and `class` (slug) filters; `class` restricts to documents
    labelled with that class in the active account. With `primary=true`, `class`
    matches only documents whose **primary** class falls under that slug — this
    is the archive browse view (one document → one folder), vs. the default which
    matches any label (used where recall matters).
    """
    query = scope.select(Document).order_by(
        Document.created_at.desc(), Document.id.desc()
    )
    if status_filter is not None:
        query = query.where(Document.status == status_filter)
    if class_filter is not None:
        slugs = expand_class_slugs(scope.db, scope.account_id, class_filter)
        link = (
            scope.select(DocumentClass)
            .join(Class, Class.id == DocumentClass.class_id)
            .where(Class.slug.in_(slugs))
        )
        if primary_only:
            link = link.where(DocumentClass.is_primary)
        query = query.where(
            Document.id.in_(link.with_only_columns(DocumentClass.document_id))
        )
    if cursor is not None:
        cur_created, cur_id = _decode_cursor(cursor)
        query = query.where(
            tuple_(Document.created_at, Document.id) < (cur_created, cur_id)
        )

    rows = scope.db.scalars(query.limit(limit + 1)).all()
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = _encode_cursor(page[-1]) if has_more and page else None
    items = [DocumentOut.model_validate(d) for d in page]
    primaries = _primary_classes(scope, [d.id for d in page])
    for item in items:
        item.primary_class = primaries.get(item.id)
    return DocumentListOut(items=items, next_cursor=next_cursor)


def _primary_classes(
    scope: AccountScope, document_ids: list[uuid.UUID]
) -> dict[uuid.UUID, PrimaryClassOut]:
    """Batch-load each document's primary class (its folder) for a list page."""
    if not document_ids:
        return {}
    rows = scope.db.execute(
        scope.select(DocumentClass)
        .join(Class, Class.id == DocumentClass.class_id)
        .where(
            DocumentClass.document_id.in_(document_ids),
            DocumentClass.is_primary,
        )
        .with_only_columns(DocumentClass.document_id, Class.slug, Class.name)
    ).all()
    return {
        doc_id: PrimaryClassOut(slug=slug, name=name) for doc_id, slug, name in rows
    }


@router.get("/documents/{document_id}", response_model=DocumentCardOut)
def get_document(
    document_id: uuid.UUID,
    scope: AccountScope = Depends(get_current_account),
) -> DocumentCardOut:
    """Fetch one document's full card by id, scoped to the active account.

    Returns 404 for another account's document. Card sections are empty until
    extraction has run.
    """
    document = scope.db.scalar(
        scope.select(Document).where(Document.id == document_id)
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Document not found."},
        )
    return _build_card(scope, document)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    scope: AccountScope = Depends(get_current_account),
) -> Response:
    """Delete a document and its stored file (archive trash). Account-scoped.

    The row delete cascades to the card tables + facts + events (DB `ON DELETE
    CASCADE`); the content-addressed file is removed best-effort. 404 for an
    unknown/foreign document. Shared OCR/page caches (keyed by content hash) are
    left intact — harmless, and reused if the same file is uploaded again.
    """
    document = scope.db.scalar(scope.select(Document).where(Document.id == document_id))
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Document not found."},
        )
    if document.storage_path:
        try:
            Path(document.storage_path).unlink(missing_ok=True)
        except OSError:
            pass  # best-effort: a stuck file must not block deleting the record
    scope.db.delete(document)
    scope.db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_id}/classes", response_model=DocumentCardOut)
def assign_document_classes(
    document_id: uuid.UUID,
    body: DocumentClassAssignIn,
    scope: AccountScope = Depends(get_current_account),
) -> DocumentCardOut:
    """Human-in-the-loop: confirm a document's classes and clear its review flag.

    The user picks existing `class_ids` and/or creates a `new_class` inline (the
    review UX for low-confidence / ambiguous / unclassified uploads). The chosen
    classes replace the model's guesses (`assigned_by="user"`), `review_reason` is
    cleared, and a document still in `needs_review` advances to `indexed` (it was
    already embedded). 404 for a foreign/unknown document or class; 400 if empty.
    """
    document = scope.db.scalar(scope.select(Document).where(Document.id == document_id))
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Document not found."},
        )

    class_ids: list[uuid.UUID] = list(dict.fromkeys(body.class_ids))
    # Validate every picked id belongs to this account before touching anything.
    for class_id in class_ids:
        if scope.db.scalar(scope.select(Class).where(Class.id == class_id)) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "class_not_found", "message": f"Class {class_id} not found."},
            )

    if body.new_class is not None:
        try:
            created = get_or_create_class(
                scope.db, scope.account_id,
                name=body.new_class.name,
                description=body.new_class.description,
                parent_id=body.new_class.parent_id,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_name", "message": str(exc)},
            )
        if created.id not in class_ids:
            class_ids.append(created.id)

    if not class_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "no_classes", "message": "Provide at least one class or a new_class."},
        )

    # `add` keeps existing labels (drag-to-folder); `replace` swaps them out
    # (review/move). User labels are authoritative, so no confidence.
    if body.mode == "add":
        existing = scope.db.execute(
            scope.select(DocumentClass)
            .where(DocumentClass.document_id == document.id)
            .with_only_columns(DocumentClass.class_id, DocumentClass.is_primary)
        ).all()
        existing_ids = {cid for cid, _ in existing}
        has_primary = any(is_primary for _, is_primary in existing)
        new_ids = [cid for cid in class_ids if cid not in existing_ids]
        for index, class_id in enumerate(new_ids):
            scope.db.add(
                DocumentClass(
                    account_id=scope.account_id,
                    document_id=document.id,
                    class_id=class_id,
                    confidence=None,
                    assigned_by="user",
                    # only take primary if the doc had none (an unfiled doc)
                    is_primary=(not has_primary and index == 0),
                )
            )
        written = len(new_ids)
    elif body.mode == "set_primary":
        # Make the first picked class the primary, keeping the document's other
        # labels — a non-destructive "move to folder". Add any picked class that
        # isn't already present (as a non-primary), then flip the primary flag.
        existing_ids = {
            cid
            for (cid,) in scope.db.execute(
                scope.select(DocumentClass)
                .where(DocumentClass.document_id == document.id)
                .with_only_columns(DocumentClass.class_id)
            ).all()
        }
        for class_id in class_ids:
            if class_id not in existing_ids:
                scope.db.add(
                    DocumentClass(
                        account_id=scope.account_id,
                        document_id=document.id,
                        class_id=class_id,
                        confidence=None,
                        assigned_by="user",
                        is_primary=False,
                    )
                )
        scope.db.flush()
        primary_id = class_ids[0]
        # Two ordered statements (clear then set) so we never transiently hold two
        # primaries — a single combined UPDATE can trip the one-primary unique index
        # depending on row order.
        scope.db.execute(
            update(DocumentClass)
            .where(
                DocumentClass.account_id == scope.account_id,
                DocumentClass.document_id == document.id,
                DocumentClass.is_primary,
            )
            .values(is_primary=False)
        )
        scope.db.execute(
            update(DocumentClass)
            .where(
                DocumentClass.account_id == scope.account_id,
                DocumentClass.document_id == document.id,
                DocumentClass.class_id == primary_id,
            )
            .values(is_primary=True)
        )
        written = len(class_ids)
    else:  # replace
        scope.db.execute(
            delete(DocumentClass).where(
                DocumentClass.account_id == scope.account_id,
                DocumentClass.document_id == document.id,
            )
        )
        # The first picked class becomes the primary (folder placement).
        for index, class_id in enumerate(class_ids):
            scope.db.add(
                DocumentClass(
                    account_id=scope.account_id,
                    document_id=document.id,
                    class_id=class_id,
                    confidence=None,
                    assigned_by="user",
                    is_primary=index == 0,
                )
            )
        written = len(class_ids)

    document.review_reason = None
    if document.status == "needs_review":
        document.status = "indexed"
    record_event(
        scope.db,
        account_id=scope.account_id,
        document_id=document.id,
        stage="extraction",
        status="succeeded",
        detail={"action": "classes_confirmed", "mode": body.mode, "classes": written, "by": "user"},
    )
    scope.db.commit()
    scope.db.refresh(document)
    return _build_card(scope, document)


@router.get("/documents/{document_id}/file")
def get_document_file(
    document_id: uuid.UUID,
    scope: AccountScope = Depends(get_current_account),
) -> FileResponse:
    """Stream a document's original file (for download / pdf.js). Account-scoped."""
    document = scope.db.scalar(scope.select(Document).where(Document.id == document_id))
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Document not found."},
        )
    path = Path(document.storage_path)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "file_missing", "message": "Stored file not found."},
        )
    return FileResponse(
        path,
        media_type=document.mime_type or "application/octet-stream",
        filename=document.original_filename,
    )


@router.get("/documents/{document_id}/facts", response_model=list[FactRegionOut])
def get_document_facts(
    document_id: uuid.UUID,
    scope: AccountScope = Depends(get_current_account),
) -> list[FactRegionOut]:
    """Atomic facts with a normalized bbox for provenance overlay (SourceGlow).

    A cited fact's `bbox` (when available, PDFs only) lets the source pane sweep a
    highlighter over the exact region; otherwise the client highlights the page.
    """
    document = scope.db.scalar(scope.select(Document).where(Document.id == document_id))
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Document not found."},
        )
    facts = scope.db.execute(
        scope.select(DocumentFact)
        .where(DocumentFact.document_id == document.id)
        .with_only_columns(
            DocumentFact.id, DocumentFact.page, DocumentFact.text, DocumentFact.bbox
        )
    ).all()
    dims = (
        rendering.page_dimensions(document.storage_path, document.mime_type, document.ocr_engine)
        if Path(document.storage_path).is_file()
        else {}
    )
    out: list[FactRegionOut] = []
    for fact_id, page, text, raw in facts:
        bbox = None
        if isinstance(raw, dict) and raw.get("bbox") and page in dims:
            width, height = dims[page]
            bbox = rendering.normalize_bbox(raw["bbox"], width, height)
        out.append(FactRegionOut(id=fact_id, page=page, text=text, bbox=bbox))
    return out


@router.get("/documents/{document_id}/pages/{page}")
def get_document_page(
    document_id: uuid.UUID,
    page: int,
    scope: AccountScope = Depends(get_current_account),
    dpi: int = Query(default=rendering.DEFAULT_DPI, ge=rendering.MIN_DPI, le=rendering.MAX_DPI),
) -> Response:
    """Render one page as an image (PDF rasterized + cached; images passed
    through) for the source pane / thumbnails. Account-scoped.

    404 for an unknown/foreign document, a missing file, or an out-of-range page;
    415 for a type with no page image (e.g. docx).
    """
    document = scope.db.scalar(scope.select(Document).where(Document.id == document_id))
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Document not found."},
        )
    if not Path(document.storage_path).is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "file_missing", "message": "Stored file not found."},
        )
    try:
        rendered = rendering.render_page(
            storage_path=document.storage_path,
            mime_type=document.mime_type,
            file_hash=document.file_hash,
            page=page,
            dpi=dpi,
        )
    except rendering.PageOutOfRange:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "page_out_of_range", "message": f"No page {page}."},
        )
    except rendering.PageNotRenderable:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"code": "not_renderable", "message": "This file type has no page image."},
        )
    return Response(
        content=rendered.data,
        media_type=rendered.media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


def _build_card(scope: AccountScope, document: Document) -> DocumentCardOut:
    """Assemble a `DocumentCardOut` from the extracted card tables (scoped)."""
    parent_cls = aliased(Class)
    classes = scope.db.execute(
        scope.select(DocumentClass)
        .where(DocumentClass.document_id == document.id)
        .join(Class, Class.id == DocumentClass.class_id)
        .join(parent_cls, parent_cls.id == Class.parent_id, isouter=True)
        .with_only_columns(
            Class.slug, Class.name, DocumentClass.confidence,
            DocumentClass.assigned_by, parent_cls.slug, DocumentClass.is_primary,
        )
        .order_by(
            DocumentClass.is_primary.desc(),
            DocumentClass.confidence.desc().nullslast(),
        )
    ).all()

    entity_rows = scope.db.execute(
        scope.select(DocumentEntity)
        .where(DocumentEntity.document_id == document.id)
        .join(Entity, Entity.id == DocumentEntity.entity_id)
        .with_only_columns(Entity.type, Entity.name)
    ).all()
    entities = EntitiesCardOut()
    _entity_bucket = {
        "person": entities.people,
        "organization": entities.organizations,
        "place": entities.places,
    }
    for type_, name in entity_rows:
        _entity_bucket[type_].append(name)

    dates = scope.db.scalars(
        scope.select(DocumentDate)
        .where(DocumentDate.document_id == document.id)
        .order_by(DocumentDate.value.asc().nullslast())
    ).all()

    typed_facts = scope.db.scalars(
        scope.select(TypedFact)
        .where(TypedFact.document_id == document.id)
        .order_by(TypedFact.label.asc())
    ).all()

    fact_count = scope.db.scalar(
        scope.select(DocumentFact)
        .where(DocumentFact.document_id == document.id)
        .with_only_columns(func.count())
    ) or 0

    card = DocumentCardOut.model_validate(document)
    card.classes = [
        ClassCardOut(
            slug=slug, name=name, confidence=confidence,
            assigned_by=assigned_by, parent_slug=parent_slug, is_primary=is_primary,
        )
        for slug, name, confidence, assigned_by, parent_slug, is_primary in classes
    ]
    card.primary_class = next(
        (PrimaryClassOut(slug=c.slug, name=c.name) for c in card.classes if c.is_primary),
        None,
    )
    card.entities = entities
    card.dates = [
        DateCardOut(value=d.value, raw_text=d.raw_text, role=d.role) for d in dates
    ]
    card.typed_facts = [
        TypedFactCardOut(
            label=f.label,
            value=f.value,
            value_numeric=float(f.value_numeric) if f.value_numeric is not None else None,
            type=f.value_type,
            unit=f.unit,
            page=f.page,
        )
        for f in typed_facts
    ]
    card.fact_count = fact_count
    return card
