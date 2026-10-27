## What and why

<!-- One or two sentences. Link the issue if there is one. -->

## Checklist

- [ ] `pytest -q` passes (offline — no live API calls, no model downloads)
- [ ] `cd web && npm run build && npm run lint` is clean (if the web app changed)
- [ ] Every new query is account-scoped (`AccountScope` or an explicit `account_id` filter)
- [ ] Schema changes are a new Alembic migration, and `schema.sql` is in sync
- [ ] Anything producing facts or answers keeps provenance (page, bbox where available, citations)
- [ ] Docs updated if behaviour, endpoints or configuration changed (`agent_guide/`, `site/content/`)
- [ ] No secrets, `.env` values or personal document content in the diff
