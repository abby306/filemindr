"""Retrieval over the indexed card (Phase 5, Steps 1).

Answers a natural-language query by retrieving against the **structured** data the
ingest pipeline produced — typed facts, dates, entities, atomic facts — never the
raw OCR text. Three retrievers run and are fused; an intent label only *weights*
them, so a misrouted query still reaches every source (robust by construction):

  * **structured** (no LLM) — `typed_facts` (numeric for aggregates), `document_dates`,
    `entities`, coupled to the semantically-relevant documents so an aggregate
    never sums across the wrong doc. This is where "how much did I spend" belongs.
  * **lexical** — Postgres FTS (`document_facts.fts`, GIN) for exact ids/names.
  * **vector, two-stage** — `embed_query` → `documents.summary_embedding` (HNSW)
    shortlists docs → `document_facts.embedding` (HNSW) ranks facts within them.

Results are merged with **Reciprocal Rank Fusion** (rank-based, scale-free), then
the top-k atomic facts are returned. Every fact carries `document_id`/`page`/`bbox`,
so a hit is already a citation. Synthesis (Gemini/GPT) is Step 4 — `answer` is left
empty here; this module is the rateable retrieval engine.

`embed_query` is the only model seam (stubbed in tests). Everything is filtered by
`account_id` explicitly, mirroring the tenancy guarantee `AccountScope` enforces in
the HTTP layer.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.orm import Session

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
from app.services.embeddings import embed_query
from app.services.taxonomy import expand_class_slugs

# --- intent routing --------------------------------------------------------

Intent = str  # one of: aggregate | metadata | lexical | semantic

# Phrase triggers, checked in priority order. The first match wins; `semantic`
# is the default. Kept as plain rules (fast, free, deterministic, unit-tested);
# an LLM classifier can replace this later behind the same signature.
_AGGREGATE = re.compile(
    r"\b(how much|how many|total|subtotal|sum|spend|spent|combined|altogether|"
    r"average|count|number of|amount due|grand total|vat|tax)\b",
    re.IGNORECASE,
)
_LEXICAL = re.compile(
    r"\b(invoice number|reference number|receipt number|order number|"
    r"serial number|account number|tracking number|\w*\s*number|id\b|code\b)\b",
    re.IGNORECASE,
)
_METADATA = re.compile(
    r"\b(who|whom|when|what date|which document|parties|party|issued by|"
    r"signed by|expires?|expiry|valid until|due date|effective date|"
    r"how long|address|on behalf of)\b",
    re.IGNORECASE,
)
# A quoted span, a long alphanumeric run (an id), or an ALL-CAPS proper noun /
# corporate suffix (e.g. "SUPERVALUE", "INC") → exact-match lookup.
_QUOTED = re.compile(r"[\"'].+?[\"']")
_LONG_ID = re.compile(r"\b[0-9]{6,}\b|\b[A-Z0-9]{2,}-?[0-9]{4,}\b")
_ENTITYISH = re.compile(r"\b[A-Z]{4,}\b|\b(?:INC|LLC|LTD|CORP|GMBH)\b")

_WORD = re.compile(r"\b[a-z]{3,}\b", re.IGNORECASE)


def classify_intent(query: str) -> Intent:
    """Route a query to an intent. Pure; the first matching rule wins."""
    q = query.strip()
    if _AGGREGATE.search(q):
        return "aggregate"
    if _QUOTED.search(q) or _LONG_ID.search(q) or _ENTITYISH.search(q) or _LEXICAL.search(q):
        return "lexical"
    if _METADATA.search(q):
        return "metadata"
    return "semantic"


def _query_words(query: str) -> set[str]:
    """Content words of the query (lowercased, stopwords dropped) for label matching."""
    return {w.lower() for w in _WORD.findall(query)} - _TERM_STOPWORDS


# Per-intent source weights for fusion. Every source still runs; the intent only
# tilts the ranking, so misclassification degrades gracefully (never drops a hit).
_WEIGHTS: dict[Intent, dict[str, float]] = {
    "aggregate": {"structured": 1.0, "vector": 0.5, "lexical": 0.4},
    "metadata": {"structured": 0.8, "vector": 0.6, "lexical": 0.5},
    "lexical": {"lexical": 1.0, "vector": 0.5, "structured": 0.4},
    "semantic": {"vector": 1.0, "lexical": 0.6, "structured": 0.3},
}

# Tuning knobs (small corpus; generous recall, fusion sorts it out).
_DOC_SHORTLIST = 12  # stage-1 vector doc candidates
_STRUCT_DOCS = 4  # structured retrieval only mines the most-relevant docs
_PER_SOURCE = 20  # rows pulled from each retriever before fusion
_RRF_K = 60  # standard RRF damping constant
_RERANK_CANDIDATES = 30  # merged candidates handed to the cross-encoder
# A typed fact whose label the query names ("gross margin" → `gross_margin`) is a
# near-exact answer; fuse it as its own high-weight source so it surfaces across
# intents — even when plain vector ranking dilutes it among verbose prose.
_EXACT_WEIGHT = 1.2

# Labels that answer "how much / total" — surfaced first on aggregate queries.
_AMOUNT_LABEL = re.compile(
    r"\b(total|grand total|amount|subtotal|sum|price|due|balance|cost)\b",
    re.IGNORECASE,
)


# --- result types ----------------------------------------------------------


@dataclass
class FactHit:
    """One retrieved fact (atomic or structured), best-first after fusion."""

    key: str  # dedup key: fact uuid, or "structured:<label>:<doc>"
    text: str
    document_id: uuid.UUID
    source: str  # "vector" | "lexical" | "structured"
    page: int | None = None
    fact_id: uuid.UUID | None = None  # set for atomic facts (citation target)
    bbox: dict | None = None
    score: float = 0.0
    exact: bool = False  # a typed fact whose label the query explicitly named


@dataclass
class RetrievalResult:
    query: str
    intent: Intent
    facts: list[FactHit] = field(default_factory=list)
    doc_ids: list[uuid.UUID] = field(default_factory=list)
    plan: dict = field(default_factory=dict)  # source row counts, for the trace


# --- reciprocal rank fusion (pure) -----------------------------------------


def rrf_merge(
    ranked_lists: dict[str, list[FactHit]],
    *,
    weights: dict[str, float],
    rrf_k: int = _RRF_K,
) -> list[FactHit]:
    """Fuse per-source ranked lists into one, scored by weighted RRF.

    Each source contributes ``weight / (rrf_k + rank)`` to a hit's score; hits
    are deduped by `key` (a fact seen in two sources keeps the richest copy and
    sums the contributions). Returns hits sorted by score, best first.
    """
    scores: dict[str, float] = {}
    chosen: dict[str, FactHit] = {}
    for source, hits in ranked_lists.items():
        weight = weights.get(source, 0.0)
        if weight == 0.0:
            continue
        for rank, hit in enumerate(hits):
            scores[hit.key] = scores.get(hit.key, 0.0) + weight / (rrf_k + rank)
            # Prefer an atomic-fact copy (has a citation target) when duplicated.
            current = chosen.get(hit.key)
            if current is None or (current.fact_id is None and hit.fact_id is not None):
                chosen[hit.key] = hit
    merged = []
    for key, hit in chosen.items():
        hit.score = scores[key]
        merged.append(hit)
    merged.sort(key=lambda h: h.score, reverse=True)
    return merged


def _rank_doc_ids(facts: Iterable[FactHit]) -> list[uuid.UUID]:
    """Unique document ids in fact-rank order (first occurrence wins)."""
    seen: list[uuid.UUID] = []
    for hit in facts:
        if hit.document_id not in seen:
            seen.append(hit.document_id)
    return seen


# --- retrievers (DB) -------------------------------------------------------


def _resolve_scope(
    db: Session,
    account_id: uuid.UUID,
    document_ids: list[uuid.UUID] | None,
    class_slug: str | None,
) -> set[uuid.UUID] | None:
    """Resolve a search scope to a set of document ids (None = whole account).

    `class_slug` expands to that class's documents; an explicit `document_ids`
    intersects with it when both are given.
    """
    if not document_ids and not class_slug:
        return None
    scope: set[uuid.UUID] | None = set(document_ids) if document_ids else None
    if class_slug:
        slugs = expand_class_slugs(db, account_id, class_slug)
        in_class = set(db.scalars(
            select(DocumentClass.document_id)
            .join(Class, Class.id == DocumentClass.class_id)
            .where(DocumentClass.account_id == account_id, Class.slug.in_(slugs))
        ).all())
        scope = in_class if scope is None else (scope & in_class)
    return scope


def _vector_search(
    db: Session, account_id: uuid.UUID, qvec: list[float], *, limit: int,
    scope: set[uuid.UUID] | None = None,
) -> list[FactHit]:
    """Two-stage vector: summary_embedding shortlists docs, then rank facts within."""
    doc_stmt = (
        select(Document.id)
        .where(
            Document.account_id == account_id,
            Document.summary_embedding.is_not(None),
        )
        .order_by(Document.summary_embedding.cosine_distance(qvec))
        .limit(_DOC_SHORTLIST)
    )
    if scope is not None:
        doc_stmt = doc_stmt.where(Document.id.in_(scope))
    doc_ids = db.scalars(doc_stmt).all()
    if not doc_ids:
        return []
    rows = db.execute(
        select(
            DocumentFact.id,
            DocumentFact.document_id,
            DocumentFact.text,
            DocumentFact.page,
            DocumentFact.bbox,
        )
        .where(
            DocumentFact.account_id == account_id,
            DocumentFact.document_id.in_(doc_ids),
            DocumentFact.embedding.is_not(None),
        )
        .order_by(DocumentFact.embedding.cosine_distance(qvec))
        .limit(limit)
    ).all()
    return [
        FactHit(
            key=str(r.id),
            text=r.text,
            document_id=r.document_id,
            page=r.page,
            bbox=r.bbox,
            fact_id=r.id,
            source="vector",
        )
        for r in rows
    ]


# Capitalized sentence-openers that aren't meaningful exact-match terms.
_TERM_STOPWORDS = frozenset(
    {"which", "what", "who", "whom", "when", "where", "how", "the", "is", "are",
     "does", "did", "a", "an", "on", "of", "to", "in", "for", "and", "inc", "llc"}
)


def _lexical_terms(query: str) -> list[str]:
    """Identifier / proper-noun terms worth an exact match (ids, names, quoted spans)."""
    terms: list[str] = re.findall(r"[\"']([^\"']+)[\"']", query)  # quoted spans
    terms += re.findall(r"\b[0-9]{4,}\b", query)  # long numeric ids
    terms += re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", query)  # Capitalized / acronyms
    seen, out = set(), []
    for t in terms:
        key = t.lower()
        if key in _TERM_STOPWORDS or key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def _lexical_search(
    db: Session, account_id: uuid.UUID, query: str, *, limit: int,
    scope: set[uuid.UUID] | None = None,
) -> list[FactHit]:
    """Exact / lexical matches: FTS over atomic facts, plus typed-fact values and
    entity names — because exact identifiers (invoice numbers, serials) and named
    parties often live only in `typed_facts` / `entities`, never in an atomic fact.
    """
    tsquery = func.websearch_to_tsquery("english", query)
    fts = literal_column("fts")
    fts_stmt = (
        select(
            DocumentFact.id,
            DocumentFact.document_id,
            DocumentFact.text,
            DocumentFact.page,
            DocumentFact.bbox,
            func.ts_rank(fts, tsquery).label("rank"),
        )
        .where(DocumentFact.account_id == account_id, fts.op("@@")(tsquery))
        .order_by(literal_column("rank").desc())
        .limit(limit)
    )
    if scope is not None:
        fts_stmt = fts_stmt.where(DocumentFact.document_id.in_(scope))
    hits = [
        FactHit(
            key=str(r.id),
            text=r.text,
            document_id=r.document_id,
            page=r.page,
            bbox=r.bbox,
            fact_id=r.id,
            source="lexical",
        )
        for r in db.execute(fts_stmt).all()
    ]

    terms = _lexical_terms(query)
    if not terms:
        return hits

    # Exact-ish matches in typed_facts.value (ids/numbers) and entity names.
    tf_stmt = (
        select(
            TypedFact.id, TypedFact.document_id, TypedFact.label,
            TypedFact.value, TypedFact.page,
        )
        .where(TypedFact.account_id == account_id, or_(*[TypedFact.value.ilike(f"%{t}%") for t in terms]))
        .limit(limit)
    )
    if scope is not None:
        tf_stmt = tf_stmt.where(TypedFact.document_id.in_(scope))
    for r in db.execute(tf_stmt).all():
        hits.append(
            FactHit(
                key=f"lexical:tf:{r.id}",
                text=f"{r.label}: {r.value}",
                document_id=r.document_id,
                page=r.page,
                source="lexical",
            )
        )

    ent_stmt = (
        select(DocumentEntity.document_id, Entity.type, Entity.name)
        .join(Entity, Entity.id == DocumentEntity.entity_id)
        .where(DocumentEntity.account_id == account_id, or_(*[Entity.name.ilike(f"%{t}%") for t in terms]))
        .limit(limit)
    )
    if scope is not None:
        ent_stmt = ent_stmt.where(DocumentEntity.document_id.in_(scope))
    for r in db.execute(ent_stmt).all():
        hits.append(
            FactHit(
                key=f"lexical:entity:{r.document_id}:{r.name}",
                text=f"{r.type}: {r.name}",
                document_id=r.document_id,
                source="lexical",
            )
        )
    return hits


def _structured_search(
    db: Session,
    account_id: uuid.UUID,
    intent: Intent,
    ranked_doc_ids: list[uuid.UUID],
    query: str,
    *,
    limit: int,
) -> list[FactHit]:
    """Typed facts / dates / entities from the most-relevant documents.

    `ranked_doc_ids` is the vector + lexical shortlist **in relevance order**;
    structured retrieval mines only its top `_STRUCT_DOCS` and emits hits ordered
    by document relevance, then by how well the fact's *label* answers the query:
    a label the query names (`vat`, `invoice number`) leads, then amount-like
    labels on aggregates, then the rest. This coupling keeps an aggregate from
    summing across unrelated documents *and* stops a fact-heavy doc from flooding
    the top — a fact's rank reflects its document's relevance, not insert order.
    """
    docs = ranked_doc_ids[:_STRUCT_DOCS]
    if not docs:
        return []
    doc_rank = {doc_id: i for i, doc_id in enumerate(docs)}
    qwords = _query_words(query)

    def _label_priority(label: str) -> int:
        words = set(re.split(r"[^a-z0-9]+", label.lower()))
        if words & qwords:
            return 0  # the query names this label
        if intent == "aggregate" and _AMOUNT_LABEL.search(label):
            return 1  # amount-like, for "how much" with no named label
        return 2
    # (doc_rank, intra-doc priority, FactHit) — sorted into final order at the end.
    scored: list[tuple[int, int, FactHit]] = []

    numeric_only = intent == "aggregate"
    tf_stmt = select(
        TypedFact.id,
        TypedFact.document_id,
        TypedFact.label,
        TypedFact.value,
        TypedFact.value_numeric,
        TypedFact.unit,
        TypedFact.page,
    ).where(
        TypedFact.account_id == account_id,
        TypedFact.document_id.in_(docs),
    )
    if numeric_only:
        tf_stmt = tf_stmt.where(TypedFact.value_numeric.is_not(None))
    for r in db.execute(tf_stmt).all():
        shown = r.value if r.value is not None else r.value_numeric
        # Avoid doubling a unit the extracted value already carries.
        unit = f" {r.unit}" if r.unit and str(r.unit) not in str(shown) else ""
        priority = _label_priority(r.label)
        scored.append((
            doc_rank[r.document_id],
            priority,
            FactHit(
                key=f"structured:tf:{r.id}",
                text=f"{r.label}: {shown}{unit}",
                document_id=r.document_id,
                page=r.page,
                source="structured",
                exact=(priority == 0),  # the query named this label
            ),
        ))

    if intent == "metadata":
        for r in db.execute(
            select(
                DocumentDate.id,
                DocumentDate.document_id,
                DocumentDate.value,
                DocumentDate.raw_text,
                DocumentDate.role,
                DocumentDate.page,
            ).where(
                DocumentDate.account_id == account_id,
                DocumentDate.document_id.in_(docs),
            )
        ).all():
            shown = r.raw_text or (r.value.isoformat() if r.value else "")
            scored.append((
                doc_rank[r.document_id], 2,
                FactHit(
                    key=f"structured:date:{r.id}",
                    text=f"{r.role} date: {shown}",
                    document_id=r.document_id,
                    page=r.page,
                    source="structured",
                ),
            ))
        for r in db.execute(
            select(DocumentEntity.document_id, Entity.type, Entity.name)
            .join(Entity, Entity.id == DocumentEntity.entity_id)
            .where(
                DocumentEntity.account_id == account_id,
                DocumentEntity.document_id.in_(docs),
            )
        ).all():
            scored.append((
                doc_rank[r.document_id], 1,
                FactHit(
                    key=f"structured:entity:{r.document_id}:{r.name}",
                    text=f"{r.type}: {r.name}",
                    document_id=r.document_id,
                    source="structured",
                ),
            ))

    # Most-relevant document first; amount/entity labels ahead of filler within it.
    scored.sort(key=lambda t: (t[0], t[1]))
    return [hit for _, _, hit in scored[:limit]]


# --- public entry point ----------------------------------------------------


def retrieve(
    query: str,
    account_id: uuid.UUID,
    *,
    db: Session | None = None,
    k: int = 5,
    rerank: bool = True,
    document_ids: list[uuid.UUID] | None = None,
    class_slug: str | None = None,
) -> RetrievalResult:
    """Retrieve the top-k facts for `query` within `account_id`.

    Two stages: the structured / lexical / vector retrievers generate candidates,
    fused with intent-weighted RRF; a cross-encoder then **reranks** the merged
    top-N by direct query-fact relevance (the precision stage). Set `rerank=False`
    to return the raw fused order (used in tests / for ablation). `document_ids` /
    `class_slug` **scope** the search to specific documents or a class (used by the
    agent when the user names a document or group). Opens its own session if one
    isn't supplied. `RetrievalResult.facts` is the ranked output.
    """
    own_session = db is None
    db = db or SessionLocal()
    try:
        intent = classify_intent(query)
        weights = _WEIGHTS[intent]
        scope = _resolve_scope(db, account_id, document_ids, class_slug)

        qvec = embed_query(query)
        vector_hits = _vector_search(db, account_id, qvec, limit=_PER_SOURCE, scope=scope)
        lexical_hits = _lexical_search(db, account_id, query, limit=_PER_SOURCE, scope=scope)

        # Structured search mines the docs the query is actually about, in
        # relevance order (so a fact's rank reflects its document's relevance).
        ranked_docs = _rank_doc_ids(vector_hits + lexical_hits)
        structured_hits = _structured_search(
            db, account_id, intent, ranked_docs, query, limit=_PER_SOURCE
        )

        # Label-matched typed facts fuse twice: as `structured` (intent-weighted)
        # and as a high-weight `exact` source, so a directly-named field surfaces.
        exact_hits = [h for h in structured_hits if h.exact]
        merged = rrf_merge(
            {
                "vector": vector_hits,
                "lexical": lexical_hits,
                "structured": structured_hits,
                "exact": exact_hits,
            },
            weights={**weights, "exact": _EXACT_WEIGHT},
        )
        if rerank and merged:
            from app.services import reranking

            top = reranking.rerank(query, merged[:_RERANK_CANDIDATES], top_k=k)
        else:
            top = merged[:k]
        return RetrievalResult(
            query=query,
            intent=intent,
            facts=top,
            doc_ids=_rank_doc_ids(top),
            plan={
                "intent": intent,
                "weights": weights,
                "reranked": bool(rerank and merged),
                "counts": {
                    "vector": len(vector_hits),
                    "lexical": len(lexical_hits),
                    "structured": len(structured_hits),
                    "merged": len(merged),
                },
            },
        )
    finally:
        if own_session:
            db.close()
