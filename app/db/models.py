"""SQLAlchemy ORM models mapped to the **existing** filemindr schema.

The schema is owned by `schema.sql` / Alembic `0001` — these classes only map
onto tables that already exist. Do not call `Base.metadata.create_all()`; tables
and enum types are created by migrations, never by the ORM.

Coverage is the document-core (identity, tenancy, classes, documents, card, and
atomic facts), chat + observability (conversations, messages, traces, ratings),
and usage/billing (plans, subscriptions, invoices, usage events/counters).

Every account-scoped table carries `account_id`; the scoping layer
(`app.core.scoping`) relies on that attribute being present.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    REAL,
    Text,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# --- Postgres ENUM types (already created by the migration) ---------------
# `create_type=False` keeps the ORM from ever trying to emit `CREATE TYPE`.
def _pg_enum(*labels: str, name: str) -> ENUM:
    return ENUM(*labels, name=name, create_type=False)


account_type_enum = _pg_enum("personal", "company", name="account_type")
member_role_enum = _pg_enum("member", "admin", "owner", name="member_role")
document_source_enum = _pg_enum("web_upload", "email_in", name="document_source")
document_status_enum = _pg_enum(
    "received", "ocr_done", "extracted", "indexed", "failed", "needs_review",
    name="document_status",
)
ocr_engine_enum = _pg_enum("pdf_text_layer", "google_vision", "docx", name="ocr_engine")
assigned_by_enum = _pg_enum("model", "user", name="assigned_by")
review_reason_enum = _pg_enum(
    "low_confidence", "ambiguous", "no_class", name="review_reason"
)
entity_type_enum = _pg_enum("person", "organization", "place", name="entity_type")
date_role_enum = _pg_enum(
    "issued", "due", "expiry", "event", "mentioned", name="date_role"
)
value_type_enum = _pg_enum(
    "money", "number", "date", "id", "string", name="value_type"
)
event_stage_enum = _pg_enum(
    "received", "ocr", "extraction", "embedding", "indexing", name="event_stage"
)
event_status_enum = _pg_enum("started", "succeeded", "failed", name="event_status")
message_role_enum = _pg_enum("user", "assistant", name="message_role")
rating_value_enum = _pg_enum("up", "down", name="rating_value")
subscription_status_enum = _pg_enum(
    "active", "past_due", "canceled", name="subscription_status"
)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )


# --- identity & tenancy ----------------------------------------------------
class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    type: Mapped[str] = mapped_column(account_type_enum, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))

    members: Mapped[list["AccountMember"]] = relationship(
        back_populates="account", passive_deletes=True
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("true"))
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))

    memberships: Mapped[list["AccountMember"]] = relationship(
        back_populates="user", passive_deletes=True
    )


class AccountMember(Base):
    __tablename__ = "account_members"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(member_role_enum, nullable=False, server_default=sql_text("'member'"))
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))

    account: Mapped[Account] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Class(Base):
    __tablename__ = "classes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("classes.id", ondelete="SET NULL")
    )
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("false"))
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


# --- documents & extracted card -------------------------------------------
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(document_source_enum, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(Text)
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    file_hash: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    summary_long: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        document_status_enum, nullable=False, server_default=sql_text("'received'")
    )
    review_reason: Mapped[str | None] = mapped_column(review_reason_enum)
    error: Mapped[str | None] = mapped_column(Text)
    ocr_text: Mapped[str | None] = mapped_column(Text)
    ocr_engine: Mapped[str | None] = mapped_column(ocr_engine_enum)
    extraction_raw: Mapped[dict | None] = mapped_column(JSONB)
    extraction_model: Mapped[str | None] = mapped_column(Text)
    summary_embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class DocumentClass(Base):
    __tablename__ = "document_classes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE"), nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(REAL)
    assigned_by: Mapped[str] = mapped_column(
        assigned_by_enum, nullable=False, server_default=sql_text("'model'")
    )
    # The single class that owns this document's folder placement (its
    # highest-confidence label). Others are secondary labels shown for display.
    is_primary: Mapped[bool] = mapped_column(
        nullable=False, server_default=sql_text("false")
    )
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(entity_type_enum, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class DocumentEntity(Base):
    __tablename__ = "document_entities"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("1"))


class DocumentDate(Base):
    __tablename__ = "document_dates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[dt.date | None] = mapped_column(Date)
    raw_text: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(date_role_enum, nullable=False, server_default=sql_text("'mentioned'"))
    page: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class TypedFact(Base):
    __tablename__ = "typed_facts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    value_numeric: Mapped[float | None] = mapped_column(Numeric)
    value_type: Mapped[str] = mapped_column(value_type_enum, nullable=False, server_default=sql_text("'string'"))
    unit: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


# --- atomic facts (primary retrieval unit) --------------------------------
class DocumentFact(Base):
    __tablename__ = "document_facts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[dict | None] = mapped_column(JSONB)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
    # `fts` is a generated tsvector column owned by Postgres — read-only here.
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


# --- pipeline observability (append-only) ---------------------------------
class ProcessingEvent(Base):
    __tablename__ = "processing_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(event_stage_enum, nullable=False)
    status: Mapped[str] = mapped_column(event_status_enum, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


# --- chat (conversation memory) -------------------------------------------
class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(message_role_enum, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class RetrievalTrace(Base):
    """Observability row written once per answered message.

    Captures what the synthesis agent did (intent, searches, citations) and what it
    cost (model, tokens, latency) so answers are auditable and ratings can attach to
    a concrete retrieval. One row per assistant message; account-scoped.
    """

    __tablename__ = "retrieval_traces"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    query_text: Mapped[str | None] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(Text)
    retrieval_plan: Mapped[dict | None] = mapped_column(JSONB)
    candidates: Mapped[dict | None] = mapped_column(JSONB)
    reranked: Mapped[dict | None] = mapped_column(JSONB)
    context_sent: Mapped[dict | None] = mapped_column(JSONB)
    answer: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[dict | None] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class AnswerRating(Base):
    """User feedback on an assistant answer (up/down, optional stars/reasons/comment).

    Linked to the rated message (and thus its retrieval trace), so feedback can be
    correlated with what the agent retrieved. Account-scoped.
    """

    __tablename__ = "answer_ratings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    rating: Mapped[str] = mapped_column(rating_value_enum, nullable=False)
    stars: Mapped[int | None] = mapped_column(Integer)
    reasons: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


# --- usage & billing (Phase 7) ---------------------------------------------
class Plan(Base):
    """Subscription plan catalog (global, seeded by the migration — no `account_id`).

    `limits` is a jsonb of quota keys (`documents`, `storage_gb`,
    `queries_per_month`); a null value means unlimited. Deliberately unscoped:
    plans are shared product configuration, not tenant data.
    """

    __tablename__ = "plans"

    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("0"))
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("'USD'"))
    limits: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class Subscription(Base):
    """An account's paid plan. At most one `active` row per account (partial unique
    index); an account with no active subscription is implicitly on the free plan.
    `external_ref` holds the payment provider's subscription/session id.
    """

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    plan_slug: Mapped[str] = mapped_column(ForeignKey("plans.slug"), nullable=False)
    status: Mapped[str] = mapped_column(
        subscription_status_enum, nullable=False, server_default=sql_text("'active'")
    )
    period_start: Mapped[dt.datetime | None] = mapped_column()
    period_end: Mapped[dt.datetime | None] = mapped_column()
    external_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class Invoice(Base):
    """A billing charge record (mock provider now, Stripe later via `external_ref`)."""

    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("'USD'"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    period: Mapped[str | None] = mapped_column(Text)
    external_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class UsageEvent(Base):
    """Append-only metering log — one row per billable action (upload, query).

    The jsonb column is named `metadata` in the schema; SQLAlchemy reserves that
    attribute on declarative classes, so it maps to `meta` here.
    """

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))


class UsageCounter(Base):
    """Per-account, per-calendar-month rollup of metered usage (`period` = "YYYY-MM").

    Kept in lockstep with `usage_events` by `services.usage.record_usage`; the
    monthly `queries` counter is what quota enforcement reads (document/storage
    caps are account totals and read the `documents` table directly).
    """

    __tablename__ = "usage_counters"

    id: Mapped[uuid.UUID] = _uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    period: Mapped[str] = mapped_column(Text, nullable=False)
    documents: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("0"))
    queries: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("0"))
    storage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=sql_text("0"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=sql_text("now()"))
