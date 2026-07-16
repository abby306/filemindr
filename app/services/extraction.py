"""Structured extraction — turn OCR text into a document card + atomic facts.

One cheap structured-output LLM pass (DeepSeek, via the OpenAI-compatible client)
reads `documents.ocr_text` and returns JSON: a title/summary, multi-label
classes, entities, dates, typed facts, and self-contained atomic facts. The raw
response is saved to `documents.extraction_raw`; the parsed result is fanned out
into the card tables (`document_classes`, `entities`/`document_entities`,
`document_dates`, `typed_facts`) and the primary retrieval unit
(`document_facts`). Provenance (page + best-effort bbox) is pulled from the OCR
cache artifact written in the OCR phase.

Design notes:
  * `parse_extraction` is pure and lenient — it never trusts the model's shapes;
    bad enums fall back to defaults and unparseable dates become null, so a noisy
    response degrades gracefully instead of failing the whole document.
  * `call_extraction_model` is the only network seam; tests monkeypatch it to run
    entirely offline.
  * `run_extraction` opens its own session (it runs as a background task chained
    after OCR), is account-scoped throughout, and is idempotent: a re-run clears
    the previous card before writing a fresh one.
"""

from __future__ import annotations

import datetime as dt
import json
import time
import uuid
from dataclasses import dataclass
from functools import partial

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.concurrency import map_bounded
from app.core.config import get_settings
from app.core.retry import with_retry
from app.db.models import (
    Class,
    Document,
    DocumentClass,
    DocumentDate,
    DocumentEntity,
    DocumentFact,
    Entity,
    TypedFact,
)
from app.db.session import SessionLocal
from app.services import ocr
from app.services.events import record_event

# --- routing thresholds ----------------------------------------------------
# Below this top-class confidence (or with no class at all) a document lands in
# `needs_review` instead of `extracted`, so a human can confirm the card.
REVIEW_CONFIDENCE = 0.5

# Ambiguity: even a confident-enough top class is sent to review when a runner-up
# is nearly as likely — the "torn between 2-3 classes" case. Flagged only when the
# top is below CONFIDENT_CEILING, the gap to the runner-up is within AMBIGUITY_DELTA,
# and that runner-up itself clears AMBIGUITY_FLOOR (so a lone weak second doesn't
# trip it). A very confident top class (>= CONFIDENT_CEILING) is always trusted.
AMBIGUITY_DELTA = 0.15
AMBIGUITY_FLOOR = 0.30
CONFIDENT_CEILING = 0.80

# Long documents are extracted in page windows so the whole document is seen, not
# just its head. `_CHUNK_CHAR_BUDGET` packs whole pages into a chunk up to this
# many characters (one LLM call per chunk); a doc under the budget stays a single
# call. `_MAX_OCR_CHARS` is a hard per-call safety ceiling (e.g. one giant page).
_CHUNK_CHAR_BUDGET = 14_000
_MAX_OCR_CHARS = 50_000

# Minimum token overlap (fraction of fact tokens found in a block) before we
# trust an OCR block's bbox as a fact's provenance.
_BBOX_MIN_OVERLAP = 0.5

_VALUE_TYPES = frozenset({"money", "number", "date", "id", "string"})
_DATE_ROLES = frozenset({"issued", "due", "expiry", "event", "mentioned"})


# --- parsed result shapes (lenient validation) -----------------------------
def _coerce_date(value: object) -> dt.date | None:
    """Parse an ISO date string into a `date`; anything else becomes None."""
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


