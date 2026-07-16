"""Catalog: find_documents filters + corpus_overview (live DB).

`embed_query` is stubbed for the semantic 'about' path so no model loads.
"""

from __future__ import annotations

import datetime as dt
import uuid

from app.db.models import Class, Document, DocumentClass
from app.db.session import SessionLocal
from app.services import catalog

DIM = 768


def _basis(i: int) -> list[float]:
    v = [0.0] * DIM
    v[i] = 1.0
    return v


def _doc(db, account_id, *, title, slug=None, status="indexed", summary="summary",
         created=None, embedding=None) -> uuid.UUID:
    doc = Document(
        account_id=account_id, source="web_upload", original_filename=f"{title}.pdf",
        mime_type="application/pdf", file_hash=uuid.uuid4().hex, storage_path="/dev/null",
        status=status, title=title, summary=summary, summary_embedding=embedding,
    )
    if created is not None:
        doc.created_at = created
    db.add(doc)
    db.flush()
    if slug:
        cls = db.scalar(
            __import__("sqlalchemy").select(Class).where(
                Class.account_id == account_id, Class.slug == slug)
        )
        if cls is None:
            cls = Class(account_id=account_id, slug=slug, name=slug.title(), is_system=True)
            db.add(cls)
            db.flush()
        db.add(DocumentClass(account_id=account_id, document_id=doc.id,
                             class_id=cls.id, confidence=0.9))
    db.commit()
    return doc.id


def test_find_by_class(seeded_account) -> None:
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        inv = _doc(db, acct, title="ACME Invoice", slug="invoice")
        _doc(db, acct, title="Service Contract", slug="contract")

        found = catalog.find_documents(db, acct, class_slug="invoice")

        assert [d.document_id for d in found] == [inv]
        assert found[0].class_slugs == ["invoice"]


def test_find_by_name(seeded_account) -> None:
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        nda = _doc(db, acct, title="Meridian NDA")
        _doc(db, acct, title="Grocery Receipt")

        found = catalog.find_documents(db, acct, name="meridian")

        assert [d.document_id for d in found] == [nda]


def test_find_by_upload_window(seeded_account) -> None:
    acct = seeded_account["personal_id"]
    old = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    new = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    with SessionLocal() as db:
        _doc(db, acct, title="Old Doc", created=old)
        recent = _doc(db, acct, title="New Doc", created=new)

        found = catalog.find_documents(db, acct, uploaded_after=dt.date(2026, 3, 1))

        assert [d.document_id for d in found] == [recent]


def test_find_about_semantic(seeded_account, monkeypatch) -> None:
    acct = seeded_account["personal_id"]
    monkeypatch.setattr(catalog, "embed_query", lambda q: _basis(0))
    with SessionLocal() as db:
        close = _doc(db, acct, title="Energy Plan", embedding=_basis(0))
        _doc(db, acct, title="Cooking Recipe", embedding=_basis(5))

        found = catalog.find_documents(db, acct, about="energy optimization")

        assert found[0].document_id == close  # nearest summary embedding first


def test_corpus_overview_small_inlines_all(seeded_account) -> None:
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        _doc(db, acct, title="Invoice A", slug="invoice")
        _doc(db, acct, title="Invoice B", slug="invoice")
        _doc(db, acct, title="A Contract", slug="contract")

        ov = catalog.corpus_overview(db, acct)

        assert ov["total_documents"] == 3
        assert ov["by_class"]["invoice"] == 2
        assert ov["complete_listing"] is True
        assert len(ov["documents"]) == 3


def test_corpus_overview_excludes_unsearchable(seeded_account) -> None:
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        _doc(db, acct, title="Indexed", status="indexed")
        _doc(db, acct, title="Still OCRing", status="ocr_done")

        ov = catalog.corpus_overview(db, acct)

        assert ov["total_documents"] == 1  # ocr_done is not yet searchable
