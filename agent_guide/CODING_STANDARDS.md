# CODING_STANDARDS.md — filemindr

Conventions the codebase already follows. Read before writing code; match the
surrounding style over any personal preference.

## Python style
- **Python 3.12**, PEP 8, 4-space indent. Keep lines readable (~100 cols).
- Start every module with `from __future__ import annotations`.
- **Type-hint** all function signatures and dataclass fields. Use modern syntax
  (`str | None`, `list[str]`, `dict`), not `Optional`/`List`.
- **Docstrings** on every module, public function, and class: a one-line summary,
  then a short paragraph on intent/contract when it isn't obvious. Explain *why*,
  not the line-by-line *what*.
- Use **`pathlib.Path`**, never `os.path` string-joining (`os` is fine for
  `os.replace`). Prefer f-strings.
- Keep imports ordered stdlib → third-party → first-party (`app.*`, `eval.*`),
  each group blank-line separated.
- Module-level constants are `UPPER_SNAKE`; private helpers are `_prefixed`.

## Architecture & boundaries
- **Account scoping is mandatory.** Every account-scoped read/write goes through
  `AccountScope` (`app/core/scoping.py`) or filters `account_id` explicitly.
  Background entry points take `account_id` and refuse cross-account work.
- **One seam per external dependency.** Wrap each network/model/filesystem
  dependency behind a single function so tests can stub it: e.g.
  `call_extraction_model` (DeepSeek), `_vision_ocr_image_bytes` (Vision),
  `embeddings._encode` (bge), `storage.get_storage_root` (FS). Never call a
  provider SDK from two places.
- **Lazy, guarded singletons** for expensive clients/models (Vision client, bge
  model). Import the heavy library *inside* the loader so module import stays
  cheap; guard concurrent init with a lock when relevant.
- **Background entry points are idempotent** (`run_ocr`, `run_extraction`,
  `run_embedding`): they open their own `SessionLocal`, are safe to re-run, log a
  `processing_events` row, and on failure set the document `failed` rather than
  raising out of the task. Re-running overwrites; it never appends duplicates.
- **DB writes stay serial** on the task's own session; never share a SQLAlchemy
  session across threads. Parallelize only the network phase (`map_bounded`).
- **Resilience:** wrap transient network calls in `with_retry` with a provider
  `is_retryable` predicate; tolerate partial failures (skip + record) rather than
  failing a whole multi-unit document when only one unit fails.

## Data & schema
- **Alembic owns all DDL.** Never `Base.metadata.create_all()`. Schema changes are
  new, additive migrations; ask before anything destructive. Keep `schema.sql`
  (the canonical reference) in sync with migrations.
- ORM models map onto existing tables only. Vector columns are `vector(768)`.
- Store numbers as typed values (`value_numeric`) so aggregates are SQL, not LLM.

## Errors & config
- All settings come from `Settings`/`get_settings()` (`app/core/config.py`); read
  config through it, never `os.environ` directly. Secrets live in `.env` only.
- API errors raise `HTTPException(detail={"code", "message"})` (consistent across
  the app). Keep new endpoints to that shape.

## Tests
- `pytest`, run against the **live local Postgres**. Keep the suite **offline and
  deterministic**: mock every network/model seam (DeepSeek, Vision, bge). No live
  API calls, no model downloads in CI.
- Use the `db` fixture (rolls back) for unit work; `seeded_account` (commits, then
  cascade-deletes) for anything that must persist across sessions.
- Prefer pure, unit-tested functions for logic (routing, parsing, scoring,
  chunking, merging); cover idempotency, account isolation, and failure paths.
- Name tests by behaviour (`test_<thing>_<expectation>`); add a one-line docstring
  when the intent isn't obvious from the name.

## Commits
- Small, focused commits; conventional prefixes (`feat`, `fix`, `perf`, `docs`,
  `refactor`). Run the full suite before committing. Co-author trailer as
  configured. Never commit secrets, `storage/`, or real document samples.
