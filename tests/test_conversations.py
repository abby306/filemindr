"""Conversation memory: persistence, windowed history, account scope, and chat().

`chat` is exercised with `synthesize` stubbed (no Gemini), so we verify it loads
prior history, persists both turns, and threads context across turns.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.models import Message, RetrievalTrace
from app.db.session import SessionLocal
from app.services import conversations
from app.services.synthesis import Citation, SynthesisResult


def test_create_and_history_roundtrip(seeded_account) -> None:
    acct = seeded_account["personal_id"]
    convo = conversations.create_conversation(acct)
    with SessionLocal() as db:
        conversations.add_message(db, acct, convo, "user", "hello")
        conversations.add_message(db, acct, convo, "assistant", "hi there")
        db.commit()

        history = conversations.load_history(db, acct, convo)

    assert history == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]


def test_history_is_windowed_and_ordered(seeded_account) -> None:
    acct = seeded_account["personal_id"]
    convo = conversations.create_conversation(acct)
    with SessionLocal() as db:
        for i in range(5):
            conversations.add_message(db, acct, convo, "user", f"m{i}")
        db.commit()

        history = conversations.load_history(db, acct, convo, limit=2)

    assert [h["content"] for h in history] == ["m3", "m4"]  # last two, oldest-first


def test_history_account_scoped(seeded_account) -> None:
    acct = seeded_account["personal_id"]
    other = seeded_account["company_id"]
    convo = conversations.create_conversation(acct)
    with SessionLocal() as db:
        conversations.add_message(db, acct, convo, "user", "secret")
        db.commit()
        assert conversations.load_history(db, other, convo) == []


def test_add_message_rejects_foreign_account(seeded_account) -> None:
    acct = seeded_account["personal_id"]
    other = seeded_account["company_id"]
    convo = conversations.create_conversation(acct)
    with SessionLocal() as db:
        with pytest.raises(ValueError):
            conversations.add_message(db, other, convo, "user", "nope")


def test_chat_persists_turns_and_passes_history(seeded_account, monkeypatch) -> None:
    acct = seeded_account["personal_id"]
    seen_histories = []

    def fake_synthesize(query, account_id, *, history=None, db=None, **kw):
        seen_histories.append(list(history or []))
        return SynthesisResult(query=query, answer=f"answer to: {query}", supported=True)

    monkeypatch.setattr("app.services.synthesis.synthesize", fake_synthesize)

    # Turn 1 — new conversation, no prior history.
    res1, convo, msg_id1 = conversations.chat(acct, "first question")
    assert seen_histories[-1] == []
    assert res1.answer == "answer to: first question"
    assert msg_id1 is not None

    # Turn 2 — same conversation; the agent should see turn 1's two messages.
    res2, convo2, _ = conversations.chat(acct, "follow up", conversation_id=convo)
    assert convo2 == convo
    assert seen_histories[-1] == [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "answer to: first question"},
    ]

    # Both turns persisted: 2 user + 2 assistant.
    with SessionLocal() as db:
        rows = db.query(Message).filter_by(conversation_id=convo).all()
    assert len(rows) == 4


def test_chat_writes_retrieval_trace(seeded_account, monkeypatch) -> None:
    acct = seeded_account["personal_id"]
    doc_id = uuid.uuid4()

    def fake_synthesize(query, account_id, *, history=None, db=None, **kw):
        return SynthesisResult(
            query=query, answer="grounded answer", supported=True,
            intent="lexical", searches=["follow-up q"], escalated=True,
            citations=[Citation(fact_id=uuid.uuid4(), document_id=doc_id,
                                title="Doc", page=3)],
            candidate_facts=[{"id": "f1", "text": "a candidate fact"}],
            plan={"vector": 5, "corpus_documents": 13},
            prompt_tokens=11, completion_tokens=7, latency_ms=42,
        )

    monkeypatch.setattr("app.services.synthesis.synthesize", fake_synthesize)

    result, convo, msg_id = conversations.chat(acct, "what is the total?")

    with SessionLocal() as db:
        trace = db.query(RetrievalTrace).filter_by(message_id=msg_id).one()
        assert trace.account_id == acct
        assert trace.intent == "lexical"
        assert trace.answer == "grounded answer"
        assert trace.prompt_tokens == 11 and trace.completion_tokens == 7
        assert trace.latency_ms == 42
        assert trace.retrieval_plan["searches"] == ["follow-up q"]
        assert trace.retrieval_plan["escalated"] is True
        assert trace.retrieval_plan["vector"] == 5  # merged from result.plan
        assert trace.candidates == [{"id": "f1", "text": "a candidate fact"}]
        assert trace.context_sent["corpus_documents"] == 13
        assert trace.citations[0]["document_id"] == str(doc_id)
        assert trace.citations[0]["page"] == 3


def test_chat_threads_document_ids(seeded_account, monkeypatch) -> None:
    acct = seeded_account["personal_id"]
    scope = uuid.uuid4()
    seen = {}

    def fake_synthesize(query, account_id, *, history=None, db=None, document_ids=None, **kw):
        seen["document_ids"] = document_ids
        return SynthesisResult(query=query, answer="x", supported=True)

    monkeypatch.setattr("app.services.synthesis.synthesize", fake_synthesize)

    conversations.chat(acct, "scoped question", document_ids=[scope])
    assert seen["document_ids"] == [scope]
