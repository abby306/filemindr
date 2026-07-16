"""Pydantic response models for the API.

These mirror `API_CONTRACTS.md`. `DocumentOut` is the light list/ingest view;
`DocumentCardOut` adds the extracted card (classes, entities, dates, typed facts)
returned by the document-detail endpoint once extraction has run.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PrimaryClassOut(BaseModel):
    """The document's primary class (its folder) — enough for a list view."""

    slug: str
    name: str | None = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    review_reason: str | None = None
    source: str
    original_filename: str
    mime_type: str | None
    byte_size: int | None
    title: str | None
    summary: str | None
    language: str | None
    page_count: int | None
    created_at: dt.datetime
    primary_class: PrimaryClassOut | None = None


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    next_cursor: str | None


# --- document card (detail view) -------------------------------------------
class ClassCardOut(BaseModel):
    slug: str
    name: str | None = None
    confidence: float | None = None
    assigned_by: str | None = None
    parent_slug: str | None = None
    is_primary: bool = False


class EntitiesCardOut(BaseModel):
    people: list[str] = []
    organizations: list[str] = []
    places: list[str] = []


class DateCardOut(BaseModel):
    value: dt.date | None = None
    raw_text: str | None = None
    role: str


class TypedFactCardOut(BaseModel):
    label: str
    value: str | None = None
    value_numeric: float | None = None
    type: str
    unit: str | None = None
    page: int | None = None


class FactRegionOut(BaseModel):
    """An atomic fact's location for provenance overlay: normalized bbox
    ``[x, y, w, h]`` in [0,1] (None when unavailable → page-level highlight)."""

    id: uuid.UUID
    page: int | None = None
    text: str | None = None
    bbox: list[float] | None = None


class DocumentCardOut(DocumentOut):
    classes: list[ClassCardOut] = []
    entities: EntitiesCardOut = EntitiesCardOut()
    dates: list[DateCardOut] = []
    typed_facts: list[TypedFactCardOut] = []
    fact_count: int = 0


# --- classes (catalog management) ------------------------------------------
class ClassOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None = None
    parent_id: uuid.UUID | None = None
    parent_slug: str | None = None
    is_system: bool
    document_count: int = 0


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = None
    parent_id: uuid.UUID | None = None


class ClassRename(BaseModel):
    name: str = Field(min_length=1, max_length=80)


# --- document class assignment (human-in-the-loop review) ------------------
class NewClassIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = None
    parent_id: uuid.UUID | None = None


class DocumentClassAssignIn(BaseModel):
    """Confirm a document's classes. Either pick existing `class_ids`, create a
    `new_class` on the spot, or both — at least one resulting class is required.

    `mode` decides folder semantics: `replace` (default) swaps in the picked
    classes (review/move); `add` appends them alongside existing labels;
    `set_primary` makes the first picked class the primary (folder placement)
    while keeping the document's other labels (drag-to-folder move without
    losing secondary labels)."""

    class_ids: list[uuid.UUID] = []
    new_class: NewClassIn | None = None
    mode: Literal["add", "replace", "set_primary"] = "replace"


# --- chat / conversations --------------------------------------------------
class ConversationOut(BaseModel):
    id: uuid.UUID


class ConversationListItem(BaseModel):
    id: uuid.UUID
    title: str | None = None
    preview: str | None = None
    message_count: int = 0
    created_at: dt.datetime
    updated_at: dt.datetime


class MessageCreate(BaseModel):
    content: str
    scope: Literal["account", "document"] | None = None
    document_id: uuid.UUID | None = None


class CitationOut(BaseModel):
    document_id: uuid.UUID
    title: str | None = None
    page: int | None = None
    fact_id: uuid.UUID | None = None


class CitationGroupOut(BaseModel):
    """Citations grouped by document — one entry per source (pages/facts merged),
    so a client renders one pill per document instead of repeating it."""

    document_id: uuid.UUID
    title: str | None = None
    pages: list[int] = []
    fact_ids: list[uuid.UUID] = []


class MessageAnswerOut(BaseModel):
    message_id: uuid.UUID
    answer: str
    citations: list[CitationOut] = []
    citation_groups: list[CitationGroupOut] = []
    supported: bool


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str | None
    created_at: dt.datetime


class MessageRatingIn(BaseModel):
    rating: Literal["up", "down"]
    stars: int | None = Field(default=None, ge=1, le=5)
    reasons: list[str] | None = None
    comment: str | None = None


class OkOut(BaseModel):
    ok: bool


# --- analytics ---------------------------------------------------------------
class SeriesPointOut(BaseModel):
    """One day of a time series (zero-filled server-side so charts don't lie)."""

    date: dt.date
    count: int
    cumulative: int | None = None


class TopClassOut(BaseModel):
    slug: str
    name: str
    count: int


class MostAskedDocumentOut(BaseModel):
    document_id: uuid.UUID
    title: str | None
    count: int


class UsageSeriesOut(BaseModel):
    documents_over_time: list[SeriesPointOut]
    queries_per_day: list[SeriesPointOut]


class AnalyticsUsageOut(BaseModel):
    """Usage lens. `documents`/`storage_bytes` are account totals (it's an
    archive); `queries`/`token_spend` are within the requested range."""

    range_days: int
    documents: int
    queries: int
    storage_bytes: int
    token_spend: int
    series: UsageSeriesOut
    top_classes: list[TopClassOut]
    most_asked_documents: list[MostAskedDocumentOut]


class AnalyticsQualityOut(BaseModel):
    """Quality lens; a metric is null until there is data to derive it from."""

    answer_rating_pct: float | None
    grounded_pct: float | None
    avg_retrieval_ms: int | None
    extraction_success_pct: float | None
    ratings_count: int
    answers_count: int


# --- billing -----------------------------------------------------------------
class PlanOut(BaseModel):
    slug: str
    name: str
    price_cents: int
    currency: str
    limits: dict

    model_config = ConfigDict(from_attributes=True)


class SubscriptionUsageOut(BaseModel):
    documents: int
    queries: int
    storage_bytes: int


class SubscriptionOut(BaseModel):
    plan: PlanOut
    status: str
    period_end: dt.datetime | None
    usage: SubscriptionUsageOut
    limits: dict


class CheckoutIn(BaseModel):
    plan_slug: str


class CheckoutOut(BaseModel):
    checkout_url: str
    session_id: str


class CheckoutCompleteIn(BaseModel):
    session_id: str


class InvoiceOut(BaseModel):
    id: uuid.UUID
    amount_cents: int
    currency: str
    status: str
    period: str | None
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceListOut(BaseModel):
    items: list[InvoiceOut]
