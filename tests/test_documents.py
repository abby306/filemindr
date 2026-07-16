"""Upload endpoint: dedup, MIME validation, OCR hand-off, account isolation.

Storage is redirected to a tmp dir and uploads use a text-layer PDF, so the
background OCR task runs entirely locally (no Vision/network calls).
"""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from app.db.models import Document, DocumentFact
from app.db.session import SessionLocal
from app.main import app
from app.services import embeddings, extraction, ocr, storage


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def tmp_storage(monkeypatch, tmp_path):
    """Point storage + OCR cache at a throwaway dir and stub the extraction LLM.

    OCR now chains into extraction; stubbing the model call keeps the upload path
    offline and deterministic (no DeepSeek network call from the background task).
    """
    monkeypatch.setattr(storage, "get_storage_root", lambda: tmp_path)
    monkeypatch.setattr(ocr, "get_storage_root", lambda: tmp_path)
    canned = {"summary": "stub", "classes": [], "atomic_facts": []}
    monkeypatch.setattr(
        extraction, "call_extraction_model", lambda text, classes: (json.dumps(canned), "stub")
    )
    # Extraction chains into embedding (incl. needs_review); stub the encoder so
    # the upload path stays offline and fast (no bge model load).
    monkeypatch.setattr(
        embeddings, "embed_passages",
        lambda texts: [[0.0] * embeddings.EMBEDDING_DIM for _ in texts],
    )


def _text_pdf_bytes(body: str = "Invoice total 1240 USD due 2025-04-01. Acme Inc.") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), body + " " + ("filler text " * 10))
    data = doc.tobytes()
    doc.close()
    return data


def _auth(seeded_account, account_key: str = "personal_id") -> dict:
    return {
        "Authorization": f"Bearer {seeded_account['user_id']}",
        "X-Account-Id": str(seeded_account[account_key]),
    }


def _upload(client, headers, content: bytes, name: str = "doc.pdf", mime: str = ocr.PDF_MIME):
    return client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (name, io.BytesIO(content), mime)},
    )


def test_upload_runs_ocr_then_extraction(client, seeded_account) -> None:
    headers = _auth(seeded_account)
    res = _upload(client, headers, _text_pdf_bytes())
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "received"
    doc_id = body["id"]

    # Background OCR + chained extraction have run by the time the request returns.
    detail = client.get(f"/api/v1/documents/{doc_id}", headers=headers).json()
    # OCR persisted its results...
    assert detail["page_count"] == 1
    assert detail["language"] is not None  # exact code is unreliable on tiny text
    # ...and the pipeline advanced past ocr_done into extraction. The stub returns
    # no classes, so the document lands in needs_review.
    assert detail["status"] == "needs_review"


def test_dedup_returns_existing_document(client, seeded_account) -> None:
    headers = _auth(seeded_account)
    content = _text_pdf_bytes("Unique dedup body 42 with enough characters to detect.")

    first = _upload(client, headers, content)
    assert first.status_code == 201

    second = _upload(client, headers, content)
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

    listing = client.get("/api/v1/documents", headers=headers).json()
    assert sum(1 for d in listing["items"] if d["id"] == first.json()["id"]) == 1


def test_unsupported_mime_rejected(client, seeded_account) -> None:
    res = _upload(client, _auth(seeded_account), b"hello world", name="notes.txt", mime="text/plain")
    assert res.status_code == 415
    assert res.json()["detail"]["code"] == "unsupported_media_type"


def test_empty_file_rejected(client, seeded_account) -> None:
    res = _upload(client, _auth(seeded_account), b"", name="empty.pdf")
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "empty_file"


def test_oversized_upload_rejected(client, seeded_account, monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)  # cap below any real file
    res = _upload(client, _auth(seeded_account), _text_pdf_bytes())
    assert res.status_code == 413
    assert res.json()["detail"]["code"] == "file_too_large"


def test_upload_requires_auth(client) -> None:
    res = _upload(client, {}, _text_pdf_bytes())
    assert res.status_code == 401


def test_account_isolation_on_detail(client, seeded_account) -> None:
    # Upload under the personal account…
    personal = _auth(seeded_account, "personal_id")
    doc_id = _upload(client, personal, _text_pdf_bytes("Isolation probe body text here.")).json()["id"]

    # …the same user, scoped to the company account, cannot see it.
    company = _auth(seeded_account, "company_id")
    res = client.get(f"/api/v1/documents/{doc_id}", headers=company)
    assert res.status_code == 404

    listing = client.get("/api/v1/documents", headers=company).json()
    assert all(d["id"] != doc_id for d in listing["items"])


def test_delete_document_removes_row_file_and_children(client, seeded_account) -> None:
    headers = _auth(seeded_account)
    doc_id = _upload(client, headers, _text_pdf_bytes()).json()["id"]

    with SessionLocal() as db:
        path = db.get(Document, uuid.UUID(doc_id)).storage_path
    assert Path(path).exists()

    res = client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert res.status_code == 204

    # Row gone (404), file removed, and child facts cascaded away.
    assert client.get(f"/api/v1/documents/{doc_id}", headers=headers).status_code == 404
    assert not Path(path).exists()
    with SessionLocal() as db:
        assert db.query(DocumentFact).filter_by(document_id=uuid.UUID(doc_id)).count() == 0


def test_delete_document_foreign_account_404(client, seeded_account) -> None:
    doc_id = _upload(client, _auth(seeded_account), _text_pdf_bytes()).json()["id"]
    res = client.delete(
        f"/api/v1/documents/{doc_id}", headers=_auth(seeded_account, "company_id")
    )
    assert res.status_code == 404
    # Still there for the owner.
    assert client.get(f"/api/v1/documents/{doc_id}", headers=_auth(seeded_account)).status_code == 200
