# Contributing to Filemindr

Thanks for considering a contribution! This project is small and opinionated;
a few ground rules keep it that way.

## Before you write code

1. Read [`agent_guide/AGENTS.md`](agent_guide/AGENTS.md) and
   [`agent_guide/CODING_STANDARDS.md`](agent_guide/CODING_STANDARDS.md) — they
   are short and they are the law of the repo.
2. For anything non-trivial, open an issue first so we agree on the approach
   before you invest time.

## The invariants (PRs that break these will be asked to change)

- **Account scoping is mandatory.** Every account-scoped read/write goes
  through `AccountScope` or filters `account_id` explicitly.
- **Alembic owns all DDL.** Schema changes are new, additive migrations —
  never `Base.metadata.create_all()`, and keep `schema.sql` in sync.
- **One seam per external dependency.** Each network/model call lives behind a
  single function that tests can stub. Never call a provider SDK from two places.
- **The test suite stays offline and deterministic.** Mock every network/model
  seam; no live API calls, no model downloads in CI.
- **The web app is a pure thin client.** Derived values are computed
  server-side; the client renders what the API sends.
- **Provenance is mandatory.** Anything producing facts/answers carries page
  (+ bbox when available) and citations.

## Workflow

```bash
# backend
source .venv/bin/activate
pytest -q                      # must be green

# web
cd web && npm run build && npm run lint   # must be clean
```

- Small, focused commits with conventional prefixes (`feat`, `fix`, `docs`,
  `refactor`, `test`).
- Write or extend tests for new logic — cover idempotency, account isolation,
  and failure paths.
- If you change schema, endpoints, or conventions, update
  `agent_guide/TECH_SPEC.md` / `API_CONTRACTS.md` in the same PR.

## Reporting bugs

Open an issue with: what you did, what you expected, what happened, and the
relevant log lines (scrub anything personal — this is a document tool, logs
can contain your documents).
