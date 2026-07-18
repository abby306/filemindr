"""HTTP chat surface: conversation creation, messaging, history, and traces.

`synthesize` is stubbed (no Gemini), so these verify the endpoints' wiring: auth +
account scoping, the thin wrapper over `conversations.chat`, document-scope
validation, the persisted `retrieval_traces` row, and history replay.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import Document, Message, RetrievalTrace
from app.db.session import SessionLocal
from app.main import app
from app.services.synthesis import Citation, SynthesisResult


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _headers(seeded_account, *, account="personal_id") -> dict:
    return {
        "Authorization": f"Bearer {seeded_account['user_id']}",
        "X-Account-Id": str(seeded_account[account]),
    }


def _stub_synthesize(monkeypatch, *, capture=None, **fields):
    """Patch the synthesis seam to return a fixed result (optionally capturing kwargs)."""
    def fake(query, account_id, *, history=None, db=None, document_ids=None, **kw):
        if capture is not None:
            capture["document_ids"] = document_ids
        defaults = dict(query=query, answer="grounded answer", supported=True)
        defaults.update(fields)
        return SynthesisResult(**defaults)

    monkeypatch.setattr("app.services.synthesis.synthesize", fake)


def test_create_conversation(client, seeded_account) -> None:
    res = client.post("/api/v1/conversations", headers=_headers(seeded_account))
    assert res.status_code == 201
    assert uuid.UUID(res.json()["id"])  # a real uuid


def test_create_conversation_requires_auth(client) -> None:
    assert client.post("/api/v1/conversations").status_code == 401


def test_post_message_returns_answer_and_writes_trace(client, seeded_account, monkeypatch) -> None:
    doc_id = uuid.uuid4()
    fact_id = uuid.uuid4()
    _stub_synthesize(
        monkeypatch, answer="the total is $1240", supported=True, intent="aggregate",
        prompt_tokens=20, completion_tokens=9, latency_ms=33,
        citations=[Citation(fact_id=fact_id, document_id=doc_id, title="Invoice", page=2)],
    )
    headers = _headers(seeded_account)
    convo_id = client.post("/api/v1/conversations", headers=headers).json()["id"]

    res = client.post(
        f"/api/v1/conversations/{convo_id}/messages",
        headers=headers,
        json={"content": "what is the total?"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["answer"] == "the total is $1240"
    assert body["supported"] is True
    assert body["citations"][0]["document_id"] == str(doc_id)
    assert body["citations"][0]["page"] == 2
    message_id = body["message_id"]

    with SessionLocal() as db:
        msgs = db.query(Message).filter_by(conversation_id=uuid.UUID(convo_id)).all()
        assert {m.role for m in msgs} == {"user", "assistant"}
        trace = db.query(RetrievalTrace).filter_by(message_id=uuid.UUID(message_id)).one()
        assert trace.intent == "aggregate"
        assert trace.answer == "the total is $1240"
        assert trace.prompt_tokens == 20


def test_post_message_unknown_conversation_404(client, seeded_account, monkeypatch) -> None:
    _stub_synthesize(monkeypatch)
    res = client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        headers=_headers(seeded_account),
        json={"content": "hello"},
    )
    assert res.status_code == 404


def test_post_message_foreign_conversation_404(client, seeded_account, monkeypatch) -> None:
    _stub_synthesize(monkeypatch)
    # Conversation created under the company account...
    convo_id = client.post(
        "/api/v1/conversations", headers=_headers(seeded_account, account="company_id")
    ).json()["id"]
    # ...is invisible from the personal account.
    res = client.post(
        f"/api/v1/conversations/{convo_id}/messages",
        headers=_headers(seeded_account, account="personal_id"),
        json={"content": "hello"},
    )
    assert res.status_code == 404


def test_document_scope_requires_document_id(client, seeded_account, monkeypatch) -> None:
    _stub_synthesize(monkeypatch)
    headers = _headers(seeded_account)
    convo_id = client.post("/api/v1/conversations", headers=headers).json()["id"]
    res = client.post(
        f"/api/v1/conversations/{convo_id}/messages",
        headers=headers,
        json={"content": "hi", "scope": "document"},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "document_id_required"


def test_document_scope_unknown_document_404(client, seeded_account, monkeypatch) -> None:
    _stub_synthesize(monkeypatch)
    headers = _headers(seeded_account)
    convo_id = client.post("/api/v1/conversations", headers=headers).json()["id"]
    res = client.post(
        f"/api/v1/conversations/{convo_id}/messages",
        headers=headers,
        json={"content": "hi", "scope": "document", "document_id": str(uuid.uuid4())},
    )
    assert res.status_code == 404


def test_document_scope_threads_document_ids(client, seeded_account, monkeypatch) -> None:
    capture: dict = {}
    _stub_synthesize(monkeypatch, capture=capture)
    headers = _headers(seeded_account)
    convo_id = client.post("/api/v1/conversations", headers=headers).json()["id"]

    with SessionLocal() as db:
        doc = Document(
            account_id=seeded_account["personal_id"], source="web_upload",
            original_filename="f.pdf", file_hash=uuid.uuid4().hex,
            storage_path="/tmp/f.pdf", status="indexed",
        )
        db.add(doc)
        db.commit()
        doc_id = doc.id

    res = client.post(
        f"/api/v1/conversations/{convo_id}/messages",
        headers=headers,
        json={"content": "what does it say?", "scope": "document", "document_id": str(doc_id)},
    )
    assert res.status_code == 200
    assert capture["document_ids"] == [doc_id]

    with SessionLocal() as db:
        db.query(Document).filter_by(id=doc_id).delete()
        db.commit()


def test_list_messages_returns_history(client, seeded_account, monkeypatch) -> None:
    _stub_synthesize(monkeypatch, answer="answer one")
    headers = _headers(seeded_account)
    convo_id = client.post("/api/v1/conversations", headers=headers).json()["id"]
    client.post(
        f"/api/v1/conversations/{convo_id}/messages",
        headers=headers, json={"content": "question one"},
    )

    res = client.get(f"/api/v1/conversations/{convo_id}/messages", headers=headers)
    assert res.status_code == 200
    history = res.json()
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "question one"),
        ("assistant", "answer one"),
    ]


def test_list_messages_foreign_conversation_404(client, seeded_account, monkeypatch) -> None:
    _stub_synthesize(monkeypatch)
    convo_id = client.post(
        "/api/v1/conversations", headers=_headers(seeded_account, account="company_id")
    ).json()["id"]
    res = client.get(
        f"/api/v1/conversations/{convo_id}/messages",
        headers=_headers(seeded_account, account="personal_id"),
    )
    assert res.status_code == 404


def _stub_synthesize_iter(monkeypatch, *, answer="streamed answer", supported=True):
    """Patch the streaming core to emit a fixed event sequence + final result."""
    def fake_iter(query, account_id, *, history=None, db=None, document_ids=None, **kw):
        yield {"type": "intent", "intent": "semantic"}
        yield {"type": "searching", "query": "vat", "found": 1}
        yield {"type": "result", "result": SynthesisResult(
            query=query, answer=answer, supported=supported, intent="semantic")}
    monkeypatch.setattr("app.services.synthesis.synthesize_iter", fake_iter)


def test_message_stream_emits_events_and_persists(client, seeded_account, monkeypatch) -> None:
    _stub_synthesize_iter(monkeypatch)
    headers = _headers(seeded_account)
    cid = client.post("/api/v1/conversations", headers=headers).json()["id"]

    res = client.post(
        f"/api/v1/conversations/{cid}/messages/stream", headers=headers,
        json={"content": "what is the vat?"},
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    body = res.text
    for frame in ("event: intent", "event: searching", "event: done"):
        assert frame in body
    assert "streamed answer" in body

    with SessionLocal() as db:
        msgs = db.query(Message).filter_by(conversation_id=uuid.UUID(cid)).all()
        assert {m.role for m in msgs} == {"user", "assistant"}
        assert db.query(RetrievalTrace).join(
            Message, Message.id == RetrievalTrace.message_id
        ).filter(Message.conversation_id == uuid.UUID(cid)).count() == 1


def test_message_stream_unknown_conversation_404(client, seeded_account, monkeypatch) -> None:
    _stub_synthesize_iter(monkeypatch)
    res = client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages/stream",
        headers=_headers(seeded_account), json={"content": "hi"},
    )
    assert res.status_code == 404


def test_list_conversations_titles_from_first_message(client, seeded_account, monkeypatch) -> None:
    """GET /conversations lists chats with a derived title + last-message preview."""
    _stub_synthesize(monkeypatch, answer="the total is $1240", supported=True)
    headers = _headers(seeded_account)
    convo_id = client.post("/api/v1/conversations", headers=headers).json()["id"]
    client.post(
        f"/api/v1/conversations/{convo_id}/messages",
        headers=headers,
        json={"content": "What is the invoice total for Acme?"},
    )

    res = client.get("/api/v1/conversations", headers=headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    item = items[0]
    assert item["id"] == convo_id
    assert item["title"] == "What is the invoice total for Acme?"  # first user message
    assert item["message_count"] == 2
    assert "1240" in item["preview"]  # preview is the latest (assistant) message


def test_list_conversations_scoped_to_account(client, seeded_account, monkeypatch) -> None:
    _stub_synthesize(monkeypatch, answer="ok")
    personal = _headers(seeded_account, account="personal_id")
    convo = client.post("/api/v1/conversations", headers=personal).json()["id"]
    client.post(
        f"/api/v1/conversations/{convo}/messages",
        headers=personal, json={"content": "hi there"},
    )
    company = _headers(seeded_account, account="company_id")
    assert client.get("/api/v1/conversations", headers=company).json() == []
    assert len(client.get("/api/v1/conversations", headers=personal).json()) == 1


def test_message_groups_citations_by_document(client, seeded_account, monkeypatch) -> None:
    """citation_groups collapses repeated same-document citations into one source."""
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    _stub_synthesize(
        monkeypatch, answer="a", supported=True,
        citations=[
            Citation(fact_id=uuid.uuid4(), document_id=d1, title="Doc A", page=7),
            Citation(fact_id=uuid.uuid4(), document_id=d1, title="Doc A", page=3),
            Citation(fact_id=uuid.uuid4(), document_id=d2, title="Doc B", page=1),
        ],
    )
    headers = _headers(seeded_account)
    convo = client.post("/api/v1/conversations", headers=headers).json()["id"]
    body = client.post(
        f"/api/v1/conversations/{convo}/messages", headers=headers, json={"content": "q"}
    ).json()

    assert len(body["citations"]) == 3  # flat list unchanged
    groups = body["citation_groups"]
    assert len(groups) == 2
    group_a = next(g for g in groups if g["document_id"] == str(d1))
    assert group_a["title"] == "Doc A"
    assert group_a["pages"] == [3, 7]  # merged + sorted
    assert len(group_a["fact_ids"]) == 2


# --- conversation deletion ----------------------------------------------------


def test_delete_conversation_removes_it_and_its_history(client, seeded_account, monkeypatch) -> None:
    _stub_synthesize(monkeypatch)
    headers = _headers(seeded_account)
    cid = client.post("/api/v1/conversations", headers=headers).json()["id"]
    client.post(f"/api/v1/conversations/{cid}/messages", headers=headers,
                json={"content": "hello"})

    res = client.delete(f"/api/v1/conversations/{cid}", headers=headers)
    assert res.status_code == 204
    assert cid not in [c["id"] for c in client.get("/api/v1/conversations", headers=headers).json()]
    with SessionLocal() as db:
        from sqlalchemy import select
        assert db.scalars(select(Message).where(Message.conversation_id == uuid.UUID(cid))).first() is None


def test_delete_conversation_foreign_or_unknown_404s(client, seeded_account) -> None:
    headers = _headers(seeded_account)
    cid = client.post("/api/v1/conversations", headers=headers).json()["id"]
    assert client.delete(
        f"/api/v1/conversations/{cid}", headers=_headers(seeded_account, account="company_id")
    ).status_code == 404
    assert client.delete(
        f"/api/v1/conversations/{uuid.uuid4()}", headers=headers
    ).status_code == 404
    # still there for its owner
    assert client.delete(f"/api/v1/conversations/{cid}", headers=headers).status_code == 204


# --- @-mention document scope (document_ids) ---------------------------------


def test_document_ids_pin_the_answer(client, seeded_account, monkeypatch) -> None:
    captured: dict = {}
    _stub_synthesize(monkeypatch, capture=captured)
    headers = _headers(seeded_account)
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        docs = [
            Document(account_id=acct, source="web_upload", original_filename=f"m{i}.pdf",
                     file_hash=uuid.uuid4().hex, storage_path=f"/tmp/m{i}.pdf", status="indexed")
            for i in range(2)
        ]
        db.add_all(docs)
        db.commit()
        ids = [doc.id for doc in docs]

    try:
        cid = client.post("/api/v1/conversations", headers=headers).json()["id"]
        res = client.post(
            f"/api/v1/conversations/{cid}/messages", headers=headers,
            json={"content": "compare them", "document_ids": [str(i) for i in ids]},
        )
        assert res.status_code == 200, res.text
        assert captured["document_ids"] == ids  # both pinned, order kept

        # A mention of a foreign/unknown document 404s.
        bad = client.post(
            f"/api/v1/conversations/{cid}/messages", headers=headers,
            json={"content": "x", "document_ids": [str(uuid.uuid4())]},
        )
        assert bad.status_code == 404
    finally:
        with SessionLocal() as db:
            for i in ids:
                doc = db.get(Document, i)
                if doc is not None:
                    db.delete(doc)
            db.commit()
