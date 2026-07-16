"""Reranking: cross-encoder reorders candidates by query relevance.

The compute seam (`reranking._score`) is monkeypatched, so the suite never
downloads the cross-encoder. One live-DB test confirms `retrieve(rerank=True)`
applies the reranker over the fused candidates.
"""

from __future__ import annotations

import uuid

from app.db.models import DocumentFact
from app.db.session import SessionLocal
from app.services import reranking, retrieval
from app.services.retrieval import FactHit

DIM = 768


def _basis(i: int) -> list[float]:
    v = [0.0] * DIM
    v[i] = 1.0
    return v


def _hit(key: str, text: str) -> FactHit:
    return FactHit(key=key, text=text, document_id=uuid.uuid4(), source="vector")


def test_rerank_reorders_by_score(monkeypatch) -> None:
    # Score the second candidate highest → it must move to the front. (Fresh hits
    # carry no fused score, so the blended order follows the cross-encoder.)
    hits = [_hit("a", "generic intro"), _hit("b", "the exact answer"), _hit("c", "filler")]
    monkeypatch.setattr(reranking, "_score", lambda pairs: [0.1, 0.9, 0.2])

    out = reranking.rerank("the question", hits, top_k=3)

    assert [h.key for h in out] == ["b", "c", "a"]
    assert out[0].score >= out[1].score >= out[2].score


def test_rerank_respects_top_k(monkeypatch) -> None:
    hits = [_hit("a", "x"), _hit("b", "y"), _hit("c", "z")]
    monkeypatch.setattr(reranking, "_score", lambda pairs: [0.3, 0.8, 0.5])

    out = reranking.rerank("q", hits, top_k=2)

    assert [h.key for h in out] == ["b", "c"]


def test_rerank_empty_is_noop(monkeypatch) -> None:
    called = {"n": 0}
    monkeypatch.setattr(reranking, "_score", lambda pairs: called.__setitem__("n", 1) or [])
    assert reranking.rerank("q", [], top_k=5) == []
    assert called["n"] == 0  # never invokes the model on an empty list


def test_rerank_passes_query_fact_pairs(monkeypatch) -> None:
    captured: dict = {}

    def fake_score(pairs):
        captured["pairs"] = pairs
        return [1.0, 2.0]

    monkeypatch.setattr(reranking, "_score", fake_score)
    reranking.rerank("my query", [_hit("a", "fact one"), _hit("b", "fact two")], top_k=2)
    assert captured["pairs"] == [("my query", "fact one"), ("my query", "fact two")]


def test_retrieve_applies_reranker(seeded_account, monkeypatch) -> None:
    # Three facts at decreasing vector relevance. The reranker favours the
    # middle one; the blend (consensus-primary) lets it overtake the fused-top
    # fact without a runaway score — i.e. the reranker refines the order.
    import math
    account_id = seeded_account["personal_id"]
    monkeypatch.setattr(retrieval, "embed_query", lambda q: _basis(0))
    # Embedding 70% aligned with the query → ranks below the fully-aligned one.
    mid = [0.0] * DIM
    mid[0] = mid[1] = 1 / math.sqrt(2)
    with SessionLocal() as db:
        from app.db.models import Document
        doc = Document(
            account_id=account_id, source="web_upload", original_filename="d.pdf",
            mime_type="application/pdf", file_hash=uuid.uuid4().hex,
            storage_path="/dev/null", status="indexed", summary="doc",
            summary_embedding=_basis(0),
        )
        db.add(doc)
        db.flush()
        db.add_all([
            DocumentFact(account_id=account_id, document_id=doc.id,
                         text="generic top-ranked fact", page=1, embedding=_basis(0)),
            DocumentFact(account_id=account_id, document_id=doc.id,
                         text="the precise answer", page=2, embedding=mid),
            DocumentFact(account_id=account_id, document_id=doc.id,
                         text="irrelevant filler", page=3, embedding=_basis(7)),
        ])
        db.commit()

    monkeypatch.setattr(
        reranking, "_score",
        lambda pairs: [1.0 if "precise" in p else 0.05 for _, p in pairs],
    )

    no_rerank = retrieval.retrieve("xyzzy plugh", account_id, k=5, rerank=False)
    reranked = retrieval.retrieve("xyzzy plugh", account_id, k=5, rerank=True)

    assert no_rerank.facts[0].text == "generic top-ranked fact"  # pure fused order
    assert reranked.plan["reranked"] is True
    assert reranked.facts[0].text == "the precise answer"  # reranker promoted it
