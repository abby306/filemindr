"""Interactive multi-turn chat — the conversational rating loop.

    python -m scripts.chat                      # new chat (Personal account)
    python -m scripts.chat --conversation <id>  # continue a previous chat
    python -m scripts.chat --account "Acme Inc"

Type questions; the agent answers with citations and remembers the conversation,
so you can refine ("no, the other contract", "just the 2024 ones") or reference a
document by class / name / upload time. The conversation id is printed so you can
resume later. Type 'exit' (or Ctrl-D) to quit. Calls the live Gemini API.
"""

from __future__ import annotations

import argparse
import uuid

from sqlalchemy import select

from app.db.models import Account
from app.db.session import SessionLocal
from app.services.conversations import chat


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
    parser = argparse.ArgumentParser(description="Interactive grounded chat.")
    parser.add_argument("--account", help="account UUID or name (default: Personal)")
    parser.add_argument("--conversation", help="continue an existing conversation id")
    args = parser.parse_args()

    account_id = _resolve_account_id(args.account)
    convo_id = uuid.UUID(args.conversation) if args.conversation else None

    print("Filemindr chat — ask about your documents. Type 'exit' to quit.\n")
    while True:
        try:
            q = input("you > ").strip()
        except EOFError:
            break
        if not q:
            continue
        if q.lower() in {"exit", "quit"}:
            break

        result, convo_id, _ = chat(account_id, q, conversation_id=convo_id)
        print(f"\nbot > {result.answer}")
        flags = "supported" if result.supported else "NOT supported"
        meta = (f"[{flags} · {len(result.searches)} searches · "
                f"{len(result.documents_looked_up)} doc-lookups · "
                f"{result.prompt_tokens}+{result.completion_tokens} tok · {result.latency_ms}ms]")
        print(meta)
        if result.citations:
            cites = "; ".join(
                f"{(c.title or str(c.document_id))}" + (f" p{c.page}" if c.page else "")
                for c in result.citations
            )
            print(f"sources: {cites}")
        print()

    print(f"\nconversation id: {convo_id}  (resume with --conversation {convo_id})")


if __name__ == "__main__":
    main()
