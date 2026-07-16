"""Cross-encoder reranking — the precision stage of retrieval (Phase 5, Step 3).

RRF fusion (in `retrieval.py`) is a good *candidate generator* but a blunt ranker:
it scores a fact by where it placed in each source's list, not by whether it
actually answers the query. So a short, generic fact ("the product is a journaling
companion") or a thesis's front-matter ("dedicated to my parents") can outrank
the fact the user wants.

A cross-encoder fixes that: it reads the query and a candidate fact **together**
and scores their relevance directly. We run it over the merged top-N candidates
and reorder, keeping the top-k. The model (`BAAI/bge-reranker-base`, CPU) is a
thread-safe lazy singleton; `_score` is the single compute seam, so tests stub it
and never download the weights — mirroring `embeddings.py`.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.retrieval import FactHit

MODEL_NAME = "BAAI/bge-reranker-base"

_model = None
_model_lock = threading.Lock()


def _load_model():
    """Load the cross-encoder (CPU) — the seam tests stub."""
    from sentence_transformers import CrossEncoder

    return CrossEncoder(MODEL_NAME, device="cpu")


def _get_model():
    """Return the process-wide reranker, loading it exactly once under concurrency."""
    global _model
    if _model is None:  # fast path — no lock once warmed
        with _model_lock:
            if _model is None:  # re-check under the lock
                _model = _load_model()
    return _model


# How much the cross-encoder is trusted vs. the retrievers' fused consensus.
# < 1.0 so the reranker *refines* the ranking rather than overriding it: a small
# CPU reranker is brittle (it under-scores answers buried in a clause and can't
# read terse structured text like "person: X"), so a fact the retrievers strongly
# agree on must not be catastrophically dropped by one weak relevance score.
_RERANK_ALPHA = 0.4


def _score(pairs: list[tuple[str, str]]) -> list[float]:
    """Relevance score for each (query, passage) pair (the single compute seam)."""
    scores = _get_model().predict(pairs)
    return [float(s) for s in scores]


def _minmax(values: list[float]) -> list[float]:
    """Scale to [0, 1]; a degenerate (all-equal) range maps to all-zeros."""
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def rerank(query: str, hits: list[FactHit], *, top_k: int) -> list[FactHit]:
    """Re-score `hits` by **blending** cross-encoder relevance with the fused
    (RRF) score they arrive with, then return the top_k.

    ``final = alpha * cross_encoder + (1 - alpha) * fused`` (both min-max
    normalized over the candidate set). The reranker reorders within reason but
    can't bury a fact the retrievers strongly agreed on. Each hit's `score` is
    overwritten with the blended value. A no-op for an empty list.
    """
    if not hits:
        return []
    ce = _minmax(_score([(query, hit.text) for hit in hits]))
    fused = _minmax([hit.score for hit in hits])  # RRF score carried in on arrival
    for hit, c, f in zip(hits, ce, fused):
        hit.score = _RERANK_ALPHA * c + (1 - _RERANK_ALPHA) * f
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]
