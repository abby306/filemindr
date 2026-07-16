"""Usage metering + plan-quota enforcement (Phase 7).

Unit tests exercise the service against the live DB (rolled back); route tests
prove the write paths meter and enforce (402 + upgrade hint) end-to-end. Plans
with tiny limits are injected by stubbing `usage.get_plan`, so no test touches
the seeded global `plans` rows.
"""

from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import (
    Document,
    Plan,
    Subscription,
    UsageCounter,
    UsageEvent,
)
from app.db.session import SessionLocal
from app.main import app
from app.services import ocr, storage, usage


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def tmp_storage(monkeypatch, tmp_path):
    """Offline upload path: tmp storage; the OCR chain is irrelevant here, so the
    background task is a no-op (keeps PNG uploads away from Vision). Quota
    enforcement (off by default for self-hosting) is switched on so the
    enforcement paths are what's under test."""
    monkeypatch.setattr(storage, "get_storage_root", lambda: tmp_path)
    monkeypatch.setattr(ocr, "get_storage_root", lambda: tmp_path)
    monkeypatch.setattr(ocr, "run_ocr", lambda *args, **kwargs: None)
    monkeypatch.setattr(usage, "_quotas_enabled", lambda: True)


def _auth(seeded_account, account_key: str = "personal_id") -> dict:
    return {
        "Authorization": f"Bearer {seeded_account['user_id']}",
        "X-Account-Id": str(seeded_account[account_key]),
    }


def _upload(client, headers, content: bytes, name: str = "doc.png"):
    return client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (name, io.BytesIO(content), "image/png")},
    )


def _png_bytes(seed: str) -> bytes:
    """Unique bytes per seed so dedup doesn't collapse test uploads."""
    return b"\x89PNG\r\n\x1a\n" + seed.encode() + b"\x00" * 32


def _plan(**limits) -> Plan:
    """A detached Plan with the given limits (unlisted keys default to None)."""
    full = {"documents": None, "storage_gb": None, "queries_per_month": None, **limits}
    return Plan(slug="test", name="Test", price_cents=0, currency="USD", limits=full)


# --- unit: metering ---------------------------------------------------------


def test_record_usage_appends_event_and_upserts_counter(seeded_account, db) -> None:
    account_id = seeded_account["personal_id"]
    usage.record_usage(
        db, account_id, type=usage.EVENT_DOCUMENT_UPLOADED, documents=1, storage_bytes=100
    )
    usage.record_usage(db, account_id, type=usage.EVENT_QUERY_ASKED, queries=1)
    db.flush()

    events = db.scalars(
        select(UsageEvent).where(UsageEvent.account_id == account_id)
    ).all()
    assert sorted(e.type for e in events) == [
        usage.EVENT_DOCUMENT_UPLOADED,
        usage.EVENT_QUERY_ASKED,
    ]
    counter = db.scalar(
        select(UsageCounter).where(
            UsageCounter.account_id == account_id,
            UsageCounter.period == usage.current_period(),
        )
    )
    assert (counter.documents, counter.queries, counter.storage_bytes) == (1, 1, 100)


def test_record_usage_increments_existing_counter(seeded_account, db) -> None:
    account_id = seeded_account["personal_id"]
    for _ in range(3):
        usage.record_usage(db, account_id, type=usage.EVENT_QUERY_ASKED, queries=1)
    db.flush()
    counter = db.scalar(
        select(UsageCounter).where(UsageCounter.account_id == account_id)
    )
    assert counter.queries == 3


def test_current_period_is_utc_year_month() -> None:
    import datetime as dt

    moment = dt.datetime(2026, 7, 16, tzinfo=dt.timezone.utc)
    assert usage.current_period(moment) == "2026-07"


# --- unit: plan resolution & quota ------------------------------------------


def test_get_plan_defaults_to_free(seeded_account, db) -> None:
    plan = usage.get_plan(db, seeded_account["personal_id"])
    assert plan.slug == "free"


def test_get_plan_uses_active_subscription(seeded_account, db) -> None:
    account_id = seeded_account["personal_id"]
    db.add(Subscription(account_id=account_id, plan_slug="pro", status="active"))
    db.flush()
    assert usage.get_plan(db, account_id).slug == "pro"


