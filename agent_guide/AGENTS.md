# AGENTS.md

Rules for AI agents (Claude Code, Antigravity) working in this repo.
Keep this file small and additive — add a rule, don't rewrite the section.

## Read first
1. `setup.md` — current machine + environment (native stack, connections, what's deferred).
2. `PRD.md` → `ARCHITECTURE.md` → `TECH_SPEC.md` for scope and design.
3. `TASKS.md` before starting work; `CODING_STANDARDS.md` before writing code.
4. `FRONTEND.md` before any UI work — design tokens and per-screen specs (no inventing colors/radii/motion).

## Golden rules
- **Do not commit secrets.** `.env` and `secrets/` are git-ignored. Never hardcode keys.
- **This phase is native, not Docker.** Don't start containers or assume them (see `setup.md`).
- **Ask before destructive DB ops** (DROP, TRUNCATE, destructive migrations). Prefer additive Alembic migrations.
- **Stay account-scoped.** Every query filters by `account_id`. Never write a query that can cross accounts.
- **Provenance is mandatory.** Anything that produces facts/answers carries page (+ bbox when available) and citations.
- **Keep the docs in sync.** If you change schema, endpoints, or conventions, update `TECH_SPEC.md` / `API_CONTRACTS.md` / `TASKS.md` in the same change.

## Workflow
- Read context → state a short plan → implement in small, reviewable commits.
- Match an existing pattern before inventing a new one. Keep modules in their `app/` home (`api`, `core`, `db`, `services`, `workers`).
- Write/extend tests for new logic. Update `TASKS.md` (move items Done / add follow-ups).
- Prefer clarity over cleverness; leave the codebase easy to evolve.

## Model routing (developer's coding agents)
- **Gemini Flash** — trivial/mechanical edits, renames, boilerplate.
- **Claude Sonnet** — significant implementation work.
- **Claude Opus** — hardest reasoning: architecture, tricky debugging, retrieval tuning.
- This is about *who writes the code*. The **app's runtime models** (OCR/extraction/embeddings) are defined in `TECH_SPEC.md` — don't conflate them.

## Guardrails on cost & RAM
- 8 GB machine: don't spawn heavy parallel processes; assume one Electron IDE open.
- App-side: cheap model for extraction, strong model only for synthesis/hard cases; local embeddings. Don't "upgrade" a model tier without noting it in `TECH_SPEC.md`.
