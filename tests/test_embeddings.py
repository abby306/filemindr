"""Embeddings: passage/query asymmetry, fact+summary indexing, scoping, chaining.

The compute seam (`embeddings._encode` / `embed_passages`) is monkeypatched, so
the suite never downloads the bge model. Fan-out tests use a real document under
a `seeded_account`; the account's cascade delete tidies up on teardown.
"""

from __future__ import annotations

import json
import threading
import time
import uuid

import pytest

from app.db.models import Class, Document, DocumentFact
from app.db.session import SessionLocal
from app.services import embeddings, extraction, ocr

PDF_MIME = "application/pdf"


@pytest.fixture(autouse=True)
def tmp_storage(monkeypatch, tmp_path):
    """Keep the OCR-cache lookup (used by the extraction chain) off real storage."""
    monkeypatch.setattr(ocr, "get_storage_root", lambda: tmp_path)


@pytest.fixture
def stub_encoder(monkeypatch):
    """Deterministic offline embeddings: a distinct 768-vec per input text."""

    def fake_passages(texts):
        return [[0.001 * (i + 1)] * embeddings.EMBEDDING_DIM for i, _ in enumerate(texts)]

    monkeypatch.setattr(embeddings, "embed_passages", fake_passages)


def _make_doc(
    account_id: uuid.UUID,
    *,
    status: str = "extracted",
    n_facts: int = 3,
    summary: str | None = "A short document summary.",
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
            summary=summary,
            ocr_text="Some text.",
        )
        db.add(document)
        db.flush()
        for i in range(n_facts):
            db.add(
                DocumentFact(
                    account_id=account_id,
                    document_id=document.id,
                    text=f"Atomic fact number {i}.",
                    page=1,
                )
            )
        db.commit()
        return document.id


