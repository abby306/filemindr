"""Conversation memory — persist chats and replay windowed history (Step 5 foundation).

A chat is a `conversations` row; each turn is a `messages` row (`user` / `assistant`).
This lets a user start a chat, leave, and **continue it later** with context intact,
and lets the synthesis agent see recent turns so follow-ups/refinements work
("no, the other contract", "just the 2024 ones").

History is **windowed** (last N turns), not unbounded: a long chat naturally drifts,
and the user's own refinement is the correction mechanism — so we keep the prompt
small rather than summarizing. Everything is `account_id`-scoped.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select

from app.db.models import Conversation, Message, RetrievalTrace
from app.db.session import SessionLocal
from app.services import usage

# Default conversation context: the last 12 turns (~6 exchanges).
_HISTORY_TURNS = 12
_TITLE_LIMIT = 60
_PREVIEW_LIMIT = 120


def _truncate(text: str | None, limit: int) -> str:
    """Collapse whitespace and cut to `limit` chars with an ellipsis."""
    cleaned = " ".join((text or "").split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit].rstrip() + "…"


def create_conversation(
    account_id: uuid.UUID, *, user_id: uuid.UUID | None = None,
    title: str | None = None, db=None,
) -> uuid.UUID:
    """Start a new chat; return its id."""
    own = db is None
    db = db or SessionLocal()
    try:
        convo = Conversation(account_id=account_id, user_id=user_id, title=title)
        db.add(convo)
        db.commit()
        return convo.id
    finally:
        if own:
            db.close()


def add_message(
    db, account_id: uuid.UUID, conversation_id: uuid.UUID, role: str, content: str,
) -> uuid.UUID:
    """Append one turn to a conversation (caller controls the session/commit).

    Verifies the conversation belongs to `account_id` (never cross-scope) and
    bumps the conversation's `updated_at` for recency ordering.
    """
    convo = db.get(Conversation, conversation_id)
    if convo is None or convo.account_id != account_id:
        raise ValueError("Conversation not found for this account.")
    # Set created_at explicitly: messages added in one transaction would otherwise
    # share now() (the transaction timestamp), and uuid ids aren't monotonic — so
    # an explicit wall-clock stamp keeps user→assistant order deterministic.
    now = dt.datetime.now(dt.timezone.utc)
    message = Message(
        account_id=account_id, conversation_id=conversation_id,
        role=role, content=content, created_at=now,
    )
    db.add(message)
    convo.updated_at = now
    # Title the conversation from its first user message (cheap, deterministic;
    # server-side so every client — web + native — gets the same title).
    if role == "user" and not convo.title and content:
        convo.title = _truncate(content, _TITLE_LIMIT)
    db.flush()
    return message.id


def list_conversations(
    db, account_id: uuid.UUID, *, limit: int = 50,
) -> list[dict]:
    """List an account's conversations (most-recently-updated first) with a
    last-message preview and message count — the data for a chat rail /
    continue-any-chat list. Account-scoped."""
    convos = db.scalars(
        select(Conversation)
        .where(Conversation.account_id == account_id)
        .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
        .limit(limit)
    ).all()
    if not convos:
        return []

    ids = [c.id for c in convos]
    counts = dict(
        db.execute(
            select(Message.conversation_id, func.count())
            .where(Message.account_id == account_id, Message.conversation_id.in_(ids))
            .group_by(Message.conversation_id)
        ).all()
    )
    # Last message per conversation (Postgres DISTINCT ON).
    last = dict(
        db.execute(
            select(Message.conversation_id, Message.content)
            .where(Message.account_id == account_id, Message.conversation_id.in_(ids))
            .order_by(
                Message.conversation_id,
                Message.created_at.desc(),
                Message.id.desc(),
            )
            .distinct(Message.conversation_id)
        ).all()
    )
    return [
        {
            "id": c.id,
            "title": c.title,
            "preview": _truncate(last.get(c.id), _PREVIEW_LIMIT) or None,
            "message_count": counts.get(c.id, 0),
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in convos
    ]


def load_history(
    db, account_id: uuid.UUID, conversation_id: uuid.UUID, *, limit: int = _HISTORY_TURNS,
) -> list[dict]:
    """Return the last `limit` turns (oldest-first) as ``{role, content}`` dicts.

    Empty for a brand-new or unknown/other-account conversation.
    """
    convo = db.get(Conversation, conversation_id)
    if convo is None or convo.account_id != account_id:
        return []
    rows = db.scalars(
        select(Message)
        .where(
            Message.account_id == account_id,
            Message.conversation_id == conversation_id,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    ).all()
    return [{"role": m.role, "content": m.content or ""} for m in reversed(rows)]


def record_trace(db, account_id: uuid.UUID, message_id: uuid.UUID, result) -> None:
    """Persist one `retrieval_traces` row for an answered message (caller commits).

    Captures what the agent did and what it cost (from the `SynthesisResult`) so the
    answer is auditable and a rating can later attach to a concrete retrieval.
    """
    trace = RetrievalTrace(
        account_id=account_id,
        message_id=message_id,
        query_text=result.query,
        intent=result.intent or None,
        retrieval_plan={
            **(result.plan or {}),
            "searches": result.searches,
            "documents_looked_up": result.documents_looked_up,
            "candidates_seen": result.candidates_seen,
            "supported": result.supported,
            "escalated": result.escalated,
        },
        candidates=result.candidate_facts or None,
        context_sent={"corpus_documents": (result.plan or {}).get("corpus_documents")},
        answer=result.answer,
        citations=[
            {
                "fact_id": str(c.fact_id) if c.fact_id else None,
                "document_id": str(c.document_id),
                "title": c.title,
                "page": c.page,
            }
            for c in result.citations
        ],
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        latency_ms=result.latency_ms,
    )
    db.add(trace)


def _meter_query(
    db,
    account_id: uuid.UUID,
    user_id: uuid.UUID | None,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    result,
) -> None:
    """Meter one answered query (usage event + monthly counter), in the same
    transaction as the messages/trace so a turn and its metering are atomic."""
    usage.record_usage(
        db,
        account_id,
        type=usage.EVENT_QUERY_ASKED,
        user_id=user_id,
        meta={
            "conversation_id": str(conversation_id),
            "message_id": str(message_id),
            "model": result.model,
            "escalated": result.escalated,
            "tokens": (result.prompt_tokens or 0) + (result.completion_tokens or 0),
        },
        queries=1,
    )


def group_citations(citations) -> list[dict]:
    """Group flat citations by document (one entry per source, pages sorted).

    A grounded answer often cites several facts from the same document; grouping
    server-side means every client shows one source per document, not repeats.
    Preserves first-seen document order.
    """
    groups: dict = {}
    order: list = []
    for c in citations:
        key = c.document_id
        if key not in groups:
            groups[key] = {"document_id": key, "title": c.title, "pages": [], "fact_ids": []}
            order.append(key)
        g = groups[key]
        if c.page is not None and c.page not in g["pages"]:
            g["pages"].append(c.page)
        if c.fact_id is not None and c.fact_id not in g["fact_ids"]:
            g["fact_ids"].append(c.fact_id)
    for g in groups.values():
        g["pages"].sort()
    return [groups[k] for k in order]


def chat(
    account_id: uuid.UUID,
    user_message: str,
    *,
    conversation_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    document_ids: list[uuid.UUID] | None = None,
    db=None,
):
    """One conversational turn: load history → answer → persist both messages.

    Creates the conversation if `conversation_id` is None. Returns
    ``(SynthesisResult, conversation_id, assistant_message_id)``. The agent sees the
    prior turns (not the just-sent message), so follow-ups and corrections work; pass
    `document_ids` to scope the answer to specific documents. Writes one
    `retrieval_traces` row for the assistant turn.
    """
    from app.services.synthesis import synthesize  # local import avoids a cycle

    own = db is None
    db = db or SessionLocal()
    try:
        if conversation_id is None:
            convo = Conversation(account_id=account_id, user_id=user_id)
            db.add(convo)
            db.flush()
            conversation_id = convo.id

        history = load_history(db, account_id, conversation_id)
        result = synthesize(
            user_message, account_id, history=history, db=db, document_ids=document_ids
        )

        add_message(db, account_id, conversation_id, "user", user_message)
        assistant_message_id = add_message(
            db, account_id, conversation_id, "assistant", result.answer
        )
        record_trace(db, account_id, assistant_message_id, result)
        _meter_query(db, account_id, user_id, conversation_id, assistant_message_id, result)
        db.commit()
        return result, conversation_id, assistant_message_id
    finally:
        if own:
            db.close()


def chat_stream(
    account_id: uuid.UUID,
    user_message: str,
    *,
    conversation_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    document_ids: list[uuid.UUID] | None = None,
):
    """Streaming variant of `chat`: yields the agent's step events, then persists.

    A generator (run by Starlette in a worker thread) that opens **its own session**,
    forwards `synthesize_iter`'s events, then persists the assistant turn + trace and
    yields a final ``done`` event with the assistant `message_id` + citations. Assumes
    the caller has already validated the conversation/document scope.

    The **user message is committed before synthesis starts**, so a client that
    disconnects (or a synthesis failure) mid-stream never loses the question —
    the turn survives in history and can be retried. Synthesis errors yield an
    ``error`` event rather than silently ending the stream.
    """
    from app.services.synthesis import synthesize_iter  # local import avoids a cycle

    db = SessionLocal()
    try:
        if conversation_id is None:
            convo = Conversation(account_id=account_id, user_id=user_id)
            db.add(convo)
            db.flush()
            conversation_id = convo.id
        yield {"type": "conversation", "conversation_id": str(conversation_id)}

        # History first (it must not include this turn), then durably record the
        # question before any slow model work begins.
        history = load_history(db, account_id, conversation_id)
        add_message(db, account_id, conversation_id, "user", user_message)
        db.commit()

        result = None
        try:
            for event in synthesize_iter(
                user_message, account_id, history=history, db=db, document_ids=document_ids
            ):
                if event["type"] == "result":
                    result = event["result"]
                else:
                    yield event
        except Exception:
            db.rollback()
            yield {
                "type": "error",
                "conversation_id": str(conversation_id),
                "message": "Answering failed — your question is saved; try again.",
            }
            return

        message_id = add_message(db, account_id, conversation_id, "assistant", result.answer)
        record_trace(db, account_id, message_id, result)
        _meter_query(db, account_id, user_id, conversation_id, message_id, result)
        db.commit()
        yield {
            "type": "done",
            "message_id": str(message_id),
            "conversation_id": str(conversation_id),
            "answer": result.answer,
            "supported": result.supported,
            "escalated": result.escalated,
            "model": result.model,
            "citations": [
                {
                    "document_id": str(c.document_id),
                    "title": c.title,
                    "page": c.page,
                    "fact_id": str(c.fact_id) if c.fact_id else None,
                }
                for c in result.citations
            ],
            "citation_groups": [
                {
                    "document_id": str(g["document_id"]),
                    "title": g["title"],
                    "pages": g["pages"],
                    "fact_ids": [str(f) for f in g["fact_ids"]],
                }
                for g in group_citations(result.citations)
            ],
        }
    finally:
        db.close()