class ClassPrediction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    slug: str
    confidence: float | None = None

    @field_validator("slug", mode="before")
    @classmethod
    def _normalize_slug(cls, v: object) -> object:
        """Coerce common near-miss slug shapes to a bare catalog slug.

        With the hierarchical catalog the model sometimes emits a parent/child
        path (``"financial/invoice"``) or an arrow (``"financial > invoice"``)
        instead of the leaf slug. Take the last path segment and normalize
        separators so it can match the catalog; a still-unknown slug is dropped
        downstream and routes the doc to review.
        """
        if not isinstance(v, str):
            return v
        s = v.strip().lower()
        for sep in ("/", ">", "\\", "::", ":", "|"):
            if sep in s:
                s = s.split(sep)[-1]
        return s.strip().replace(" ", "_").replace("-", "_")

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> float | None:
        if v is None:
            return None
        try:
            return max(0.0, min(1.0, float(v)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None


class EntityGroups(BaseModel):
    model_config = ConfigDict(extra="ignore")

    people: list[str] = []
    organizations: list[str] = []
    places: list[str] = []

    @field_validator("people", "organizations", "places", mode="before")
    @classmethod
    def _coerce_names(cls, value):
        """Tolerate the model returning entity objects instead of plain strings.

        DeepSeek sometimes emits ``[{"name": "South Supermarket"}]`` instead of
        ``["South Supermarket"]``. Flatten dicts (preferring name/value/text keys),
        keep non-empty strings, and drop anything else — so one odd shape never
        fails the whole document.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        names: list[str] = []
        for item in value:
            if isinstance(item, str):
                name = item.strip()
            elif isinstance(item, dict):
                name = str(item.get("name") or item.get("value") or item.get("text") or "").strip()
            else:
                name = ""
            if name:
                names.append(name)
        return names


class DatePrediction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: dt.date | None = None
    raw_text: str | None = None
    role: str = "mentioned"

    @field_validator("value", mode="before")
    @classmethod
    def _parse_value(cls, v: object) -> dt.date | None:
        return _coerce_date(v)

    @field_validator("role", mode="before")
    @classmethod
    def _valid_role(cls, v: object) -> str:
        return v if v in _DATE_ROLES else "mentioned"


class TypedFactPrediction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str
    value: str | None = None
    value_numeric: float | None = None
    value_type: str = "string"
    unit: str | None = None
    page: int | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _stringify(cls, v: object) -> str | None:
        return None if v is None else str(v)

    @field_validator("value_numeric", mode="before")
    @classmethod
    def _numeric(cls, v: object) -> float | None:
        if v is None or v == "":
            return None
        try:
            return float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    @field_validator("value_type", mode="before")
    @classmethod
    def _valid_type(cls, v: object) -> str:
        return v if v in _VALUE_TYPES else "string"


class AtomicFactPrediction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    page: int | None = None


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    summary: str | None = None
    classes: list[ClassPrediction] = []
    entities: EntityGroups = EntityGroups()
    dates: list[DatePrediction] = []
    typed_facts: list[TypedFactPrediction] = []
    atomic_facts: list[AtomicFactPrediction] = []


# --- prompt ----------------------------------------------------------------
_SYSTEM_PROMPT = """You are a meticulous document archivist. Read the OCR text \
of a single document and return ONLY a JSON object describing it. Do not invent \
facts; extract only what the text supports.

Return this exact shape:
{
  "title": "short human title for the document",
  "summary": "1-3 sentence neutral summary",
  "classes": [{"slug": "<one of the provided class slugs>", "confidence": 0.0-1.0}],
  "entities": {"people": [], "organizations": [], "places": []},
  "dates": [{"value": "YYYY-MM-DD", "raw_text": "as written", "role": "issued|due|expiry|event|mentioned"}],
  "typed_facts": [{"label": "snake_case_label", "value": "string", "value_numeric": number_or_null, "value_type": "money|number|date|id|string", "unit": "USD|kg|...|null", "page": 1}],
  "atomic_facts": [{"text": "a self-contained sentence stating one fact", "page": 1}]
}

Rules:
- The text is divided by "===== PAGE n =====" markers. Set the `page` of every fact/date to the page number of the marker it appears under. You may be given only a slice of a longer document — extract only from the pages shown here.
- Use ONLY class slugs from the provided catalog; omit classes that do not apply. Multi-label is allowed. The catalog is a tree: prefer the most specific (indented) subclass, and use a parent category only when no subclass fits. If two classes are genuinely plausible, return both with honest confidences rather than forcing one.
- Atomic facts must each stand alone (resolve pronouns; name the subject) and carry the page they came from.
- Put every quantity (amounts, totals, counts, IDs) into typed_facts with value_numeric set when numeric.
- Use null for unknown fields. Output JSON only — no prose, no code fences."""


def _format_catalog(classes: list[Class]) -> str:
    """Render the class catalog as a two-level tree (parents, indented children).

    Leaves are shown under their parent so the model can prefer a specific subclass
    and fall back to the parent category only when nothing more specific fits.
    """
    by_id = {c.id: c for c in classes}
    children: dict[object, list[Class]] = {}
    roots: list[Class] = []
    for c in classes:
        if c.parent_id is not None and c.parent_id in by_id:
            children.setdefault(c.parent_id, []).append(c)
        else:
            roots.append(c)

    lines: list[str] = []
    for root in sorted(roots, key=lambda c: c.name):
        lines.append(f"- {root.slug}: {root.description or root.name}")
        for child in sorted(children.get(root.id, []), key=lambda c: c.name):
            lines.append(f"    - {child.slug}: {child.description or child.name}")
    return "\n".join(lines)


def build_messages(ocr_text: str, classes: list[Class]) -> list[dict]:
    """Assemble the chat messages for the extraction call (pure)."""
    text = ocr_text[:_MAX_OCR_CHARS]
    truncated = "\n\n[... text truncated ...]" if len(ocr_text) > _MAX_OCR_CHARS else ""
    user = (
        f"Class catalog (slug: description):\n{_format_catalog(classes)}\n\n"
        f"--- DOCUMENT OCR TEXT ---\n{text}{truncated}"
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


# --- LLM call (the only network seam; monkeypatched in tests) ---------------
_client = None


def _deepseek_client():
    global _client
    if _client is None:
        from openai import OpenAI

        settings = get_settings()
        _client = OpenAI(
            api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url
        )
    return _client


def _is_transient_llm(exc: Exception) -> bool:
    """True for transient DeepSeek/OpenAI errors worth retrying (never 4xx/auth)."""
    try:
        import openai
    except ImportError:  # pragma: no cover - openai is a hard dependency
        return False
    if isinstance(
        exc,
        (
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.RateLimitError,
            openai.InternalServerError,
        ),
    ):
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and (status == 429 or 500 <= status < 600)


def call_extraction_model(ocr_text: str, classes: list[Class]) -> tuple[str, str]:
    """Run the structured-output pass. Returns ``(raw_json, model_name)``."""
    settings = get_settings()
    response = _deepseek_client().chat.completions.create(
        model=settings.deepseek_model,
        messages=build_messages(ocr_text, classes),
        response_format={"type": "json_object"},
        temperature=0,
    )
    return response.choices[0].message.content or "{}", settings.deepseek_model


def parse_extraction(content: str) -> ExtractionResult:
    """Parse a raw model response into a validated `ExtractionResult` (lenient)."""
    cleaned = content.strip()
    if cleaned.startswith("```"):  # defensive: strip accidental code fences
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    data = json.loads(cleaned)
    return ExtractionResult.model_validate(data)


# --- page-window chunking (long documents) ---------------------------------
@dataclass
class PageChunk:
    """A contiguous run of pages extracted in a single LLM call.

    `text` carries `===== PAGE n =====` markers so the model can attribute each
    fact to its real page number, even within a multi-page chunk.
    """

    start_page: int
    end_page: int
    text: str


def _page_marker(page: int) -> str:
    return f"\n\n===== PAGE {page} =====\n"


def chunk_pages(
    pages: list[ocr.OcrPage], budget: int = _CHUNK_CHAR_BUDGET
) -> list[PageChunk]:
    """Pack whole pages into chunks of up to `budget` characters (pure).

    A page is never split across chunks; a single page larger than the budget
    becomes its own (over-budget) chunk. Returns one chunk per call the extractor
    will make — a short document yields exactly one.
    """
    chunks: list[PageChunk] = []
    buf: list[str] = []
    start: int | None = None
    last = 0
    size = 0
    for page in pages:
        segment = _page_marker(page.page) + (page.text or "")
        if buf and size + len(segment) > budget:
            chunks.append(PageChunk(start, last, "".join(buf).strip()))
            buf, size, start = [], 0, None
        if start is None:
            start = page.page
        buf.append(segment)
        size += len(segment)
        last = page.page
    if buf:
        chunks.append(PageChunk(start, last, "".join(buf).strip()))
    return chunks


# --- merge per-chunk cards into one ----------------------------------------
def _dedup_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        key = name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(name)
    return out


def merge_results(results: list[ExtractionResult]) -> ExtractionResult:
    """Combine per-chunk extractions into one card (pure).

    Title/summary take the first chunk that supplies them (the document opening);
    classes keep the highest confidence per slug; entities/dates/typed/atomic
    facts are unioned with duplicates removed. A single result passes through
    unchanged, so short (one-chunk) documents are unaffected.
    """
    if len(results) == 1:
        return results[0]

    title = next((r.title for r in results if r.title), None)
    summary = next((r.summary for r in results if r.summary), None)

    classes: dict[str, ClassPrediction] = {}
    for r in results:
        for c in r.classes:
            current = classes.get(c.slug)
            if current is None or (c.confidence or 0.0) > (current.confidence or 0.0):
                classes[c.slug] = c

    entities = EntityGroups(
        people=_dedup_names([n for r in results for n in r.entities.people]),
        organizations=_dedup_names([n for r in results for n in r.entities.organizations]),
        places=_dedup_names([n for r in results for n in r.entities.places]),
    )

    dates: list[DatePrediction] = []
    seen_dates: set[tuple] = set()
    for r in results:
        for d in r.dates:
            key = (d.value, d.role, d.raw_text)
            if key not in seen_dates:
                seen_dates.add(key)
                dates.append(d)

    typed_facts: list[TypedFactPrediction] = []
    seen_typed: set[tuple] = set()
    for r in results:
        for f in r.typed_facts:
            key = (f.label, f.value, f.page)
            if key not in seen_typed:
                seen_typed.add(key)
                typed_facts.append(f)

    atomic_facts: list[AtomicFactPrediction] = []
    seen_atomic: set[str] = set()
    for r in results:
        for f in r.atomic_facts:
            key = f.text.strip().lower()
            if key and key not in seen_atomic:
                seen_atomic.add(key)
                atomic_facts.append(f)

    return ExtractionResult(
        title=title,
        summary=summary,
        classes=list(classes.values()),
        entities=entities,
        dates=dates,
        typed_facts=typed_facts,
        atomic_facts=atomic_facts,
    )


# --- card fan-out ----------------------------------------------------------
def _load_class_catalog(db: Session, account_id: uuid.UUID) -> list[Class]:
    return list(
        db.scalars(select(Class).where(Class.account_id == account_id)).all()
    )


def _clear_previous_extraction(
    db: Session, account_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    """Idempotency: drop a document's prior card so a re-run is a clean rewrite.

    Shared `entities` rows are left in place (other documents may reference
    them); only the per-document join/fact rows are removed.
    """
    for model in (DocumentClass, DocumentEntity, DocumentDate, TypedFact, DocumentFact):
        db.execute(
            delete(model).where(
                model.account_id == account_id, model.document_id == document_id
            )
        )


def _upsert_entity(
    db: Session, account_id: uuid.UUID, name: str, type_: str
) -> Entity | None:
    normalized = name.strip().lower()
    if not normalized:
        return None
    entity = db.scalar(
        select(Entity).where(
            Entity.account_id == account_id,
            Entity.type == type_,
            Entity.normalized_name == normalized,
        )
    )
    if entity is None:
        entity = Entity(
            account_id=account_id,
            name=name.strip(),
            normalized_name=normalized,
            type=type_,
        )
        db.add(entity)
        db.flush()
    return entity


def _write_card(
    db: Session, document: Document, result: ExtractionResult, catalog: list[Class]
) -> None:
    account_id = document.account_id
    slug_to_id = {c.slug: c.id for c in catalog}

    # Keep only predictions whose slug is in the catalog; the highest-confidence
    # one becomes the document's primary class (its single folder placement).
    valid_preds = [p for p in result.classes if p.slug in slug_to_id]
    primary_pred = max(
        valid_preds, key=lambda p: p.confidence if p.confidence is not None else -1.0,
        default=None,
    )
    for pred in valid_preds:
        db.add(
            DocumentClass(
                account_id=account_id,
                document_id=document.id,
                class_id=slug_to_id[pred.slug],
                confidence=pred.confidence,
                assigned_by="model",
                is_primary=pred is primary_pred,
            )
        )

    groups = (
        ("person", result.entities.people),
        ("organization", result.entities.organizations),
        ("place", result.entities.places),
    )
    for type_, names in groups:
        seen: set[str] = set()
        for name in names:
            key = name.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            entity = _upsert_entity(db, account_id, name, type_)
            if entity is not None:
                db.add(
                    DocumentEntity(
                        account_id=account_id,
                        document_id=document.id,
                        entity_id=entity.id,
                    )
                )

    for date in result.dates:
        db.add(
            DocumentDate(
                account_id=account_id,
                document_id=document.id,
                value=date.value,
                raw_text=date.raw_text,
                role=date.role,
            )
        )

    for fact in result.typed_facts:
        db.add(
            TypedFact(
                account_id=account_id,
                document_id=document.id,
                label=fact.label,
                value=fact.value,
                value_numeric=fact.value_numeric,
                value_type=fact.value_type,
                unit=fact.unit,
                page=fact.page,
            )
        )


def _bbox_for_fact(
    cached: ocr.OcrResult | None, page: int | None, text: str
) -> dict | None:
    """Best-effort provenance: the OCR block on `page` that most overlaps `text`.

    Returns a `{"page", "bbox"}` dict when a confident match is found, else None.
    Atomic facts are model-paraphrased, so an exact match is not expected; we use
    token overlap and only attach a bbox when it clears `_BBOX_MIN_OVERLAP`.
    """
    if cached is None or page is None:
        return None
    fact_tokens = {t for t in text.lower().split() if len(t) > 2}
    if not fact_tokens:
        return None
    ocr_page = next((p for p in cached.pages if p.page == page), None)
    if ocr_page is None:
        return None

    best_overlap = 0.0
    best_bbox = None
    for block in ocr_page.blocks:
        block_tokens = {t for t in block.text.lower().split() if len(t) > 2}
        if not block_tokens:
            continue
        overlap = len(fact_tokens & block_tokens) / len(fact_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_bbox = block.bbox
    if best_bbox is None or best_overlap < _BBOX_MIN_OVERLAP:
        return None
    return {"page": page, "bbox": best_bbox}


def _write_atomic_facts(
    db: Session,
    document: Document,
    result: ExtractionResult,
    cached: ocr.OcrResult | None,
) -> int:
    count = 0
    for fact in result.atomic_facts:
        text = fact.text.strip()
        if not text:
            continue
        db.add(
            DocumentFact(
                account_id=document.account_id,
                document_id=document.id,
                text=text,
                page=fact.page,
                bbox=_bbox_for_fact(cached, fact.page, text),
                # `embedding` stays null until Phase 4.
            )
        )
        count += 1
    return count


def _route_status(
    result: ExtractionResult, valid_slugs: set[str] | None = None
) -> tuple[str, str | None]:
    """Decide the post-extraction status and (if any) the review reason.

    Returns ``("extracted", None)`` for a confident, unambiguous card, else
    ``("needs_review", reason)`` where reason is one of ``no_class`` /
    ``low_confidence`` / ``ambiguous`` — the signal the review UI prompts on.

    When `valid_slugs` is given, predictions whose slug isn't in the catalog are
    ignored for routing — so a doc the model was "confident" about under an
    invalid slug (which `_write_card` would drop) is sent to review, not silently
    indexed with no class.
    """
    preds = result.classes
    if valid_slugs is not None:
        preds = [c for c in preds if c.slug in valid_slugs]
    if not preds:
        return "needs_review", "no_class"
    confidences = sorted((c.confidence or 0.0 for c in preds), reverse=True)
    top = confidences[0]
    if top < REVIEW_CONFIDENCE:
        return "needs_review", "low_confidence"
    second = confidences[1] if len(confidences) > 1 else 0.0
    if top < CONFIDENT_CEILING and (top - second) <= AMBIGUITY_DELTA and second >= AMBIGUITY_FLOOR:
        return "needs_review", "ambiguous"
    return "extracted", None


# --- orchestration (background entry point) --------------------------------
# Statuses we are allowed to (re-)extract from. `extracted`/`needs_review` are
# included so a manual re-run is possible without resetting the document first.
_EXTRACTABLE = frozenset({"ocr_done", "extracted", "needs_review"})


def run_extraction(document_id: uuid.UUID, account_id: uuid.UUID) -> None:
    """Extract one document's card + atomic facts and advance its status.

    Runs after OCR (chained or invoked directly). Opens its own session, never
    crosses account scope, and swallows its own failures (marking the document
    `failed`) so it is safe to call from a background task.
    """
    started = time.monotonic()
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None or document.account_id != account_id:
            return  # deleted or wrong account — never cross-scope
        if document.status not in _EXTRACTABLE or not document.ocr_text:
            return  # nothing to extract (no OCR text, or wrong stage)

        record_event(
            db, account_id=account_id, document_id=document_id,
            stage="extraction", status="started",
        )
        db.commit()

        try:
            catalog = _load_class_catalog(db, account_id)

            # Split into page windows so the whole document is seen, not just its
            # head. The OCR cache holds per-page text; without it, fall back to a
            # single chunk over the stored ocr_text.
            cached = ocr.load_cached_ocr(document.file_hash)
            if cached and cached.pages:
                chunks = chunk_pages(cached.pages, _CHUNK_CHAR_BUDGET)
            else:
                chunks = [PageChunk(1, document.page_count or 1, document.ocr_text)]

            settings = get_settings()

            def _extract_chunk(item: tuple[int, PageChunk]) -> dict:
                """Network + parse for one chunk (runs in a worker thread; no DB)."""
                index, chunk = item
                try:
                    raw, model = with_retry(
                        partial(call_extraction_model, chunk.text, catalog),
                        attempts=settings.retry_max_attempts,
                        base_delay=settings.retry_base_delay,
                        is_retryable=_is_transient_llm,
                    )
                    return {"raw": raw, "model": model, "parsed": parse_extraction(raw)}
                except Exception as exc:  # noqa: BLE001 — tolerate a bad chunk, record it
                    return {
                        "failed": {
                            "chunk": index,
                            "pages": [chunk.start_page, chunk.end_page],
                            "error": str(exc),
                        }
                    }

            # Parallelize only the network phase; results stay in chunk order so
            # the merge's title/summary still come from the earliest chunk.
            outcomes = map_bounded(
                _extract_chunk,
                list(enumerate(chunks)),
                max_workers=settings.max_parallel_calls,
            )

            raw_chunks: list[dict] = []
            results: list[ExtractionResult] = []
            failed_chunks: list[dict] = []
            model_name = ""
            for outcome in outcomes:
                if "failed" in outcome:
                    failed_chunks.append(outcome["failed"])
                    continue
                results.append(outcome["parsed"])
                model_name = outcome["model"]
                try:
                    raw_chunks.append(json.loads(outcome["raw"]))
                except json.JSONDecodeError:
                    raw_chunks.append({"raw": outcome["raw"]})

            # Partial tolerance: a doc fails only if *every* chunk failed; one or
            # more good chunks still produce a (partial) card.
            if not results:
                raise RuntimeError(
                    f"All {len(chunks)} extraction chunk(s) failed: {failed_chunks}"
                )
            result = merge_results(results)

            _clear_previous_extraction(db, account_id, document_id)
            _write_card(db, document, result, catalog)
            fact_count = _write_atomic_facts(db, document, result, cached)

            document.extraction_raw = {
                "chunk_count": len(chunks),
                "chunks": raw_chunks,
                "failed_chunks": failed_chunks,
            }
            document.extraction_model = model_name
            if result.title:
                document.title = result.title
            document.summary = result.summary
            document.status, document.review_reason = _route_status(
                result, {c.slug for c in catalog}
            )

            record_event(
                db, account_id=account_id, document_id=document_id,
                stage="extraction", status="succeeded",
                duration_ms=int((time.monotonic() - started) * 1000),
                detail={
                    "model": model_name,
                    "status": document.status,
                    "review_reason": document.review_reason,
                    "chunks": len(chunks),
                    "failed_chunks": len(failed_chunks),
                    "classes": len(result.classes),
                    "entities": (
                        len(result.entities.people)
                        + len(result.entities.organizations)
                        + len(result.entities.places)
                    ),
                    "dates": len(result.dates),
                    "typed_facts": len(result.typed_facts),
                    "atomic_facts": fact_count,
                },
            )
            final_status = document.status
            db.commit()

            # Chain embedding for every successfully-extracted doc so it is
            # retrievable — including `needs_review` (run_embedding keeps that
            # flag rather than flipping it to `indexed`). Local import avoids a
            # cycle; run_embedding opens its own session and handles its own
            # failures, so it never disturbs the committed card.
            if final_status in ("extracted", "needs_review"):
                from app.services import embeddings

                embeddings.run_embedding(document_id, account_id)
        except Exception as exc:  # noqa: BLE001 — record any failure, don't crash the worker
            db.rollback()
            document = db.get(Document, document_id)
            if document is not None:
                document.status = "failed"
                document.error = f"Extraction failed: {exc}"
            record_event(
                db, account_id=account_id, document_id=document_id,
                stage="extraction", status="failed",
                error=str(exc),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            db.commit()
