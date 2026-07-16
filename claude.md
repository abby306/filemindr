# CLAUDE.md

This project is governed by a small set of docs. **Read them before acting:**

- `AGENTS.md` — rules, golden constraints, workflow, model routing. (Start here.)
- `setup.md` — current machine + environment (native Postgres 16 + pgvector + Redis, pyenv 3.12 venv, connections).
- `PRD.md` → `ARCHITECTURE.md` → `TECH_SPEC.md` — scope, design, schema.
- `CODING_STANDARDS.md` — style and engineering practices (follow exactly).
- `API_CONTRACTS.md` — endpoint shapes. `FRONTEND.md` — design tokens + screen specs (UI work).
- `TASKS.md` — live backlog; update it as you work.

Non-negotiables (full list in `AGENTS.md`): never commit secrets; every query is `account_id`-scoped; provenance + citations are mandatory; migrations via Alembic only; keep the docs in sync with code.

The database schema is already applied (`schema.sql` / `alembic/versions/0001_initial_schema.py`) at `vector(768)` for `bge-base-en-v1.5`. Do not recreate tables — map to them.