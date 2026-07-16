"""Retrieval: intent routing, RRF fusion (pure), and a live-DB retrieve smoke.

`classify_intent` and `rrf_merge` are pure and tested directly. The end-to-end
`retrieve` runs against the live DB with hand-placed embeddings and a stubbed
`embed_query`, so vector ranking is deterministic and no model is downloaded.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.models import Document, DocumentFact, TypedFact
from app.db.session import SessionLocal
from app.services import retrieval
from app.services.retrieval import FactHit, classify_intent, rrf_merge

DIM = 768


def _basis(i: int) -> list[float]:
    """A unit basis vector with a 1 at position `i` (orthogonal for distinct i)."""
    v = [0.0] * DIM
    v[i] = 1.0
    return v


# --- intent routing (pure) -------------------------------------------------
@pytest.mark.parametrize(
    "query, expected",
    [
        ("How much did I spend at Blue Fern Cafe?", "aggregate"),
        ("What is the total amount due?", "aggregate"),
        ("How many invoices are there?", "aggregate"),
        ("What was the VAT on the receipt?", "aggregate"),  # vat/tax → amount lookup
        ("What is the invoice number on the receipt?", "lexical"),
        ('Which document mentions "SUPERVALUE, INC."?', "lexical"),
        ("Which document is issued by SUPERVALUE, INC.?", "lexical"),  # ALL-CAPS proper noun
        ("Find reference 104044328167", "lexical"),
        ("Who are the parties to the NDA?", "metadata"),
        ("When does the agreement expire?", "metadata"),
        ("What technology stack does the project plan use?", "semantic"),
        ("Tell me about the project", "semantic"),
    ],
)
def test_classify_intent(query, expected) -> None:
    assert classify_intent(query) == expected


# --- RRF fusion (pure) -----------------------------------------------------
def test_rrf_merge_orders_by_weighted_score() -> None:
    doc = uuid.uuid4()
    vec = [FactHit(key="a", text="a", document_id=doc, source="vector", fact_id=uuid.uuid4()),
           FactHit(key="b", text="b", document_id=doc, source="vector", fact_id=uuid.uuid4())]
    lex = [FactHit(key="b", text="b", document_id=doc, source="lexical", fact_id=uuid.uuid4())]

    merged = rrf_merge({"vector": vec, "lexical": lex},
                       weights={"vector": 1.0, "lexical": 1.0})

    # "b" appears in both lists → its summed score beats "a" (vector only).
    assert [h.key for h in merged] == ["b", "a"]
    assert merged[0].score > merged[1].score


def test_rrf_merge_zero_weight_source_excluded() -> None:
    doc = uuid.uuid4()
    hits = {"vector": [FactHit(key="a", text="a", document_id=doc, source="vector")],
            "structured": [FactHit(key="s", text="s", document_id=doc, source="structured")]}
    merged = rrf_merge(hits, weights={"vector": 1.0, "structured": 0.0})
    assert [h.key for h in merged] == ["a"]


def test_rrf_merge_prefers_citable_copy() -> None:
    doc, fid = uuid.uuid4(), uuid.uuid4()
    structured = [FactHit(key="x", text="x", document_id=doc, source="structured")]
    vector = [FactHit(key="x", text="x", document_id=doc, source="vector", fact_id=fid)]
    merged = rrf_merge({"structured": structured, "vector": vector},
                       weights={"structured": 1.0, "vector": 1.0})
    assert len(merged) == 1
    assert merged[0].fact_id == fid  # the copy with a citation target wins


# --- live-DB retrieve ------------------------------------------------------
def _seed_doc(account_id, *, summary_vec, facts, summary="A document."):
    """Create a document with a summary embedding and (text, vec, page) facts."""
    with SessionLocal() as db:
        doc = Document(
            account_id=account_id, source="web_upload", original_filename="d.pdf",
            mime_type="application/pdf", file_hash=uuid.uuid4().hex,
            storage_path="/dev/null", status="indexed", summary=summary,
            summary_embedding=summary_vec,
        )
        db.add(doc)
        db.flush()
        for text, vec, page in facts:
            db.add(DocumentFact(account_id=account_id, document_id=doc.id,
                                text=text, page=page, embedding=vec))
        db.commit()
        return doc.id


def test_retrieve_vector_ranks_aligned_fact_first(seeded_account, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    # Query aligns with basis(0); the matching fact shares it, the distractor is orthogonal.
    monkeypatch.setattr(retrieval, "embed_query", lambda q: _basis(0))
    doc_id = _seed_doc(
        account_id, summary_vec=_basis(0),
        facts=[("The subscription price is $20/month.", _basis(0), 2),
               ("Unrelated boilerplate text.", _basis(5), 1)],
    )

    result = retrieval.retrieve("what is the price", account_id, k=5, rerank=False)

    assert result.intent == "semantic"
    assert doc_id in result.doc_ids
    assert result.facts[0].text == "The subscription price is $20/month."
    assert result.facts[0].page == 2
    assert result.facts[0].fact_id is not None  # citable


def test_retrieve_lexical_finds_exact_identifier(seeded_account, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    # Vector points away so only FTS can surface the id-bearing fact.
    monkeypatch.setattr(retrieval, "embed_query", lambda q: _basis(9))
    _seed_doc(
        account_id, summary_vec=_basis(9),
        facts=[("The invoice number is 104044328167.", _basis(9), 1),
               ("Some other detail entirely.", _basis(9), 1)],
    )

    result = retrieval.retrieve("invoice number 104044328167", account_id, k=5, rerank=False)

    assert result.intent == "lexical"
    assert any("104044328167" in h.text for h in result.facts)


def test_retrieve_aggregate_surfaces_typed_fact(seeded_account, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    monkeypatch.setattr(retrieval, "embed_query", lambda q: _basis(0))
    doc_id = _seed_doc(
        account_id, summary_vec=_basis(0),
        facts=[("Receipt from Blue Fern Cafe.", _basis(0), 1)],
        summary="Blue Fern Cafe receipt",
    )
    with SessionLocal() as db:
        db.add(TypedFact(account_id=account_id, document_id=doc_id, label="total",
                         value="189.00", value_numeric=189.00, value_type="money",
                         unit="PHP", page=1))
        db.commit()

    result = retrieval.retrieve("how much did I spend at Blue Fern Cafe", account_id, k=5, rerank=False)

    assert result.intent == "aggregate"
    assert any(h.source == "structured" and "189" in h.text for h in result.facts)


def test_retrieve_lexical_matches_entity_name(seeded_account, monkeypatch) -> None:
    # An org named only in `entities` (never in an atomic fact) must still be found.
    from app.db.models import DocumentEntity, Entity
    account_id = seeded_account["personal_id"]
    monkeypatch.setattr(retrieval, "embed_query", lambda q: _basis(3))
    doc_id = _seed_doc(account_id, summary_vec=_basis(3),
                       facts=[("A receipt for groceries.", _basis(3), 1)],
                       summary="grocery receipt")
    with SessionLocal() as db:
        ent = Entity(account_id=account_id, name="SUPERVALUE, INC.",
                     normalized_name="supervalue, inc.", type="organization")
        db.add(ent)
        db.flush()
        db.add(DocumentEntity(account_id=account_id, document_id=doc_id, entity_id=ent.id))
        db.commit()

    result = retrieval.retrieve("Which document is issued by SUPERVALUE, INC.?",
                                account_id, k=5, rerank=False)

    assert result.intent == "lexical"
    assert doc_id in result.doc_ids
    assert any("SUPERVALUE, INC." in h.text for h in result.facts)


def test_retrieve_aggregate_prioritizes_named_label(seeded_account, monkeypatch) -> None:
    # "What was the VAT" must surface the vat_amount typed fact over generic totals.
    account_id = seeded_account["personal_id"]
    monkeypatch.setattr(retrieval, "embed_query", lambda q: _basis(0))
    doc_id = _seed_doc(account_id, summary_vec=_basis(0),
                       facts=[("A sales invoice.", _basis(0), 1)], summary="invoice")
    with SessionLocal() as db:
        db.add_all([
            TypedFact(account_id=account_id, document_id=doc_id, label="total",
                      value="189.00", value_numeric=189.00, value_type="money", unit="PHP"),
            TypedFact(account_id=account_id, document_id=doc_id, label="vat_amount",
                      value="20.25", value_numeric=20.25, value_type="money", unit="PHP"),
        ])
        db.commit()

    result = retrieval.retrieve("What was the VAT on the receipt?", account_id, k=5, rerank=False)

    assert result.intent == "aggregate"
    # The query names "vat" → the vat_amount fact ranks ahead of the generic total.
    texts = [h.text for h in result.facts]
    assert any("vat_amount" in t for t in texts)
    vat_i = next(i for i, t in enumerate(texts) if "vat_amount" in t)
    total_i = next((i for i, t in enumerate(texts) if t.startswith("total:")), len(texts))
    assert vat_i < total_i


def test_retrieve_scoped_to_document(seeded_account, monkeypatch) -> None:
    # document_ids restricts results to the named document only.
    account_id = seeded_account["personal_id"]
    monkeypatch.setattr(retrieval, "embed_query", lambda q: _basis(0))
    keep = _seed_doc(account_id, summary_vec=_basis(0),
                     facts=[("Fact in the target document.", _basis(0), 1)])
    _seed_doc(account_id, summary_vec=_basis(0),
              facts=[("Fact in another document.", _basis(0), 1)])

    result = retrieval.retrieve("fact", account_id, k=5, rerank=False, document_ids=[keep])

    assert result.facts  # found something
    assert {h.document_id for h in result.facts} == {keep}  # nothing from the other doc


def test_retrieve_is_account_scoped(seeded_account, monkeypatch) -> None:
    personal = seeded_account["personal_id"]
    company = seeded_account["company_id"]
    monkeypatch.setattr(retrieval, "embed_query", lambda q: _basis(0))
    _seed_doc(personal, summary_vec=_basis(0),
              facts=[("A personal-account secret fact.", _basis(0), 1)])

    result = retrieval.retrieve("secret fact", company, k=5, rerank=False)  # different account

    assert result.facts == []
    assert result.doc_ids == []
