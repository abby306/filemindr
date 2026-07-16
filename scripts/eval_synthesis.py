"""Score the live synthesis agent against the gold set (answer_correctness).

Sibling of `scripts.eval_retrieval`: same slug→document mapping, but the adapter runs
the full agentic answer (`synthesize`) instead of bare retrieval, so the eval finally
exercises **answer_correctness** alongside doc/fact recall. Citations supply the
retrieved doc ids + fact texts; `result.answer` is scored against `answer_contains`.

    python -m scripts.seed_corpus          # ingest the corpus first (live)
    python -m scripts.eval_synthesis       # → Personal account, gold/seed.yaml
    python -m scripts.eval_synthesis --k 5 --doc-map eval/gold/doc_map.yaml

Live Gemini (and possible GPT-4o escalation) — not part of the offline test suite.
"""

from __future__ import annotations

import argparse
import uuid

from app.services.synthesis import synthesize
from eval.run import GOLD_PATH, print_report, run_eval
from eval.schema import RetrievedAnswer, load_gold
from scripts.eval_retrieval import _auto_map, _load_override, _resolve_account_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Score live synthesis vs the gold set.")
    parser.add_argument("--account", help="account UUID or name (default: Personal)")
    parser.add_argument("--k", type=int, default=5, help="top-k cutoff for recall")
    parser.add_argument("--gold", default=str(GOLD_PATH))
    parser.add_argument("--doc-map", help="YAML override of slug → document UUID")
    args = parser.parse_args()

    account_id = _resolve_account_id(args.account)
    gold = load_gold(args.gold)

    wanted = {slug for q in gold for slug in q.expected_doc_ids}
    mapping = _auto_map(account_id, wanted)
    mapping.update(_load_override(args.doc_map))  # explicit pins win
    uuid_to_slug = {v: k for k, v in mapping.items()}

    print(f"\nslug → document map (account {account_id}):")
    for slug in sorted(wanted):
        print(f"  {slug:<28} → {mapping.get(slug, 'UNMAPPED')}")

    def adapter(query: str) -> RetrievedAnswer:
        result = synthesize(query, account_id)
        doc_ids = [uuid_to_slug.get(c.document_id, str(c.document_id)) for c in result.citations]
        flag = "GPT-4o" if result.escalated else "flash"
        print(f"  · [{flag}] {query[:48]!r:50} supported={result.supported}")
        return RetrievedAnswer(
            doc_ids=doc_ids,
            facts=[c.title or str(c.document_id) for c in result.citations],
            answer=result.answer,
        )

    scores = run_eval(adapter, gold, k=args.k)
    print_report(scores)


if __name__ == "__main__":
    main()
