"""Fire a retrieval query from the CLI and inspect the ranked facts — the rating loop.

    python -m scripts.retrieve "How much did I spend at Blue Fern Cafe?"
    python -m scripts.retrieve --account <uuid> --k 8 "parties to the NDA"

Prints the routed intent, per-source counts, and the top-k facts with their
document, page, fusion score, and which retriever found them — so you can judge
retrieval quality directly and tell me what to improve. No synthesis yet (Step 4).
"""

from __future__ import annotations

import argparse
import uuid

from sqlalchemy import select

from app.db.models import Account, Document
from app.db.session import SessionLocal
from app.services.retrieval import retrieve


def _resolve_account_id(account: str | None) -> uuid.UUID:
    with SessionLocal() as db:
        if account:
            try:
                return db.get(Account, uuid.UUID(account)).id  # type: ignore[union-attr]
            except (ValueError, AttributeError):
                acc = db.scalar(select(Account).where(Account.name == account))
                if acc is None:
                    raise SystemExit(f"No account matching {account!r}")
                return acc.id
        acc = db.scalar(select(Account).where(Account.type == "personal"))
        if acc is None:
            raise SystemExit("No personal account — run `python -m scripts.seed` first.")
        return acc.id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a retrieval query.")
    parser.add_argument("query", help="the natural-language question")
    parser.add_argument("--account", help="account UUID or name (default: Personal)")
    parser.add_argument("--k", type=int, default=5, help="number of facts to return")
    args = parser.parse_args()

    account_id = _resolve_account_id(args.account)
    result = retrieve(args.query, account_id, k=args.k)

    counts = result.plan["counts"]
    print(f"\nQ: {result.query}")
    print(f"intent: {result.intent}   sources: "
          f"vector={counts['vector']} lexical={counts['lexical']} "
          f"structured={counts['structured']} → merged={counts['merged']}")

    # Resolve document titles for readable output.
    titles: dict[uuid.UUID, str] = {}
    with SessionLocal() as db:
        for doc_id in result.doc_ids:
            doc = db.get(Document, doc_id)
            titles[doc_id] = (doc.title or doc.original_filename) if doc else str(doc_id)

    if not result.facts:
        print("\n  (no facts retrieved)\n")
        return

    print(f"\nTop {len(result.facts)} facts:")
    for i, hit in enumerate(result.facts, 1):
        loc = f"p{hit.page}" if hit.page is not None else "—"
        title = titles.get(hit.document_id, str(hit.document_id))
        print(f"\n{i:>2}. [{hit.score:.4f} · {hit.source:<10} · {loc:>4}] {title}")
        print(f"    {hit.text}")
    print()


if __name__ == "__main__":
    main()
