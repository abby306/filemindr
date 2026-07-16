"""File + page-image endpoints (`GET /documents/{id}/file`, `.../pages/{page}`).

Covers streaming the original file, rasterizing a PDF page, image pass-through,
the no-page-image type (docx → 415), out-of-range pages, and account isolation.
Offline: PDFs are built with fitz; the page cache is redirected to a tmp dir.
"""

from __future__ import annotations

import base64
import uuid

import fitz
import pytest
from fastapi.testclient import TestClient

from app.db.models import Document
from app.db.session import SessionLocal
from app.main import app
from app.services import ocr, storage

# 1x1 PNG.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _tmp_page_cache(monkeypatch, tmp_path):
    """Keep the rasterized-page cache off real storage."""
    monkeypatch.setattr(storage, "get_storage_root", lambda: tmp_path)


def _headers(seeded_account, *, account="personal_id") -> dict:
    return {
        "Authorization": f"Bearer {seeded_account['user_id']}",
        "X-Account-Id": str(seeded_account[account]),
    }


def _pdf_bytes(pages: int = 1) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"Page {i + 1} content")
    data = doc.tobytes()
    doc.close()
    return data


def _make_doc(account_id, tmp_path, name, mime, content: bytes, *, page_count=1):
    path = tmp_path / name
    path.write_bytes(content)
    with SessionLocal() as db:
        doc = Document(
            account_id=account_id, source="web_upload", original_filename=name,
            mime_type=mime, file_hash=uuid.uuid4().hex, storage_path=str(path),
            status="indexed", page_count=page_count,
        )
        db.add(doc)
        db.commit()
        return doc.id


def test_get_file_streams_original(client, seeded_account, tmp_path) -> None:
    content = _pdf_bytes()
    doc_id = _make_doc(seeded_account["personal_id"], tmp_path, "doc.pdf", ocr.PDF_MIME, content)
    res = client.get(f"/api/v1/documents/{doc_id}/file", headers=_headers(seeded_account))
    assert res.status_code == 200
    assert res.headers["content-type"] == ocr.PDF_MIME
    assert res.content == content


def test_get_file_foreign_account_404(client, seeded_account, tmp_path) -> None:
    doc_id = _make_doc(seeded_account["personal_id"], tmp_path, "doc.pdf", ocr.PDF_MIME, _pdf_bytes())
    res = client.get(
        f"/api/v1/documents/{doc_id}/file",
        headers=_headers(seeded_account, account="company_id"),
    )
    assert res.status_code == 404


def test_render_pdf_page_returns_png(client, seeded_account, tmp_path) -> None:
    doc_id = _make_doc(
        seeded_account["personal_id"], tmp_path, "doc.pdf", ocr.PDF_MIME, _pdf_bytes(2), page_count=2
    )
    res = client.get(f"/api/v1/documents/{doc_id}/pages/1", headers=_headers(seeded_account))
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic


def test_render_page_out_of_range_404(client, seeded_account, tmp_path) -> None:
    doc_id = _make_doc(seeded_account["personal_id"], tmp_path, "doc.pdf", ocr.PDF_MIME, _pdf_bytes(1))
    res = client.get(f"/api/v1/documents/{doc_id}/pages/5", headers=_headers(seeded_account))
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "page_out_of_range"


def test_image_page_passthrough(client, seeded_account, tmp_path) -> None:
    doc_id = _make_doc(seeded_account["personal_id"], tmp_path, "img.png", "image/png", _PNG)
    res = client.get(f"/api/v1/documents/{doc_id}/pages/1", headers=_headers(seeded_account))
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content == _PNG


def test_docx_has_no_page_image_415(client, seeded_account, tmp_path) -> None:
    doc_id = _make_doc(seeded_account["personal_id"], tmp_path, "d.docx", ocr.DOCX_MIME, b"PK\x03\x04stub")
    res = client.get(f"/api/v1/documents/{doc_id}/pages/1", headers=_headers(seeded_account))
    assert res.status_code == 415
    assert res.json()["detail"]["code"] == "not_renderable"