def test_get_plan_ignores_canceled_subscription(seeded_account, db) -> None:
    account_id = seeded_account["personal_id"]
    db.add(Subscription(account_id=account_id, plan_slug="pro", status="canceled"))
    db.flush()
    assert usage.get_plan(db, account_id).slug == "free"


def test_document_quota_blocks_at_limit(seeded_account, db, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    db.add(
        Document(
            account_id=account_id,
            source="web_upload",
            original_filename="a.pdf",
            mime_type="application/pdf",
            byte_size=10,
            file_hash=uuid.uuid4().hex,
            storage_path="/tmp/x",
            status="received",
        )
    )
    db.flush()
    monkeypatch.setattr(usage, "get_plan", lambda *_: _plan(documents=1))
    with pytest.raises(usage.QuotaExceededError) as exc:
        usage.check_document_quota(db, account_id)
    assert exc.value.kind == "documents"
    assert (exc.value.current, exc.value.limit) == (1, 1)


def test_storage_quota_counts_incoming_bytes(seeded_account, db, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    monkeypatch.setattr(usage, "get_plan", lambda *_: _plan(storage_gb=1))
    # Empty account: a 1 GB - 1 byte file fits; one byte more does not.
    usage.check_document_quota(db, account_id, incoming_bytes=1024**3 - 1)
    with pytest.raises(usage.QuotaExceededError) as exc:
        usage.check_document_quota(db, account_id, incoming_bytes=1024**3 + 1)
    assert exc.value.kind == "storage"


def test_query_quota_reads_monthly_counter(seeded_account, db, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    monkeypatch.setattr(usage, "get_plan", lambda *_: _plan(queries_per_month=2))
    usage.check_query_quota(db, account_id)  # 0 used — fine
    usage.record_usage(db, account_id, type=usage.EVENT_QUERY_ASKED, queries=2)
    db.flush()
    with pytest.raises(usage.QuotaExceededError) as exc:
        usage.check_query_quota(db, account_id)
    assert exc.value.kind == "queries"


def test_null_limits_are_unlimited(seeded_account, db, monkeypatch) -> None:
    account_id = seeded_account["personal_id"]
    monkeypatch.setattr(usage, "get_plan", lambda *_: _plan())
    usage.record_usage(db, account_id, type=usage.EVENT_QUERY_ASKED, queries=10_000)
    db.flush()
    usage.check_document_quota(db, account_id, incoming_bytes=10 * 1024**3)
    usage.check_query_quota(db, account_id)  # neither raises


def test_quotas_disabled_by_default(seeded_account, db, monkeypatch) -> None:
    """With ENFORCE_QUOTAS off (the self-hosting default), even a zero-limit
    plan never blocks a write."""
    monkeypatch.setattr(usage, "_quotas_enabled", lambda: False)
    monkeypatch.setattr(usage, "get_plan", lambda *_: _plan(documents=0, queries_per_month=0))
    usage.check_document_quota(db, seeded_account["personal_id"], incoming_bytes=10)
    usage.check_query_quota(db, seeded_account["personal_id"])  # neither raises


def test_quota_detail_has_contract_shape() -> None:
    exc = usage.QuotaExceededError(kind="queries", limit=50, current=50, plan=_plan())
    detail = usage.quota_http_detail(exc)
    assert detail["code"] == "quota_exceeded"
    assert "Upgrade" in detail["message"]
    assert detail["upgrade_hint"] == "/billing"
    assert (detail["kind"], detail["limit"], detail["current"]) == ("queries", 50, 50)


# --- routes: metering + enforcement on the write paths -----------------------


def test_upload_meters_documents_and_storage(client, seeded_account) -> None:
    headers = _auth(seeded_account)
    content = _png_bytes("meter-me")
    res = _upload(client, headers, content)
    assert res.status_code == 201

    session = SessionLocal()
    try:
        account_id = seeded_account["personal_id"]
        event = session.scalar(
            select(UsageEvent).where(
                UsageEvent.account_id == account_id,
                UsageEvent.type == usage.EVENT_DOCUMENT_UPLOADED,
            )
        )
        assert event is not None
        assert event.meta["byte_size"] == len(content)
        counter = session.scalar(
            select(UsageCounter).where(UsageCounter.account_id == account_id)
        )
        assert (counter.documents, counter.storage_bytes) == (1, len(content))
    finally:
        session.close()


def test_dedup_upload_is_not_metered_twice(client, seeded_account) -> None:
    headers = _auth(seeded_account)
    content = _png_bytes("dedup-once")
    assert _upload(client, headers, content).status_code == 201
    assert _upload(client, headers, content).status_code == 200

    session = SessionLocal()
    try:
        counter = session.scalar(
            select(UsageCounter).where(
                UsageCounter.account_id == seeded_account["personal_id"]
            )
        )
        assert counter.documents == 1
    finally:
        session.close()


def test_upload_over_document_limit_returns_402(client, seeded_account, monkeypatch) -> None:
    monkeypatch.setattr(usage, "get_plan", lambda *_: _plan(documents=1))
    headers = _auth(seeded_account)
    assert _upload(client, headers, _png_bytes("first")).status_code == 201
    res = _upload(client, headers, _png_bytes("second"))
    assert res.status_code == 402
    detail = res.json()["detail"]
    assert detail["code"] == "quota_exceeded"
    assert detail["kind"] == "documents"
    assert detail["upgrade_hint"] == "/billing"

    session = SessionLocal()
    try:  # the rejected upload left no document and no metering
        docs = session.scalars(
            select(Document).where(
                Document.account_id == seeded_account["personal_id"]
            )
        ).all()
        assert len(docs) == 1
        counter = session.scalar(
            select(UsageCounter).where(
                UsageCounter.account_id == seeded_account["personal_id"]
            )
        )
        assert counter.documents == 1
    finally:
        session.close()


def test_message_over_query_limit_returns_402(client, seeded_account, monkeypatch) -> None:
    monkeypatch.setattr(usage, "get_plan", lambda *_: _plan(queries_per_month=0))
    headers = _auth(seeded_account)
    convo = client.post("/api/v1/conversations", headers=headers)
    assert convo.status_code == 201
    res = client.post(
        f"/api/v1/conversations/{convo.json()['id']}/messages",
        headers=headers,
        json={"content": "What is my invoice total?"},
    )
    assert res.status_code == 402
    assert res.json()["detail"]["kind"] == "queries"


def test_chat_meters_one_query(seeded_account, monkeypatch) -> None:
    """A chat turn writes a query usage event + bumps the monthly counter,
    in the same transaction as the messages/trace."""
    from app.services import conversations
    from app.services.synthesis import SynthesisResult

    account_id = seeded_account["personal_id"]

    def fake_synthesize(query, acct, *, history=None, db=None, **kw):
        return SynthesisResult(
            query=query, answer="ok", supported=True, prompt_tokens=7, completion_tokens=3
        )

    monkeypatch.setattr("app.services.synthesis.synthesize", fake_synthesize)
    _, _, message_id = conversations.chat(
        account_id, "what?", user_id=seeded_account["user_id"]
    )

    session = SessionLocal()
    try:
        event = session.scalar(
            select(UsageEvent).where(
                UsageEvent.account_id == account_id,
                UsageEvent.type == usage.EVENT_QUERY_ASKED,
            )
        )
        assert event is not None
        assert event.meta["message_id"] == str(message_id)
        assert event.meta["tokens"] == 10
        counter = session.scalar(
            select(UsageCounter).where(UsageCounter.account_id == account_id)
        )
        assert counter.queries == 1
    finally:
        session.close()


def test_metering_is_account_scoped(client, seeded_account) -> None:
    """Uploads on one account never bump another account's counters."""
    assert _upload(client, _auth(seeded_account), _png_bytes("mine")).status_code == 201
    session = SessionLocal()
    try:
        company_counter = session.scalar(
            select(UsageCounter).where(
                UsageCounter.account_id == seeded_account["company_id"]
            )
        )
        assert company_counter is None
    finally:
        session.close()
