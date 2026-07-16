"""Chat endpoints — create conversations, send messages, read history.

Thin wrappers over the `conversations` service: `POST /conversations` opens a chat,
`POST /conversations/{id}/messages` runs one grounded agentic turn (and persists a
`retrieval_traces` row), and `GET /conversations/{id}/messages` replays history. Every
read/write is account-scoped through `AccountScope`, so no chat can cross accounts.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.schemas import (
    CitationGroupOut,
    CitationOut,
    ConversationListItem,
    ConversationOut,
    MessageAnswerOut,
    MessageCreate,
    MessageOut,
    MessageRatingIn,
    OkOut,
)
from app.core.scoping import AccountScope, get_current_account
from app.db.models import AnswerRating, Conversation, Document, Message
from app.services import conversations, usage

router = APIRouter(prefix="/api/v1", tags=["conversations"])


def _require_query_quota(scope: AccountScope) -> None:
    """402 (with an upgrade hint) when the plan's monthly query limit is spent."""
    try:
        usage.check_query_quota(scope.db, scope.account_id)
    except usage.QuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=usage.quota_http_detail(exc),
        )


def _resolve_document_scope(
    scope: AccountScope, body: MessageCreate
) -> list[uuid.UUID] | None:
    """Validate a `scope="document"` request → the pinned document ids (or None).

    400 if `scope="document"` without a `document_id`; 404 if that document isn't in
    the active account.
    """
    if body.scope != "document":
        return None
    if body.document_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "document_id_required",
                "message": "scope='document' requires document_id.",
            },
        )
    doc = scope.db.scalar(scope.select(Document).where(Document.id == body.document_id))
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Document not found."},
        )
    return [body.document_id]


def _require_conversation(scope: AccountScope, conversation_id: uuid.UUID) -> None:
    """404 unless `conversation_id` belongs to the active account."""
    convo = scope.db.scalar(
        scope.select(Conversation).where(Conversation.id == conversation_id)
    )
    if convo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Conversation not found."},
        )


@router.get("/conversations", response_model=list[ConversationListItem])
def list_conversations(
    scope: AccountScope = Depends(get_current_account),
) -> list[ConversationListItem]:
    """List the account's conversations (most-recent first) with title +
    last-message preview — the chat rail / continue-any-chat data."""
    return [
        ConversationListItem(**row)
        for row in conversations.list_conversations(scope.db, scope.account_id)
    ]


@router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    scope: AccountScope = Depends(get_current_account),
) -> ConversationOut:
    """Start a new chat for the active account."""
    convo_id = conversations.create_conversation(
        scope.account_id, user_id=scope.user.id, db=scope.db
    )
    return ConversationOut(id=convo_id)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageAnswerOut,
)
def post_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    scope: AccountScope = Depends(get_current_account),
) -> MessageAnswerOut:
    """Send a user message and get a grounded, cited answer.

    `scope="document"` pins the answer to `document_id` (which must belong to the
    active account). Returns 404 for an unknown/foreign conversation or document.
    """
    document_ids = _resolve_document_scope(scope, body)
    _require_query_quota(scope)

    try:
        result, _, message_id = conversations.chat(
            scope.account_id,
            body.content,
            conversation_id=conversation_id,
            user_id=scope.user.id,
            document_ids=document_ids,
            db=scope.db,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Conversation not found."},
        )

    return MessageAnswerOut(
        message_id=message_id,
        answer=result.answer,
        supported=result.supported,
        citations=[
            CitationOut(
                document_id=c.document_id,
                title=c.title,
                page=c.page,
                fact_id=c.fact_id,
            )
            for c in result.citations
        ],
        citation_groups=[
            CitationGroupOut(**g) for g in conversations.group_citations(result.citations)
        ],
    )


def _sse(events) -> "object":
    """Format an iterable of event dicts as a Server-Sent Events byte stream."""
    for event in events:
        yield f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"


@router.post("/conversations/{conversation_id}/messages/stream")
def post_message_stream(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    scope: AccountScope = Depends(get_current_account),
) -> StreamingResponse:
    """Same as POST messages, but streams the agent's steps as Server-Sent Events.

    Emits `intent` → `find_documents`/`searching` → (`escalating`) → `done` (the final
    answer + citations). Scope/conversation are validated up front, before streaming.
    """
    document_ids = _resolve_document_scope(scope, body)
    _require_conversation(scope, conversation_id)
    _require_query_quota(scope)
    events = conversations.chat_stream(
        scope.account_id,
        body.content,
        conversation_id=conversation_id,
        user_id=scope.user.id,
        document_ids=document_ids,
    )
    return StreamingResponse(_sse(events), media_type="text/event-stream")


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageOut],
)
def list_messages(
    conversation_id: uuid.UUID,
    scope: AccountScope = Depends(get_current_account),
) -> list[MessageOut]:
    """Return the conversation's full message history, oldest first."""
    _require_conversation(scope, conversation_id)
    rows = scope.db.scalars(
        select(Message)
        .where(
            Message.account_id == scope.account_id,
            Message.conversation_id == conversation_id,
        )
        .order_by(Message.created_at.asc(), Message.id.asc())
    ).all()
    return [MessageOut.model_validate(m) for m in rows]


@router.post("/messages/{message_id}/rating", response_model=OkOut)
def rate_message(
    message_id: uuid.UUID,
    body: MessageRatingIn,
    scope: AccountScope = Depends(get_current_account),
) -> OkOut:
    """Attach a rating to an assistant answer (feedback for eval/quality).

    404 unless the message belongs to the active account. Writes an `answer_ratings`
    row linked to the message (and its retrieval trace).
    """
    message = scope.db.scalar(
        scope.select(Message).where(Message.id == message_id)
    )
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Message not found."},
        )
    scope.db.add(
        AnswerRating(
            account_id=scope.account_id,
            message_id=message_id,
            user_id=scope.user.id,
            rating=body.rating,
            stars=body.stars,
            reasons=body.reasons or None,
            comment=body.comment,
        )
    )
    scope.db.commit()
    return OkOut(ok=True)
