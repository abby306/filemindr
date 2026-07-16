"""Analytics endpoints: derived numbers match the seeded rows, empty accounts
degrade to zeros/nulls (not errors), and nothing leaks across accounts.

The seed writes straight to the observability tables (documents, traces,
ratings, processing events) with known values, so every asserted number is a
hand-computable fact about the seed — the same cross-check the Phase-7 eval
runs against the live corpus with SQL.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import (
    AnswerRating,
    Class,
    Conversation,
    Document,
    DocumentClass,
    Message,
    ProcessingEvent,
    RetrievalTrace,
)
from app.db.session import SessionLocal
from app.main import app

NOW = dt.datetime.now(dt.timezone.utc)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _auth(seeded_account, account_key: str = "personal_id") -> dict:
    return {
        "Authorization": f"Bearer {seeded_account['user_id']}",
        "X-Account-Id": str(seeded_account[account_key]),
    }


def _doc(account_id, *, byte_size: int, created_at: dt.datetime, title: str) -> Document:
    return Document(
        account_id=account_id,
        source="web_upload",
        original_filename=f"{title}.pdf",
        title=title,
        mime_type="application/pdf",
        byte_size=byte_size,
        file_hash=uuid.uuid4().hex,
        storage_path=f"/tmp/{uuid.uuid4().hex}",
        status="indexed",
        created_at=created_at,
    )


def _trace(
    session,
    account_id,
    *,
    created_at: dt.datetime,
    supported: bool,
    latency_ms: int,
    tokens: tuple[int, int],
    cited_doc_ids: list[uuid.UUID],
    rating: str | None = None,
) -> None:
    """One answered turn: conversation → message → trace (+ optional rating)."""
    convo = Conversation(account_id=account_id)
    session.add(convo)
    session.flush()
    message = Message(
        account_id=account_id, conversation_id=convo.id, role="assistant", content="a"
    )
    session.add(message)
    session.flush()
    session.add(
        RetrievalTrace(
            account_id=account_id,
            message_id=message.id,
            retrieval_plan={"supported": supported},
            citations=[
                {"document_id": str(d), "title": "t", "page": 1} for d in cited_doc_ids
            ],
            prompt_tokens=tokens[0],
            completion_tokens=tokens[1],
            latency_ms=latency_ms,
            created_at=created_at,
        )
    )
    if rating is not None:
        session.add(
            AnswerRating(account_id=account_id, message_id=message.id, rating=rating)
        )


@pytest.fixture
def seeded_analytics(seeded_account):
    """Known observability rows on the personal account; company stays empty."""
    session = SessionLocal()
    account_id = seeded_account["personal_id"]

    docs = [
        _doc(account_id, byte_size=100, created_at=NOW - dt.timedelta(days=40), title="old"),
        _doc(account_id, byte_size=200, created_at=NOW, title="alpha"),
        _doc(account_id, byte_size=300, created_at=NOW, title="beta"),
    ]
    session.add_all(docs)
    invoice_class = Class(account_id=account_id, slug="invoice-x", name="Invoice X")
    session.add(invoice_class)
    session.flush()
    for doc in docs[1:]:
        session.add(
            DocumentClass(
                account_id=account_id,
                document_id=doc.id,
                class_id=invoice_class.id,
                assigned_by="model",
                is_primary=True,
            )
        )

    # Two answered queries in range (one grounded, one not; alpha cited twice),
    # one out of range (must not count toward range-scoped numbers).
    _trace(
        session, account_id,
        created_at=NOW, supported=True, latency_ms=100, tokens=(10, 5),
        cited_doc_ids=[docs[1].id], rating="up",
    )
    _trace(
        session, account_id,
        created_at=NOW, supported=False, latency_ms=200, tokens=(20, 5),
        cited_doc_ids=[docs[1].id, docs[2].id], rating="down",
    )
    _trace(
        session, account_id,
        created_at=NOW - dt.timedelta(days=40), supported=True, latency_ms=1000,
        tokens=(100, 100), cited_doc_ids=[docs[2].id],
    )

    for status in ["succeeded", "succeeded", "succeeded", "failed"]:
        session.add(
            ProcessingEvent(
                account_id=account_id,
                document_id=docs[1].id,
                stage="extraction",
                status=status,
            )
        )
    session.commit()
    ids = {"alpha_id": docs[1].id, "beta_id": docs[2].id}
    try:
        yield {**seeded_account, **ids}
    finally:
        session.close()  # rows cascade with the seeded accounts


def test_usage_headline_numbers(client, seeded_analytics) -> None:
    body = client.get("/api/v1/analytics/usage", headers=_auth(seeded_analytics)).json()
    assert body["documents"] == 3  # archive total, range-independent
    assert body["storage_bytes"] == 600
    assert body["queries"] == 2  # the 40-day-old trace is outside 30d
    assert body["token_spend"] == 40  # (10+5) + (20+5)


def test_usage_series_zero_filled_and_cumulative(client, seeded_analytics) -> None:
    body = client.get(
        "/api/v1/analytics/usage",
        headers=_auth(seeded_analytics),
        params={"range": "7d"},
    ).json()
    docs = body["series"]["documents_over_time"]
    queries = body["series"]["queries_per_day"]
    assert len(docs) == 7 and len(queries) == 7
    assert docs[-1]["count"] == 2  # today's uploads
    assert docs[-1]["cumulative"] == 3  # seeded with the pre-range doc
    assert docs[0]["count"] == 0  # zero-filled quiet day
    assert queries[-1]["count"] == 2


def test_usage_top_classes_and_most_asked(client, seeded_analytics) -> None:
    body = client.get("/api/v1/analytics/usage", headers=_auth(seeded_analytics)).json()
    assert body["top_classes"] == [{"slug": "invoice-x", "name": "Invoice X", "count": 2}]
    most_asked = body["most_asked_documents"]
    assert most_asked[0]["document_id"] == str(seeded_analytics["alpha_id"])
    assert most_asked[0]["count"] == 2  # cited by both in-range traces
    assert most_asked[0]["title"] == "alpha"
    assert most_asked[1]["count"] == 1


def test_usage_bad_range_rejected(client, seeded_analytics) -> None:
    res = client.get(
        "/api/v1/analytics/usage",
        headers=_auth(seeded_analytics),
        params={"range": "365d"},
    )
    assert res.status_code == 422


def test_quality_numbers(client, seeded_analytics) -> None:
    body = client.get("/api/v1/analytics/quality", headers=_auth(seeded_analytics)).json()
    assert body["answer_rating_pct"] == 50.0  # 1 up of 2
    assert body["grounded_pct"] == pytest.approx(66.7)  # 2 supported of 3 (all-time)
    assert body["avg_retrieval_ms"] == 433  # (100+200+1000)/3
    assert body["extraction_success_pct"] == 75.0
    assert body["ratings_count"] == 2
    assert body["answers_count"] == 3


def test_empty_account_returns_zeros_not_errors(client, seeded_analytics) -> None:
    headers = _auth(seeded_analytics, "company_id")
    usage_body = client.get("/api/v1/analytics/usage", headers=headers).json()
    assert usage_body["documents"] == 0
    assert usage_body["token_spend"] == 0
    assert usage_body["top_classes"] == []
    assert usage_body["most_asked_documents"] == []
    assert all(p["count"] == 0 for p in usage_body["series"]["queries_per_day"])

    quality = client.get("/api/v1/analytics/quality", headers=headers).json()
    assert quality["answer_rating_pct"] is None
    assert quality["grounded_pct"] is None
    assert quality["avg_retrieval_ms"] is None
    assert quality["extraction_success_pct"] is None


def test_analytics_requires_auth(client) -> None:
    assert client.get("/api/v1/analytics/usage").status_code == 401
    assert client.get("/api/v1/analytics/quality").status_code == 401
