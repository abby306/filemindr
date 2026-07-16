"""Ask a question and get a grounded, cited answer — the synthesis rating loop.

    python -m scripts.ask "How much did I spend at Blue Fern Cafe?"
    python -m scripts.ask --account <uuid> "What is the invoice total?"

Shows the agent's answer, whether it was supported, the citations (document +
page), any follow-up searches the LLM issued, and token usage — so you can judge
both the answer and how the agent got there. Calls the live Gemini API.
"""

from __future__ import annotations

import argparse
import uuid

from sqlalchemy import select

from app.db.models import Account
from app.db.session import SessionLocal
from app.services.synthesis import synthesize


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask a grounded question.")
    parser.add_argument("query", help="the natural-language question")
    parser.add_argument("--account", help="account UUID or name (default: Personal)")
    args = parser.parse_args()

    account_id = _resolve_account_id(args.account)
    result = synthesize(args.query, account_id)

    mark = "✓ supported" if result.supported else "✗ NOT supported"
    print(f"\nQ: {result.query}")
    print(f"\nA: {result.answer}\n")
    print(f"[{mark} · intent={result.intent} · candidates seen={result.candidates_seen}"
          f" · {result.prompt_tokens}+{result.completion_tokens} tok · {result.latency_ms}ms]")

    if result.searches:
        print("\nfollow-up searches the agent issued:")
        for s in result.searches:
            print(f"   · {s}")

    if result.citations:
        print("\ncitations:")
        for c in result.citations:
            loc = f"p{c.page}" if c.page is not None else "—"
            print(f"   · {c.title or c.document_id} ({loc})")
    print()


if __name__ == "__main__":
    main()
