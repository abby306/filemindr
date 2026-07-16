"""Re-drive documents stuck in a non-terminal or failed state.

`BackgroundTasks` don't survive a restart, so a document can be parked mid-
pipeline; `failed` docs have no automatic retry. This sweep re-invokes the
idempotent background entry points from the right point for each status. Run:

    python -m scripts.reprocess                       # default stuck statuses
    python -m scripts.reprocess --statuses failed,ocr_done
    python -m scripts.reprocess --account <uuid>
"""

from __future__ import annotations

import argparse
import uuid

from app.services.reprocessing import reprocess_stuck


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-drive stuck/failed documents.")
    parser.add_argument(
        "--statuses",
        help="comma-separated statuses to sweep "
        "(default: received,ocr_done,extracted,failed)",
    )
    parser.add_argument("--account", help="limit the sweep to one account UUID")
    args = parser.parse_args()

    statuses = [s.strip() for s in args.statuses.split(",")] if args.statuses else None
    account_id = uuid.UUID(args.account) if args.account else None

    summary = reprocess_stuck(account_id=account_id, statuses=statuses)
    if not summary:
        print("No documents to reprocess.")
        return
    for entry, count in sorted(summary.items()):
        print(f"{entry}: {count}")


if __name__ == "__main__":
    main()
