"""Pure scorers for retrieval quality.

`recall_at_k` measures whether the things that should have been retrieved (gold
documents, or gold fact substrings) appear in the top-k results.
`answer_correctness` measures whether the synthesized answer contains the
required phrases. Both return None when a query declares no expectation of that
kind, so they are excluded from averages rather than scored as 0 or 1.

Answer/fact matching is substring-based on normalized text for now; the
`normalize` seam and the None-aware aggregation make it straightforward to swap
in an LLM judge later without changing the runner.
"""

from __future__ import annotations

from collections.abc import Sequence
from statistics import mean

from eval.schema import GoldQuery, RetrievedAnswer


def normalize(text: str) -> str:
    """Casefold and collapse whitespace for tolerant substring matching."""
    return " ".join(text.split()).casefold()


def recall_at_k(expected: Sequence[str], retrieved: Sequence[str], k: int) -> float | None:
    """Fraction of `expected` items found in the top-k `retrieved`.

    Each expected string matches if it is a substring of any top-k retrieved
    string (so it works for both exact doc ids and fact substrings). Returns None
    when nothing is expected (not applicable to this query).
    """
    if not expected:
        return None
    top = [normalize(r) for r in retrieved[:k]]
    hits = sum(1 for exp in expected if any(normalize(exp) in r for r in top))
    return hits / len(expected)


def answer_correctness(answer: str, must_contain: Sequence[str]) -> float | None:
    """Fraction of required phrases present in `answer` (None if none required)."""
    if not must_contain:
        return None
    haystack = normalize(answer)
    hits = sum(1 for phrase in must_contain if normalize(phrase) in haystack)
    return hits / len(must_contain)


def score_query(gold: GoldQuery, result: RetrievedAnswer, *, k: int) -> dict[str, float | None]:
    """Score one query → doc_recall@k, fact_recall@k, answer_correctness."""
    return {
        "doc_recall": recall_at_k(gold.expected_doc_ids, result.doc_ids, k),
        "fact_recall": recall_at_k(gold.expected_fact_substrings, result.facts, k),
        "answer_correctness": answer_correctness(result.answer, gold.answer_contains),
    }


def _mean_ignoring_none(values: Sequence[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return mean(present) if present else None


def score_dataset(
    gold: Sequence[GoldQuery],
    results: dict[str, RetrievedAnswer],
    *,
    k: int = 5,
) -> dict:
    """Aggregate per-query scores into per-type and overall means.

    `results` maps gold-query id → RetrievedAnswer (a missing id scores against an
    empty answer, i.e. counts as a miss). Returns
    ``{"overall": {...}, "by_type": {type: {...}}, "k": k, "n": len(gold)}``.
    """
    per_metric: dict[str, list[float | None]] = {
        "doc_recall": [], "fact_recall": [], "answer_correctness": []
    }
    by_type: dict[str, dict[str, list[float | None]]] = {}

    for query in gold:
        result = results.get(query.id, RetrievedAnswer())
        scores = score_query(query, result, k=k)
        bucket = by_type.setdefault(query.type, {m: [] for m in per_metric})
        for metric, value in scores.items():
            per_metric[metric].append(value)
            bucket[metric].append(value)

    return {
        "k": k,
        "n": len(gold),
        "overall": {m: _mean_ignoring_none(v) for m, v in per_metric.items()},
        "by_type": {
            t: {m: _mean_ignoring_none(v) for m, v in metrics.items()}
            for t, metrics in by_type.items()
        },
    }
