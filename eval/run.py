"""Eval runner: score a retrieval callable against the gold set.

    python -m eval.run                 # runs the built-in stub (fixtures)
    python -m eval.run --k 3

Phase 5 wiring: pass any ``retrieve(query: str) -> RetrievedAnswer`` to
`run_eval`. The real engine's ``retrieve(query, account_id)`` is adapted by
binding the eval account id (see eval/README.md); nothing else changes.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from eval.schema import GoldQuery, RetrievedAnswer, load_gold
from eval.scorers import score_dataset

GOLD_PATH = Path(__file__).resolve().parent / "gold" / "seed.yaml"

Retrieve = Callable[[str], RetrievedAnswer]


def run_eval(retrieve: Retrieve, gold: list[GoldQuery], *, k: int = 5) -> dict:
    """Run `retrieve` over every gold query and score the results."""
    results = {query.id: retrieve(query.query) for query in gold}
    return score_dataset(gold, results, k=k)


def _fmt(value: float | None) -> str:
    return "  n/a" if value is None else f"{value:5.2f}"


def print_report(scores: dict) -> None:
    """Pretty-print per-type and overall scores."""
    header = f"{'group':<12} {'doc_recall':>11} {'fact_recall':>12} {'answer':>8}"
    print(f"\nRetrieval eval — n={scores['n']} queries, k={scores['k']}")
    print(header)
    print("-" * len(header))
    for type_, metrics in sorted(scores["by_type"].items()):
        print(
            f"{type_:<12} {_fmt(metrics['doc_recall']):>11} "
            f"{_fmt(metrics['fact_recall']):>12} {_fmt(metrics['answer_correctness']):>8}"
        )
    o = scores["overall"]
    print("-" * len(header))
    print(
        f"{'OVERALL':<12} {_fmt(o['doc_recall']):>11} "
        f"{_fmt(o['fact_recall']):>12} {_fmt(o['answer_correctness']):>8}\n"
    )


# --- built-in stub retrieval (fixtures, so the runner works offline) --------
# Derived from the gold set itself — the stub demos the *scoring plumbing*, not
# retrieval, and deriving it means a gold refresh can't strand it. One semantic
# query is deliberately degraded so the scores stay non-trivial.
_DEGRADED_QUERY_ID = "garden_model"


def _stub_fixtures() -> dict[str, RetrievedAnswer]:
    fixtures: dict[str, RetrievedAnswer] = {}
    for gold_query in load_gold(GOLD_PATH):
        facts = list(gold_query.expected_fact_substrings)
        if gold_query.id == _DEGRADED_QUERY_ID:
            facts = ["The model is a recurrent neural network."]  # deliberate miss
        fixtures[gold_query.query] = RetrievedAnswer(
            doc_ids=list(gold_query.expected_doc_ids),
            facts=facts,
            answer=" ".join(gold_query.answer_contains),
        )
    return fixtures


def _stub_retrieve(query: str) -> RetrievedAnswer:
    return _stub_fixtures().get(query, RetrievedAnswer())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the retrieval eval.")
    parser.add_argument("--k", type=int, default=5, help="top-k cutoff for recall")
    parser.add_argument("--gold", default=str(GOLD_PATH), help="path to a gold YAML file")
    args = parser.parse_args()

    gold = load_gold(args.gold)
    scores = run_eval(_stub_retrieve, gold, k=args.k)
    print_report(scores)


if __name__ == "__main__":
    main()
