"""Extraction: lenient parsing, card fan-out, scoping, and review routing.

The LLM call (`extraction.call_extraction_model`) is monkeypatched with a canned
response, so the whole suite runs offline and deterministically. Fan-out tests
use a real document committed under a `seeded_account`; the account's cascade
delete tidies up the card rows on teardown.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import uuid

import pytest
from fastapi.testclient import TestClient

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
from app.db.session import SessionLocal
from app.main import app
from app.services import embeddings, extraction, ocr

# --- canned model output ---------------------------------------------------
CANNED = {
    "title": "Acme Invoice #42",
    "summary": "An invoice from Acme Inc for 1240 USD, due 2025-04-01.",
    "classes": [
        {"slug": "invoice", "confidence": 0.96},
        {"slug": "made_up_slug", "confidence": 0.9},  # not in catalog -> skipped
    ],
    "entities": {
        "people": ["Jane Doe"],
        "organizations": ["Acme Inc", "acme inc"],  # dedup case-insensitively
        "places": ["Berlin"],
    },
    "dates": [
        {"value": "2025-04-01", "raw_text": "April 1, 2025", "role": "due"},
        {"value": "not-a-date", "role": "bogus"},  # -> null value, role mentioned
    ],
    "typed_facts": [
        {
            "label": "invoice_total",
            "value": "1240",
            "value_numeric": 1240,
            "value_type": "money",
            "unit": "USD",
            "page": 1,
        }
    ],
    "atomic_facts": [
        {"text": "The invoice total is 1240 USD.", "page": 1},
        {"text": "   ", "page": 1},  # blank -> skipped
    ],
}


@pytest.fixture(autouse=True)
def tmp_storage(monkeypatch, tmp_path):
    """Keep OCR-cache lookups off real storage and the chained embedding offline.

    Extraction chains into embedding for confident docs; stubbing `embed_passages`
    keeps that fast/deterministic and avoids loading the bge model in extraction
    tests (the embedding behaviour itself is covered in test_embeddings.py).
    """
    monkeypatch.setattr(ocr, "get_storage_root", lambda: tmp_path)
    monkeypatch.setattr(
        embeddings, "embed_passages",
        lambda texts: [[0.0] * embeddings.EMBEDDING_DIM for _ in texts],
    )


@pytest.fixture
def canned_model(monkeypatch):
    """Replace the network call with a canned JSON response."""

    def _fake(ocr_text, classes):
        return json.dumps(CANNED), "deepseek-chat-test"

    monkeypatch.setattr(extraction, "call_extraction_model", _fake)


def _make_document(
    account_id: uuid.UUID,
    *,
    status: str = "ocr_done",
    page_texts: list[str] | None = None,
) -> uuid.UUID:
    """Commit a document (+ an `invoice` class) for the account; return its id.

    When `page_texts` is given, a matching multi-page OCR-cache artifact is saved
    so `run_extraction` exercises the page-window chunking path.
    """
    with SessionLocal() as db:
        db.add(
            Class(account_id=account_id, slug="invoice", name="Invoice", is_system=True)
        )
        file_hash = uuid.uuid4().hex
        document = Document(
            account_id=account_id,
            source="web_upload",
            original_filename="invoice.pdf",
            mime_type=ocr.PDF_MIME,
            file_hash=file_hash,
            storage_path="/dev/null",
            status=status,
            ocr_text="Acme Inc invoice total 1240 USD due 2025-04-01. Jane Doe, Berlin.",
        )
        db.add(document)
        db.commit()
        doc_id = document.id

    if page_texts is not None:
        result = ocr.OcrResult(
            engine="pdf_text_layer",
            page_count=len(page_texts),
            language="en",
            text="\n\n".join(page_texts),
            pages=[ocr.OcrPage(page=i, text=t) for i, t in enumerate(page_texts, start=1)],
        )
        ocr.save_cached_ocr(file_hash, result)
    return doc_id


# --- pure parsing ----------------------------------------------------------
def test_parse_extraction_valid() -> None:
    result = extraction.parse_extraction(json.dumps(CANNED))
    assert result.title == "Acme Invoice #42"
    assert result.classes[0].slug == "invoice"
    assert result.typed_facts[0].value_numeric == 1240.0


def test_parse_extraction_is_lenient() -> None:
    result = extraction.parse_extraction(json.dumps(CANNED))
    # Invalid date string and role both degrade to safe defaults.
    bad_date = result.dates[1]
    assert bad_date.value is None
    assert bad_date.role == "mentioned"


def test_parse_extraction_coerces_and_clamps() -> None:
    raw = json.dumps(
        {
            "classes": [{"slug": "x", "confidence": 1.7}],
            "typed_facts": [
                {"label": "amt", "value": 99, "value_numeric": "nope", "value_type": "weird"}
            ],
        }
    )
    result = extraction.parse_extraction(raw)
    assert result.classes[0].confidence == 1.0  # clamped to [0, 1]
    fact = result.typed_facts[0]
    assert fact.value == "99"  # stringified
    assert fact.value_numeric is None  # uncoercible -> null
    assert fact.value_type == "string"  # invalid enum -> default


def test_parse_extraction_strips_code_fences() -> None:
    fenced = "```json\n" + json.dumps({"title": "T"}) + "\n```"
    assert extraction.parse_extraction(fenced).title == "T"


def test_parse_extraction_coerces_entity_objects() -> None:
    # DeepSeek sometimes returns entities as {"name": ...} objects, not strings.
    raw = json.dumps(
        {
            "entities": {
                "people": [{"name": "Daine Genevie Sebastian"}, "Plain Name", {"x": 1}, ""],
                "organizations": [{"name": "South Supermarket"}],
                "places": "Sta Rosa, Laguna",  # not even a list
            }
        }
    )
    result = extraction.parse_extraction(raw)
    assert result.entities.people == ["Daine Genevie Sebastian", "Plain Name"]  # object→name, junk dropped
    assert result.entities.organizations == ["South Supermarket"]
    assert result.entities.places == ["Sta Rosa, Laguna"]  # scalar wrapped into a list


def test_bbox_for_fact_matches_native_pdf_blocks() -> None:
    # A text-layer PDF now carries block bboxes (4-vertex polygons); the matcher
    # attaches one to a fact that overlaps a block, and nothing to an unrelated one.
    box = [[0, 0], [100, 0], [100, 20], [0, 20]]
    cached = ocr.OcrResult(
        engine=ocr.ENGINE_PDF_TEXT, page_count=1, language="en",
        text="Invoice total 1240 USD due 2025-04-01.",
        pages=[
            ocr.OcrPage(
                page=1,
                text="Invoice total 1240 USD due 2025-04-01.",
                blocks=[ocr.OcrBlock(text="Invoice total 1240 USD due 2025-04-01.", bbox=box)],
            )
        ],
    )
    hit = extraction._bbox_for_fact(cached, 1, "The invoice total is 1240 USD.")
    assert hit == {"page": 1, "bbox": box}
    assert extraction._bbox_for_fact(cached, 1, "completely unrelated content here") is None


# --- fan-out (live DB) -----------------------------------------------------
def test_run_extraction_writes_card(seeded_account, canned_model) -> None:
    account_id = seeded_account["personal_id"]
    doc_id = _make_document(account_id)

    extraction.run_extraction(doc_id, account_id)

    with SessionLocal() as db:
        document = db.get(Document, doc_id)
        assert document.status == "indexed"  # extraction chained into embedding
        assert document.title == "Acme Invoice #42"
        assert document.summary.startswith("An invoice")
        assert document.extraction_model == "deepseek-chat-test"
        assert document.extraction_raw["chunk_count"] == 1
        assert document.extraction_raw["chunks"][0]["classes"][0]["slug"] == "invoice"

        classes = db.query(DocumentClass).filter_by(document_id=doc_id).all()
        assert len(classes) == 1  # made_up_slug dropped
        assert classes[0].is_primary  # the sole valid class is the primary

        entities = (
            db.query(DocumentEntity, Entity)
            .join(Entity, Entity.id == DocumentEntity.entity_id)
            .filter(DocumentEntity.document_id == doc_id)
            .all()
        )
        names = {e.name for _, e in entities}
        assert names == {"Jane Doe", "Acme Inc", "Berlin"}  # org deduped

        dates = db.query(DocumentDate).filter_by(document_id=doc_id).all()
        assert len(dates) == 2
        assert any(d.role == "due" and str(d.value) == "2025-04-01" for d in dates)

        facts = db.query(TypedFact).filter_by(document_id=doc_id).all()
        assert len(facts) == 1 and float(facts[0].value_numeric) == 1240.0

        atomic = db.query(DocumentFact).filter_by(document_id=doc_id).all()
        assert len(atomic) == 1  # blank fact skipped
        assert atomic[0].embedding is not None  # chained embedding populated it


def test_run_extraction_is_idempotent(seeded_account, canned_model) -> None:
    account_id = seeded_account["personal_id"]
    doc_id = _make_document(account_id)

    extraction.run_extraction(doc_id, account_id)
    extraction.run_extraction(doc_id, account_id)  # re-run clears + rewrites

    with SessionLocal() as db:
        assert db.query(DocumentClass).filter_by(document_id=doc_id).count() == 1
        assert db.query(DocumentFact).filter_by(document_id=doc_id).count() == 1


def test_low_confidence_routes_to_needs_review(seeded_account, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    doc_id = _make_document(account_id)
    low = {**CANNED, "classes": [{"slug": "invoice", "confidence": 0.2}]}
    monkeypatch.setattr(
        extraction, "call_extraction_model", lambda t, c: (json.dumps(low), "m")
    )

    extraction.run_extraction(doc_id, account_id)

    with SessionLocal() as db:
        assert db.get(Document, doc_id).status == "needs_review"


def test_write_card_marks_highest_confidence_class_primary(seeded_account, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    doc_id = _make_document(account_id)  # seeds the `invoice` class
    with SessionLocal() as db:  # add a second catalog class so both labels are valid
        db.add(Class(account_id=account_id, slug="report", name="Report", is_system=True))
        db.commit()
    payload = {
        **CANNED,
        "classes": [
            {"slug": "invoice", "confidence": 0.55},
            {"slug": "report", "confidence": 0.91},  # higher → primary
        ],
    }
    monkeypatch.setattr(
        extraction, "call_extraction_model", lambda t, c: (json.dumps(payload), "m")
    )

    extraction.run_extraction(doc_id, account_id)

    with SessionLocal() as db:
        rows = db.query(DocumentClass).filter_by(document_id=doc_id).all()
        primary = [r for r in rows if r.is_primary]
        assert len(rows) == 2
        assert len(primary) == 1
        assert primary[0].confidence == pytest.approx(0.91)


def test_run_extraction_never_crosses_account(seeded_account, canned_model) -> None:
    # A document owned by the personal account is untouched when run under the
    # company account scope.
    personal = seeded_account["personal_id"]
    company = seeded_account["company_id"]
    doc_id = _make_document(personal)

    extraction.run_extraction(doc_id, company)  # wrong account — no-op

    with SessionLocal() as db:
        assert db.get(Document, doc_id).status == "ocr_done"
        assert db.query(DocumentClass).filter_by(document_id=doc_id).count() == 0


def test_get_document_returns_card(seeded_account, canned_model) -> None:
    account_id = seeded_account["personal_id"]
    doc_id = _make_document(account_id)
    extraction.run_extraction(doc_id, account_id)

    client = TestClient(app)
    headers = {
        "Authorization": f"Bearer {seeded_account['user_id']}",
        "X-Account-Id": str(account_id),
    }
    card = client.get(f"/api/v1/documents/{doc_id}", headers=headers).json()

    assert card["status"] == "indexed"  # extraction chained into embedding
    assert card["classes"][0]["slug"] == "invoice"
    assert card["classes"][0]["name"] == "Invoice"
    assert "Acme Inc" in card["entities"]["organizations"]
    assert card["typed_facts"][0]["type"] == "money"
    assert card["typed_facts"][0]["value_numeric"] == 1240.0
    assert card["fact_count"] == 1


# --- page-window chunking (pure) -------------------------------------------
def test_chunk_pages_single_chunk_when_small() -> None:
    pages = [ocr.OcrPage(page=1, text="hello"), ocr.OcrPage(page=2, text="world")]
    chunks = extraction.chunk_pages(pages, budget=10_000)
    assert len(chunks) == 1
    assert (chunks[0].start_page, chunks[0].end_page) == (1, 2)
    assert "PAGE 1" in chunks[0].text and "PAGE 2" in chunks[0].text


def test_chunk_pages_splits_contiguously_without_splitting_a_page() -> None:
    pages = [ocr.OcrPage(page=i, text="word " * 60) for i in range(1, 7)]
    chunks = extraction.chunk_pages(pages, budget=300)
    assert len(chunks) > 1
    assert chunks[0].start_page == 1 and chunks[-1].end_page == 6
    # Contiguous, every page in exactly one chunk (no gaps, no splits).
    prev = 0
    for c in chunks:
        assert c.start_page == prev + 1
        prev = c.end_page


# --- card merge (pure) -----------------------------------------------------
def test_merge_results_unions_and_dedups() -> None:
    r1 = extraction.ExtractionResult(
        title="Doc",
        summary="first",
        classes=[extraction.ClassPrediction(slug="report", confidence=0.6)],
        entities=extraction.EntityGroups(organizations=["Acme"]),
        dates=[extraction.DatePrediction(value=dt.date(2025, 1, 1), role="issued")],
        typed_facts=[extraction.TypedFactPrediction(label="total", value="5", page=1)],
        atomic_facts=[extraction.AtomicFactPrediction(text="Fact A", page=1)],
    )
    r2 = extraction.ExtractionResult(
        title=None,
        summary="second",
        classes=[
            extraction.ClassPrediction(slug="report", confidence=0.9),
            extraction.ClassPrediction(slug="invoice", confidence=0.4),
        ],
        entities=extraction.EntityGroups(organizations=["acme", "Globex"]),
        dates=[extraction.DatePrediction(value=dt.date(2025, 1, 1), role="issued")],  # dup
        typed_facts=[extraction.TypedFactPrediction(label="total", value="5", page=2)],
        atomic_facts=[
            extraction.AtomicFactPrediction(text="fact a", page=2),  # case-dup of Fact A
            extraction.AtomicFactPrediction(text="Fact B", page=2),
        ],
    )
    merged = extraction.merge_results([r1, r2])

    assert merged.title == "Doc"  # first non-empty wins
    assert merged.summary == "first"
    assert {c.slug for c in merged.classes} == {"report", "invoice"}
    assert next(c for c in merged.classes if c.slug == "report").confidence == 0.9
    assert merged.entities.organizations == ["Acme", "Globex"]  # acme deduped
    assert len(merged.dates) == 1  # duplicate date removed
    assert len(merged.typed_facts) == 2  # same label, different page -> both kept
    assert [f.text for f in merged.atomic_facts] == ["Fact A", "Fact B"]


def test_merge_results_passthrough_single() -> None:
    only = extraction.ExtractionResult(title="X")
    assert extraction.merge_results([only]) is only


# --- multi-chunk run (live DB, mocked LLM) ---------------------------------
def test_run_extraction_covers_all_pages_via_chunks(seeded_account, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    # Force every page into its own chunk so we prove all pages are extracted.
    monkeypatch.setattr(extraction, "_CHUNK_CHAR_BUDGET", 50)
    page_texts = [f"Page {i} body " + "filler " * 20 for i in range(1, 4)]
    doc_id = _make_document(account_id, page_texts=page_texts)

    calls = {"n": 0}

    def fake(text, classes):
        calls["n"] += 1
        pages = [int(n) for n in re.findall(r"PAGE (\d+)", text)]
        payload = {
            "classes": [{"slug": "invoice", "confidence": 0.9}],
            "atomic_facts": [{"text": f"Fact on page {p}", "page": p} for p in pages],
        }
        return json.dumps(payload), "chunked-model"

    monkeypatch.setattr(extraction, "call_extraction_model", fake)

    extraction.run_extraction(doc_id, account_id)

    assert calls["n"] == 3  # one LLM call per page-chunk
    with SessionLocal() as db:
        document = db.get(Document, doc_id)
        assert document.status == "indexed"  # extraction chained into embedding
        assert document.extraction_raw["chunk_count"] == 3
        facts = db.query(DocumentFact).filter_by(document_id=doc_id).all()
        assert {f.page for f in facts} == {1, 2, 3}  # every page covered


def test_run_extraction_merges_in_chunk_order(seeded_account, monkeypatch) -> None:
    # Even when chunks are extracted in parallel, the merged title/summary must
    # come from the earliest chunk (results stay in chunk order).
    account_id = seeded_account["personal_id"]
    monkeypatch.setattr(extraction, "_CHUNK_CHAR_BUDGET", 50)
    page_texts = [f"Page {i} body " + "filler " * 20 for i in range(1, 4)]
    doc_id = _make_document(account_id, page_texts=page_texts)

    def per_page(text, classes):
        page = int(re.search(r"PAGE (\d+)", text).group(1))
        payload = {
            "title": f"Title from page {page}",
            "summary": f"Summary from page {page}",
            "classes": [{"slug": "invoice", "confidence": 0.9}],
            "atomic_facts": [{"text": f"Fact on page {page}", "page": page}],
        }
        return json.dumps(payload), "m"

    monkeypatch.setattr(extraction, "call_extraction_model", per_page)

    extraction.run_extraction(doc_id, account_id)

    with SessionLocal() as db:
        document = db.get(Document, doc_id)
        assert document.title == "Title from page 1"  # earliest chunk wins
        assert document.summary == "Summary from page 1"


def test_run_extraction_tolerates_a_failed_chunk(seeded_account, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    monkeypatch.setattr(extraction, "_CHUNK_CHAR_BUDGET", 50)
    page_texts = [f"Page {i} body " + "filler " * 20 for i in range(1, 4)]
    doc_id = _make_document(account_id, page_texts=page_texts)

    def flaky(text, classes):
        if "PAGE 2" in text:  # the middle chunk persistently fails
            raise ValueError("chunk 2 is down")
        pages = [int(n) for n in re.findall(r"PAGE (\d+)", text)]
        payload = {
            "classes": [{"slug": "invoice", "confidence": 0.9}],
            "atomic_facts": [{"text": f"Fact on page {p}", "page": p} for p in pages],
        }
        return json.dumps(payload), "m"

    monkeypatch.setattr(extraction, "call_extraction_model", flaky)

    extraction.run_extraction(doc_id, account_id)

    with SessionLocal() as db:
        document = db.get(Document, doc_id)
        assert document.status == "indexed"  # partial success still completes
        failed = document.extraction_raw["failed_chunks"]
        assert len(failed) == 1 and failed[0]["pages"] == [2, 2]
        pages = {f.page for f in db.query(DocumentFact).filter_by(document_id=doc_id).all()}
        assert pages == {1, 3}  # page 2's chunk was skipped


def test_run_extraction_fails_when_all_chunks_fail(seeded_account, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    doc_id = _make_document(account_id)  # no cache -> single chunk over ocr_text

    def always_fail(text, classes):
        raise ValueError("model down")

    monkeypatch.setattr(extraction, "call_extraction_model", always_fail)

    extraction.run_extraction(doc_id, account_id)

    with SessionLocal() as db:
        assert db.get(Document, doc_id).status == "failed"
