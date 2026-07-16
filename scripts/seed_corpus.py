"""Seed a retrieval eval corpus: ingest `storage/samples/*` through the real pipeline.

Each sample file is content-addressed, persisted, and run through the **live**
OCR → extraction → embedding chain (real Vision + DeepSeek + bge), exactly as a
web upload would be — so afterwards the documents are `indexed`/`needs_review`
and searchable. Idempotent: re-running dedups on content hash and re-drives any
document that didn't reach a terminal state.

    python -m scripts.seed_corpus                       # → Personal account
    python -m scripts.seed_corpus --account-name "Acme Inc"
    python -m scripts.seed_corpus --account <uuid>

Prints a filename → document-id → status → fact-count table; use those ids in the
CLI (`python -m scripts.retrieve`) or the gold map for the eval runner.
"""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import Account, Document, DocumentFact, User
from app.db.session import SessionLocal
from app.services import ocr
from app.services.events import record_event
from app.services.storage import save_stream
from scripts.seed import DEV_USER_EMAIL

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "storage" / "samples"

_MIME_BY_EXT = {
    ".pdf": ocr.PDF_MIME,
    ".docx": ocr.DOCX_MIME,
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _resolve_account(db, *, account_id: str | None, account_name: str | None) -> Account:
    if account_id:
        account = db.get(Account, uuid.UUID(account_id))
        if account is None:
            raise SystemExit(f"No account with id {account_id}")
        return account
    if account_name:
        account = db.scalar(select(Account).where(Account.name == account_name))
        if account is None:
            raise SystemExit(f"No account named {account_name!r} (run scripts.seed first)")
        return account
    account = db.scalar(select(Account).where(Account.type == "personal"))
    if account is None:
        raise SystemExit("No personal account found — run `python -m scripts.seed` first.")
    return account


def _sample_files() -> list[Path]:
    if not SAMPLES_DIR.is_dir():
        raise SystemExit(f"No samples directory at {SAMPLES_DIR}")
    return sorted(
        p for p in SAMPLES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in _MIME_BY_EXT
    )


def _ingest_one(account_id: uuid.UUID, uploaded_by: uuid.UUID | None, path: Path) -> uuid.UUID:
    """Persist + register one file at `received`; return its document id (deduped)."""
    mime = _MIME_BY_EXT[path.suffix.lower()]
    ext = ocr.extension_for(mime, path.name)
    settings = get_settings()
    with path.open("rb") as fh:
        stored = save_stream(
            fh, account_id, ext, max_bytes=settings.max_upload_mb * 1024 * 1024
        )

    with SessionLocal() as db:
        existing = db.scalar(
            select(Document).where(
                Document.account_id == account_id,
                Document.file_hash == stored.file_hash,
            )
        )
        if existing is not None:
            return existing.id
        document = Document(
            account_id=account_id,
            uploaded_by=uploaded_by,
            source="web_upload",
            original_filename=path.name,
            mime_type=mime,
            byte_size=stored.byte_size,
            file_hash=stored.file_hash,
            storage_path=stored.storage_path,
            status="received",
        )
        db.add(document)
        db.flush()
        record_event(
            db, account_id=account_id, document_id=document.id,
            stage="received", status="succeeded",
            detail={"source": "seed_corpus", "byte_size": stored.byte_size},
        )
        db.commit()
        return document.id


def _status_and_facts(account_id: uuid.UUID, doc_id: uuid.UUID) -> tuple[str, int]:
    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        count = db.scalar(
            select(func.count())
            .select_from(DocumentFact)
            .where(
                DocumentFact.account_id == account_id,
                DocumentFact.document_id == doc_id,
            )
        ) or 0
        return (doc.status if doc else "missing"), count


_TERMINAL = frozenset({"indexed", "needs_review"})


def seed_corpus(*, account_id: str | None, account_name: str | None) -> None:
    with SessionLocal() as db:
        account = _resolve_account(db, account_id=account_id, account_name=account_name)
        user = db.scalar(select(User).where(User.email == DEV_USER_EMAIL))
        acct_id, uploaded_by = account.id, (user.id if user else None)
        acct_name = account.name

    files = _sample_files()
    print(f"Ingesting {len(files)} sample(s) into account {acct_id} ({acct_name})\n")

    rows = []
    for path in files:
        doc_id = _ingest_one(acct_id, uploaded_by, path)
        status, _ = _status_and_facts(acct_id, doc_id)
        # Drive (or re-drive) the full chain synchronously; run_ocr chains
        # extraction → embedding. Idempotent if already processed.
        if status not in _TERMINAL:
            print(f"  · processing {path.name} … (live Vision/DeepSeek/bge)")
            ocr.run_ocr(doc_id, acct_id)
        status, facts = _status_and_facts(acct_id, doc_id)
        rows.append((path.name, doc_id, status, facts))

    width = max((len(n) for n, *_ in rows), default=8)
    print(f"\n{'file':<{width}}  {'document_id':<36}  {'status':<12}  facts")
    print("-" * (width + 60))
    for name, doc_id, status, facts in rows:
        print(f"{name:<{width}}  {str(doc_id):<36}  {status:<12}  {facts}")
    print(f"\nDone. Query with:  python -m scripts.retrieve --account {acct_id} \"<question>\"")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the retrieval eval corpus.")
    parser.add_argument("--account", help="target account UUID")
    parser.add_argument("--account-name", help="target account by name (e.g. 'Personal')")
    args = parser.parse_args()
    seed_corpus(account_id=args.account, account_name=args.account_name)


if __name__ == "__main__":
    main()
