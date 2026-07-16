"""Score the live retrieval engine against the gold set.

Bridges `app.services.retrieval.retrieve` (returns real document UUIDs) to the
eval scorers (expect gold *slugs*) by mapping each gold slug to a seeded document:
token-overlap of the slug against each document's title / filename / summary,
best match wins. The mapping is printed so you can sanity-check it, and can be
pinned with an explicit YAML override (`slug: <document-uuid>`).

    python -m scripts.seed_corpus          # ingest the corpus first
    python -m scripts.eval_retrieval       # → Personal account, gold/seed.yaml
    python -m scripts.eval_retrieval --k 3 --doc-map eval/gold/doc_map.yaml

`answer_correctness` will read low until synthesis (Step 4) — doc_recall and
fact_recall are the metrics to watch right now.
"""

from __future__ import annotations

import argparse
import re
import uuid
from pathlib import Path

import yaml
from sqlalchemy import select

from app.db.models import Account, Document
from app.db.session import SessionLocal
from app.services.retrieval import retrieve
from eval.run import GOLD_PATH, print_report, run_eval
from eval.schema import RetrievedAnswer, load_gold


def _resolve_account_id(account: str | None) -> uuid.UUID:
    with SessionLocal() as db:
        if account:
            acc = db.scalar(select(Account).where(Account.name == account))
            if acc is None:
                try:
                    acc = db.get(Account, uuid.UUID(account))
                except ValueError:
                    acc = None
            if acc is None:
                raise SystemExit(f"No account matching {account!r}")
            return acc.id
        acc = db.scalar(select(Account).where(Account.type == "personal"))
        if acc is None:
            raise SystemExit("No personal account — run `python -m scripts.seed` first.")
        return acc.id


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) > 1}


def _auto_map(account_id: uuid.UUID, slugs: set[str]) -> dict[str, uuid.UUID]:
    """Map each gold slug to the best-matching document by token overlap."""
    with SessionLocal() as db:
        docs = db.scalars(
            select(Document).where(Document.account_id == account_id)
        ).all()
    mapping: dict[str, uuid.UUID] = {}
    for slug in slugs:
        slug_tokens = _tokens(slug)
        best, best_score = None, 0
        for doc in docs:
            haystack = _tokens(
                f"{doc.title or ''} {doc.original_filename or ''} {doc.summary or ''}"
            )
            score = len(slug_tokens & haystack)
            if score > best_score:
                best, best_score = doc.id, score
        if best is not None:
            mapping[slug] = best
    return mapping


def _load_override(path: str | None) -> dict[str, uuid.UUID]:
    if not path or not Path(path).exists():
        return {}
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return {slug: uuid.UUID(str(doc_id)) for slug, doc_id in raw.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Score live retrieval vs the gold set.")
    parser.add_argument("--account", help="account UUID or name (default: Personal)")
    parser.add_argument("--k", type=int, default=5)
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
        result = retrieve(query, account_id, k=args.k)
        doc_ids = [uuid_to_slug.get(d, str(d)) for d in result.doc_ids]
        return RetrievedAnswer(
            doc_ids=doc_ids,
            facts=[hit.text for hit in result.facts],
            answer="",  # synthesis is Step 4
        )

    scores = run_eval(adapter, gold, k=args.k)
    print_report(scores)


if __name__ == "__main__":
    main()
