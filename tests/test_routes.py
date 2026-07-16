"""Health probe and the auth + account-scoping gate on /api/v1/me."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_ok(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/me").status_code == 401


def test_me_rejects_bad_token(client: TestClient) -> None:
    res = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-uuid"})
    assert res.status_code == 401


def test_me_rejects_unknown_user(client: TestClient) -> None:
    res = client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {uuid.uuid4()}"}
    )
    assert res.status_code == 401


def test_me_multi_account_requires_header(client: TestClient, seeded_account) -> None:
    # The seeded user belongs to two accounts, so one must be named explicitly.
    res = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {seeded_account['user_id']}"},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "account_required"


def test_me_returns_active_account(client: TestClient, seeded_account) -> None:
    res = client.get(
        "/api/v1/me",
        headers={
            "Authorization": f"Bearer {seeded_account['user_id']}",
            "X-Account-Id": str(seeded_account["company_id"]),
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["account"]["id"] == str(seeded_account["company_id"])
    assert body["account"]["type"] == "company"


def test_me_rejects_non_member_account(client: TestClient, seeded_account) -> None:
    res = client.get(
        "/api/v1/me",
        headers={
            "Authorization": f"Bearer {seeded_account['user_id']}",
            "X-Account-Id": str(uuid.uuid4()),
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "not_a_member"
