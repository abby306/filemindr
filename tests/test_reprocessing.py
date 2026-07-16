"""Re-drive path: status routing, full re-drive, sweep, and account scoping.

All pipeline seams are mocked, so the entry points run offline. Documents are
committed under a `seeded_account`; its cascade delete tidies up on teardown.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.db.models import Class, Document, DocumentFact
from app.db.session import SessionLocal
from app.services import embeddings, extraction, ocr, reprocessing

PDF_MIME = "application/pdf"


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """Keep OCR-cache lookups off real storage and the encoder offline."""
    monkeypatch.setattr(ocr, "get_storage_root", lambda: tmp_path)
    monkeypatch.setattr(
        embeddings, "embed_passages",
        lambda texts: [[0.0] * embeddings.EMBEDDING_DIM for _ in texts],
    )


def _make_document(
    account_id: uuid.UUID, *, status: str, ocr_text: str = "Some text.", error: str | None = None
) -> uuid.UUID:
    with SessionLocal() as db:
        document = Document(
            account_id=account_id,
            source="web_upload",
            original_filename="doc.pdf",
            mime_type=PDF_MIME,
            file_hash=uuid.uuid4().hex,
            storage_path="/dev/null",
            status=status,
            error=error,
            ocr_text=ocr_text,
        )
        db.add(document)
        db.commit()
        return document.id


# --- routing ---------------------------------------------------------------
@pytest.mark.parametrize(
    "status, entry_name",
    [
        ("received", "run_ocr"),
        ("failed", "run_ocr"),
        ("ocr_done", "run_extraction"),
        ("extracted", "run_embedding"),
        ("needs_review", "run_embedding"),
    ],
)
def test_reprocess_routes_by_status(seeded_account, monkeypatch, status, entry_name) -> None:
    account_id = seeded_account["personal_id"]
    doc_id = _make_document(account_id, status=status)

    calls: list = []
    monkeypatch.setattr(ocr, "run_ocr", lambda d, a: calls.append(("run_ocr", d, a)))
    monkeypatch.setattr(extraction, "run_extraction", lambda d, a: calls.append(("run_extraction", d, a)))
    monkeypatch.setattr(embeddings, "run_embedding", lambda d, a: calls.append(("run_embedding", d, a)))

    used = reprocessing.reprocess_document(doc_id, account_id)

    # `used` reflects the (monkeypatched) function name; the recorder proves which
    # entry point ran for the status.
    assert used is not None
    assert calls == [(entry_name, doc_id, account_id)]


def test_reprocess_skips_terminal(seeded_account) -> None:
    account_id = seeded_account["personal_id"]
    doc_id = _make_document(account_id, status="indexed")
    assert reprocessing.reprocess_document(doc_id, account_id) is None


def test_reprocess_never_crosses_account(seeded_account, monkeypatch) -> None:
    personal = seeded_account["personal_id"]
    company = seeded_account["company_id"]
    doc_id = _make_document(personal, status="ocr_done")
    monkeypatch.setattr(extraction, "run_extraction", lambda d, a: pytest.fail("should not run"))

    assert reprocessing.reprocess_document(doc_id, company) is None


# --- full re-drive ---------------------------------------------------------
def test_reprocess_ocr_done_to_indexed(seeded_account, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    with SessionLocal() as db:
        db.add(Class(account_id=account_id, slug="invoice", name="Invoice", is_system=True))
        db.commit()
    doc_id = _make_document(account_id, status="ocr_done", ocr_text="Acme invoice total 10 USD.")

    canned = {
        "summary": "An invoice.",
        "classes": [{"slug": "invoice", "confidence": 0.95}],
        "atomic_facts": [{"text": "The total is 10 USD.", "page": 1}],
    }
    monkeypatch.setattr(
        extraction, "call_extraction_model", lambda text, classes: (json.dumps(canned), "m")
    )

    used = reprocessing.reprocess_document(doc_id, account_id)

    assert used == "run_extraction"
    with SessionLocal() as db:
        document = db.get(Document, doc_id)
        assert document.status == "indexed"  # extraction chained through embedding
        fact = db.query(DocumentFact).filter_by(document_id=doc_id).one()
        assert fact.embedding is not None


def test_reprocess_failed_clears_error(seeded_account, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    doc_id = _make_document(account_id, status="failed", error="OCR failed: boom")
    monkeypatch.setattr(ocr, "run_ocr", lambda d, a: None)  # re-OCR is a no-op here

    reprocessing.reprocess_document(doc_id, account_id)

    with SessionLocal() as db:
        assert db.get(Document, doc_id).error is None


# --- sweep -----------------------------------------------------------------
def test_reprocess_stuck_sweeps_account(seeded_account, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    with SessionLocal() as db:
        db.add(Class(account_id=account_id, slug="invoice", name="Invoice", is_system=True))
        db.commit()
    extracted_id = _make_document(account_id, status="extracted")
    indexed_id = _make_document(account_id, status="indexed")  # terminal -> untouched

    summary = reprocessing.reprocess_stuck(account_id=account_id)

    assert summary == {"run_embedding": 1}  # only the extracted doc swept
    with SessionLocal() as db:
        assert db.get(Document, extracted_id).status == "indexed"
        assert db.get(Document, indexed_id).status == "indexed"
