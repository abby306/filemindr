"""Rating endpoint: persist feedback on an assistant answer, account-scoped.

`synthesize` is stubbed so we can produce a real assistant message to rate, then
exercise the rating writes, validation, and account isolation.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import AnswerRating
from app.db.session import SessionLocal
from app.main import app
from app.services.synthesis import SynthesisResult


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _headers(seeded_account, *, account="personal_id") -> dict:
    return {
        "Authorization": f"Bearer {seeded_account['user_id']}",
        "X-Account-Id": str(seeded_account[account]),
    }


@pytest.fixture
def answered(client, seeded_account, monkeypatch):
    """Create a conversation + one answered message; return (headers, message_id)."""
    monkeypatch.setattr(
        "app.services.synthesis.synthesize",
        lambda q, a, *, history=None, db=None, document_ids=None, **kw: SynthesisResult(
            query=q, answer="an answer", supported=True
        ),
    )
    headers = _headers(seeded_account)
    cid = client.post("/api/v1/conversations", headers=headers).json()["id"]
    mid = client.post(
        f"/api/v1/conversations/{cid}/messages", headers=headers, json={"content": "q"}
    ).json()["message_id"]
    return headers, mid


def test_rate_message_persists(answered) -> None:
    headers, mid = answered
    res = TestClient(app).post(
        f"/api/v1/messages/{mid}/rating",
        headers=headers,
        json={"rating": "down", "stars": 2, "reasons": ["wrong_number"], "comment": "off"},
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    with SessionLocal() as db:
        row = db.query(AnswerRating).filter_by(message_id=uuid.UUID(mid)).one()
        assert row.rating == "down"
        assert row.stars == 2
        assert row.reasons == ["wrong_number"]
        assert row.comment == "off"


def test_rate_message_minimal_thumbs_up(answered) -> None:
    headers, mid = answered
    res = TestClient(app).post(
        f"/api/v1/messages/{mid}/rating", headers=headers, json={"rating": "up"}
    )
    assert res.status_code == 200


def test_rate_unknown_message_404(client, seeded_account) -> None:
    res = client.post(
        f"/api/v1/messages/{uuid.uuid4()}/rating",
        headers=_headers(seeded_account),
        json={"rating": "up"},
    )
    assert res.status_code == 404


def test_rate_bad_rating_value_422(answered) -> None:
    headers, mid = answered
    res = TestClient(app).post(
        f"/api/v1/messages/{mid}/rating", headers=headers, json={"rating": "meh"}
    )
    assert res.status_code == 422


def test_rate_message_account_isolation(answered, seeded_account) -> None:
    _, mid = answered
    # The message lives in the personal account; the company scope must not see it.
    res = TestClient(app).post(
        f"/api/v1/messages/{mid}/rating",
        headers=_headers(seeded_account, account="company_id"),
        json={"rating": "up"},
    )
    assert res.status_code == 404