# --- passage / query asymmetry (offline) -----------------------------------
def test_embed_query_prefixes_instruction(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(
        embeddings, "_encode",
        lambda texts: captured.setdefault("texts", texts) or [[0.0] * 768 for _ in texts],
    )
    embeddings.embed_query("how much did I spend?")
    assert captured["texts"] == [
        embeddings.QUERY_INSTRUCTION + "how much did I spend?"
    ]


def test_embed_passages_has_no_prefix(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(
        embeddings, "_encode",
        lambda texts: captured.setdefault("texts", texts) or [[0.0] * 768 for _ in texts],
    )
    embeddings.embed_passages(["a passage"])
    assert captured["texts"] == ["a passage"]


def test_embed_passages_empty_is_noop() -> None:
    assert embeddings.embed_passages([]) == []


def test_model_loads_once_under_concurrency(monkeypatch) -> None:
    """Concurrent first-calls must initialize the encoder exactly once."""
    monkeypatch.setattr(embeddings, "_model", None)
    calls = {"n": 0}

    def slow_load():
        calls["n"] += 1
        time.sleep(0.05)  # widen the race window
        return object()

    monkeypatch.setattr(embeddings, "_load_model", slow_load)

    results: list = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()  # release all threads into _get_model at once
        results.append(embeddings._get_model())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls["n"] == 1  # loaded exactly once
    assert len({id(r) for r in results}) == 1  # everyone got the same instance
    monkeypatch.setattr(embeddings, "_model", None)  # reset for other tests


# --- run_embedding fan-out (live DB) ---------------------------------------
def test_run_embedding_indexes_facts_and_summary(seeded_account, stub_encoder) -> None:
    account_id = seeded_account["personal_id"]
    doc_id = _make_doc(account_id, n_facts=3)

    embeddings.run_embedding(doc_id, account_id)

    with SessionLocal() as db:
        document = db.get(Document, doc_id)
        assert document.status == "indexed"
        assert document.summary_embedding is not None
        assert len(document.summary_embedding) == embeddings.EMBEDDING_DIM
        facts = db.query(DocumentFact).filter_by(document_id=doc_id).all()
        assert len(facts) == 3
        assert all(f.embedding is not None for f in facts)
        assert all(len(f.embedding) == embeddings.EMBEDDING_DIM for f in facts)


def test_run_embedding_handles_no_facts(seeded_account, stub_encoder) -> None:
    account_id = seeded_account["personal_id"]
    doc_id = _make_doc(account_id, n_facts=0, summary="Summary only.")

    embeddings.run_embedding(doc_id, account_id)

    with SessionLocal() as db:
        document = db.get(Document, doc_id)
        assert document.status == "indexed"
        assert document.summary_embedding is not None


def test_run_embedding_is_idempotent(seeded_account, stub_encoder) -> None:
    account_id = seeded_account["personal_id"]
    doc_id = _make_doc(account_id, n_facts=2)

    embeddings.run_embedding(doc_id, account_id)
    embeddings.run_embedding(doc_id, account_id)  # re-index overwrites in place

    with SessionLocal() as db:
        assert db.query(DocumentFact).filter_by(document_id=doc_id).count() == 2
        assert db.get(Document, doc_id).status == "indexed"


def test_run_embedding_preserves_needs_review(seeded_account, stub_encoder) -> None:
    # A low-confidence doc is embedded (searchable) but keeps its review flag.
    account_id = seeded_account["personal_id"]
    doc_id = _make_doc(account_id, status="needs_review", n_facts=2)

    embeddings.run_embedding(doc_id, account_id)

    with SessionLocal() as db:
        document = db.get(Document, doc_id)
        assert document.status == "needs_review"  # not flipped to indexed
        facts = db.query(DocumentFact).filter_by(document_id=doc_id).all()
        assert all(f.embedding is not None for f in facts)


def test_run_embedding_skips_unindexable_status(seeded_account, stub_encoder) -> None:
    account_id = seeded_account["personal_id"]
    doc_id = _make_doc(account_id, status="received", n_facts=1)

    embeddings.run_embedding(doc_id, account_id)  # received -> no-op

    with SessionLocal() as db:
        document = db.get(Document, doc_id)
        assert document.status == "received"
        assert db.query(DocumentFact).filter_by(document_id=doc_id).one().embedding is None


def test_run_embedding_never_crosses_account(seeded_account, stub_encoder) -> None:
    personal = seeded_account["personal_id"]
    company = seeded_account["company_id"]
    doc_id = _make_doc(personal, n_facts=1)

    embeddings.run_embedding(doc_id, company)  # wrong account — no-op

    with SessionLocal() as db:
        document = db.get(Document, doc_id)
        assert document.status == "extracted"
        assert db.query(DocumentFact).filter_by(document_id=doc_id).one().embedding is None


# --- extraction -> embedding chain (live DB, both seams stubbed) ------------
def test_extraction_chains_embedding_to_indexed(seeded_account, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    # Seed the class so the canned response routes to `extracted` (not needs_review).
    with SessionLocal() as db:
        db.add(Class(account_id=account_id, slug="invoice", name="Invoice", is_system=True))
        document = Document(
            account_id=account_id,
            source="web_upload",
            original_filename="invoice.pdf",
            mime_type=PDF_MIME,
            file_hash=uuid.uuid4().hex,
            storage_path="/dev/null",
            status="ocr_done",
            ocr_text="Acme Inc invoice total 1240 USD.",
        )
        db.add(document)
        db.commit()
        doc_id = document.id

    canned = {
        "summary": "An Acme invoice.",
        "classes": [{"slug": "invoice", "confidence": 0.95}],
        "atomic_facts": [{"text": "The invoice total is 1240 USD.", "page": 1}],
    }
    monkeypatch.setattr(
        extraction, "call_extraction_model", lambda text, classes: (json.dumps(canned), "m")
    )
    monkeypatch.setattr(
        embeddings, "embed_passages",
        lambda texts: [[0.01] * embeddings.EMBEDDING_DIM for _ in texts],
    )

    extraction.run_extraction(doc_id, account_id)  # chains run_embedding

    with SessionLocal() as db:
        document = db.get(Document, doc_id)
        assert document.status == "indexed"
        assert document.summary_embedding is not None
        fact = db.query(DocumentFact).filter_by(document_id=doc_id).one()
        assert fact.embedding is not None and len(fact.embedding) == embeddings.EMBEDDING_DIM


def test_extraction_chains_embedding_on_needs_review(seeded_account, monkeypatch) -> None:
    # A low-confidence doc must still be embedded (searchable) while keeping its
    # review flag — the chain fires for needs_review too, not just extracted.
    account_id = seeded_account["personal_id"]
    with SessionLocal() as db:
        document = Document(
            account_id=account_id,
            source="web_upload",
            original_filename="mystery.pdf",
            mime_type=PDF_MIME,
            file_hash=uuid.uuid4().hex,
            storage_path="/dev/null",
            status="ocr_done",
            ocr_text="Some ambiguous text with no clear class.",
        )
        db.add(document)
        db.commit()
        doc_id = document.id

    # No class predicted -> routes to needs_review.
    canned = {
        "summary": "An ambiguous document.",
        "classes": [],
        "atomic_facts": [{"text": "The document is ambiguous.", "page": 1}],
    }
    monkeypatch.setattr(
        extraction, "call_extraction_model", lambda text, classes: (json.dumps(canned), "m")
    )
    monkeypatch.setattr(
        embeddings, "embed_passages",
        lambda texts: [[0.02] * embeddings.EMBEDDING_DIM for _ in texts],
    )

    extraction.run_extraction(doc_id, account_id)

    with SessionLocal() as db:
        document = db.get(Document, doc_id)
        assert document.status == "needs_review"  # flag preserved
        assert document.summary_embedding is not None  # but still embedded
        fact = db.query(DocumentFact).filter_by(document_id=doc_id).one()
        assert fact.embedding is not None
