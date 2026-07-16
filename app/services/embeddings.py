"""Local embeddings — make the extracted card searchable (Phase 4).

Each atomic fact (`document_facts.text`) and each document summary is embedded
with **BAAI/bge-base-en-v1.5** (local, 768-d, CPU, zero per-token cost) and
written to the `vector(768)` columns that already carry HNSW cosine indexes.
That powers the two-stage retrieval built in Phase 5: `summary_embedding` picks
candidate documents, then `document_facts.embedding` ranks atomic facts within
them — and because every fact row keeps its `page`/`bbox`, a vector hit is
already a citation.

Retrieval correctness depends on two details, both handled here:
  * **Normalized** vectors, so cosine distance (the index's operator) is exact.
  * **Asymmetric** encoding — bge wants a retrieval *instruction* on the query
    side only, never on the indexed passages. `embed_passages` (ingest) and
    `embed_query` (Phase 5 search) keep that asymmetry in one place.

The model is loaded lazily as a process-wide singleton; `_encode` is the single
compute seam, so tests stub it and never download the weights.
"""

from __future__ import annotations

import threading
import time
import uuid

from sqlalchemy import select

from app.db.models import Document, DocumentFact
from app.db.session import SessionLocal
from app.services.events import record_event

MODEL_NAME = "BAAI/bge-base-en-v1.5"
EMBEDDING_DIM = 768

# bge-v1.5 retrieval instruction — prepended to *queries* only (asymmetric).
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_BATCH_SIZE = 32

# Statuses we will (re-)embed. `extracted` is the normal entry; `indexed` allows
# a clean re-index; `needs_review` docs are embedded so they are searchable, but
# without clearing their review flag (see `run_embedding`).
_INDEXABLE = frozenset({"extracted", "indexed", "needs_review"})

_model = None
_model_lock = threading.Lock()


def _load_model():
    """Load the sentence-transformers model (CPU) — the seam tests stub."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME, device="cpu")


def _get_model():
    """Return the process-wide model, loading it exactly once under concurrency.

    Double-checked locking: concurrent first uploads can race the lazy init, and
    the load is ~400 MB — the lock guarantees a single load without paying lock
    cost on the hot path once warmed.
    """
    global _model
    if _model is None:  # fast path — no lock once warmed
        with _model_lock:
            if _model is None:  # re-check under the lock
                _model = _load_model()
    return _model


def _encode(texts: list[str]) -> list[list[float]]:
    """Encode texts to normalized 768-d vectors (the single compute seam)."""
    vectors = _get_model().encode(
        texts,
        batch_size=_BATCH_SIZE,
        normalize_embeddings=True,  # unit vectors -> cosine distance is exact
        convert_to_numpy=True,
    )
    return vectors.tolist()


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed documents/facts for indexing — no instruction prefix."""
    if not texts:
        return []
    return _encode(list(texts))


def embed_query(query: str) -> list[float]:
    """Embed a search query — with the bge retrieval instruction prefix."""
    return _encode([QUERY_INSTRUCTION + query])[0]


def run_embedding(document_id: uuid.UUID, account_id: uuid.UUID) -> None:
    """Embed a document's facts + summary and advance it to `indexed`.

    Runs after extraction (chained or invoked directly). Opens its own session,
    is account-scoped, idempotent (re-embedding overwrites in place), and
    swallows its own failures (marking the document `failed`) so it is safe from
    a background task. A `needs_review` document is still embedded (so it can be
    retrieved) but keeps its review status rather than flipping to `indexed`.
    """
    started = time.monotonic()
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None or document.account_id != account_id:
            return  # deleted or wrong account — never cross-scope
        if document.status not in _INDEXABLE:
            return  # not yet extracted

        record_event(
            db, account_id=account_id, document_id=document_id,
            stage="embedding", status="started",
        )
        db.commit()

        try:
            facts = db.scalars(
                select(DocumentFact)
                .where(
                    DocumentFact.account_id == account_id,
                    DocumentFact.document_id == document_id,
                )
                .order_by(DocumentFact.created_at)
            ).all()

            if facts:
                vectors = embed_passages([f.text for f in facts])
                for fact, vector in zip(facts, vectors):
                    fact.embedding = vector

            if document.summary:
                document.summary_embedding = embed_passages([document.summary])[0]

            # Don't erase a needs_review flag; embedding only advances the
            # pipeline status for documents already past confidence review.
            if document.status in ("extracted", "indexed"):
                document.status = "indexed"

            record_event(
                db, account_id=account_id, document_id=document_id,
                stage="embedding", status="succeeded",
                duration_ms=int((time.monotonic() - started) * 1000),
                detail={
                    "model": MODEL_NAME,
                    "facts_embedded": len(facts),
                    "summary_embedded": bool(document.summary),
                    "status": document.status,
                },
            )
            db.commit()
        except Exception as exc:  # noqa: BLE001 — record any failure, don't crash the worker
            db.rollback()
            document = db.get(Document, document_id)
            if document is not None:
                document.status = "failed"
                document.error = f"Embedding failed: {exc}"
            record_event(
                db, account_id=account_id, document_id=document_id,
                stage="embedding", status="failed",
                error=str(exc),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            db.commit()
