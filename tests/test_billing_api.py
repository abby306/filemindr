"""Billing endpoints: plan catalog, implicit-free subscription, the mocked
Stripe-shaped checkout flow (session → complete → active plan + invoice),
upgrades, and account isolation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _auth(seeded_account, account_key: str = "personal_id") -> dict:
    return {
        "Authorization": f"Bearer {seeded_account['user_id']}",
        "X-Account-Id": str(seeded_account[account_key]),
    }


def _checkout_and_complete(client, headers, plan_slug: str) -> dict:
    """Drive the full mock flow; returns the final subscription payload."""
    session = client.post(
        "/api/v1/billing/checkout", headers=headers, json={"plan_slug": plan_slug}
    )
    assert session.status_code == 200
    body = session.json()
    assert body["session_id"] in body["checkout_url"]
    done = client.post(
        "/api/v1/billing/checkout/complete",
        headers=headers,
        json={"session_id": body["session_id"]},
    )
    assert done.status_code == 200
    return done.json()


def test_plans_catalog_cheapest_first(client, seeded_account) -> None:
    res = client.get("/api/v1/billing/plans", headers=_auth(seeded_account))
    assert res.status_code == 200
    plans = res.json()
    assert [p["slug"] for p in plans] == ["free", "pro", "team"]
    assert plans[0]["price_cents"] == 0
    assert "documents" in plans[0]["limits"]


def test_subscription_defaults_to_free(client, seeded_account) -> None:
    body = client.get("/api/v1/billing/subscription", headers=_auth(seeded_account)).json()
    assert body["plan"]["slug"] == "free"
    assert body["status"] == "active"
    assert body["period_end"] is None
    assert body["usage"] == {"documents": 0, "queries": 0, "storage_bytes": 0}
    assert body["limits"] == body["plan"]["limits"]


def test_checkout_unknown_plan_404(client, seeded_account) -> None:
    res = client.post(
        "/api/v1/billing/checkout",
        headers=_auth(seeded_account),
        json={"plan_slug": "platinum"},
    )
    assert res.status_code == 404


def test_checkout_free_plan_rejected(client, seeded_account) -> None:
    res = client.post(
        "/api/v1/billing/checkout",
        headers=_auth(seeded_account),
        json={"plan_slug": "free"},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "free_plan_checkout"


def test_complete_invalid_session_400(client, seeded_account) -> None:
    for bogus in ["nonsense", "cs_mock_platinum_deadbeef", "cs_mock_free_deadbeef"]:
        res = client.post(
            "/api/v1/billing/checkout/complete",
            headers=_auth(seeded_account),
            json={"session_id": bogus},
        )
        assert res.status_code == 400, bogus


def test_checkout_flow_activates_plan_and_invoices(client, seeded_account) -> None:
    headers = _auth(seeded_account)
    body = _checkout_and_complete(client, headers, "pro")
    assert body["plan"]["slug"] == "pro"
    assert body["status"] == "active"
    assert body["period_end"] is not None

    # The subscription persists and the paid invoice is on record.
    sub = client.get("/api/v1/billing/subscription", headers=headers).json()
    assert sub["plan"]["slug"] == "pro"
    invoices = client.get("/api/v1/billing/invoices", headers=headers).json()["items"]
    assert len(invoices) == 1
    assert (invoices[0]["amount_cents"], invoices[0]["status"]) == (1500, "paid")


def test_upgrade_replaces_active_subscription(client, seeded_account) -> None:
    headers = _auth(seeded_account)
    _checkout_and_complete(client, headers, "pro")
    body = _checkout_and_complete(client, headers, "team")
    assert body["plan"]["slug"] == "team"

    sub = client.get("/api/v1/billing/subscription", headers=headers).json()
    assert sub["plan"]["slug"] == "team"
    invoices = client.get("/api/v1/billing/invoices", headers=headers).json()["items"]
    assert len(invoices) == 2  # newest first: team (5000) then pro (1500)
    assert invoices[0]["amount_cents"] == 5000


def test_billing_is_account_scoped(client, seeded_account) -> None:
    """An upgrade on the personal account leaves the company account on free."""
    _checkout_and_complete(client, _auth(seeded_account), "pro")
    company = _auth(seeded_account, "company_id")
    assert (
        client.get("/api/v1/billing/subscription", headers=company).json()["plan"]["slug"]
        == "free"
    )
    assert client.get("/api/v1/billing/invoices", headers=company).json()["items"] == []


def test_billing_requires_auth(client) -> None:
    assert client.get("/api/v1/billing/plans").status_code == 401
    assert client.get("/api/v1/billing/subscription").status_code == 401
    assert client.get("/api/v1/billing/invoices").status_code == 401
