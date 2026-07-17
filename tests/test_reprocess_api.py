"""The reprocess endpoint + the bounded pipeline executor.

The endpoint re-drives a failed/stalled document (resetting `failed` →
`received` immediately so the UI shows live progress); `pipeline.submit` runs
inline when PIPELINE_WORKERS=0 (the test mode) and on the dedicated pool
otherwise. Entry points are monkeypatched — no OCR/LLM work runs here.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import Document
from app.db.session import SessionLocal
from app.main import app
from app.services import ocr, pipeline


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _headers(seeded_account: dict, account: str = "personal_id") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded_account['user_id']}",
        "X-Account-Id": str(seeded_account[account]),
    }


@pytest.fixture
def make_document(seeded_account):
    """Create a doc in a given status for the personal account; cleaned up."""
    created: list[uuid.UUID] = []

    def _make(status: str, *, error: str | None = None) -> uuid.UUID:
        with SessionLocal() as db:
            doc = Document(
                account_id=seeded_account["personal_id"],
                source="web_upload",
                original_filename=f"{status}-{uuid.uuid4().hex[:6]}.pdf",
                file_hash=uuid.uuid4().hex,
                storage_path="/tmp/nonexistent.pdf",
                status=status,
                error=error,
            )
            db.add(doc)
            db.commit()
            created.append(doc.id)
            return doc.id

    yield _make
    with SessionLocal() as db:
        for doc_id in created:
            doc = db.get(Document, doc_id)
            if doc is not None:
                db.delete(doc)
        db.commit()


@pytest.fixture
def recorded_ocr(monkeypatch):
    """Stub the OCR entry point (the route for received/failed docs)."""
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []
    monkeypatch.setattr(ocr, "run_ocr", lambda doc_id, account_id: calls.append((doc_id, account_id)))
    return calls


def test_reprocess_failed_resets_and_redrives(
    client, seeded_account, make_document, recorded_ocr
) -> None:
    doc_id = make_document("failed", error="QueuePool limit reached")

    res = client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=_headers(seeded_account))
    assert res.status_code == 200
    body = res.json()
    # Reset is visible immediately — the UI flips back to the live pipeline.
    assert body["status"] == "received"

    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        assert doc.status == "received"
        assert doc.error is None
    # Inline pipeline (workers=0) drove the OCR entry point for this doc.
    assert recorded_ocr == [(doc_id, seeded_account["personal_id"])]


def test_reprocess_stuck_received_redrives_without_reset(
    client, seeded_account, make_document, recorded_ocr
) -> None:
    doc_id = make_document("received")

    res = client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=_headers(seeded_account))
    assert res.status_code == 200
    assert res.json()["status"] == "received"
    assert recorded_ocr == [(doc_id, seeded_account["personal_id"])]


def test_reprocess_indexed_conflicts(client, seeded_account, make_document) -> None:
    doc_id = make_document("indexed")
    res = client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=_headers(seeded_account))
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "already_indexed"


def test_reprocess_foreign_document_404s(
    client, seeded_account, make_document, recorded_ocr
) -> None:
    doc_id = make_document("failed")
    res = client.post(
        f"/api/v1/documents/{doc_id}/reprocess",
        headers=_headers(seeded_account, account="company_id"),
    )
    assert res.status_code == 404
    assert recorded_ocr == []


def test_reprocess_unknown_document_404s(client, seeded_account) -> None:
    res = client.post(
        f"/api/v1/documents/{uuid.uuid4()}/reprocess", headers=_headers(seeded_account)
    )
    assert res.status_code == 404


# --- pipeline.submit --------------------------------------------------------


def test_submit_runs_inline_when_workers_zero() -> None:
    ran: list[int] = []
    pipeline.submit(ran.append, 1)  # PIPELINE_WORKERS=0 in the test env
    assert ran == [1]


def test_submit_uses_bounded_pool_when_workers_positive(monkeypatch) -> None:
    class _Settings:
        pipeline_workers = 2

    monkeypatch.setattr(pipeline, "get_settings", lambda: _Settings())
    monkeypatch.setattr(pipeline, "_executor", None)
    done = threading.Event()
    try:
        pipeline.submit(done.set)
        assert done.wait(timeout=5), "task never ran on the pipeline pool"
        assert pipeline._executor is not None
        assert pipeline._executor._max_workers == 2
    finally:
        pipeline._executor.shutdown(wait=True)
        pipeline._executor = None
