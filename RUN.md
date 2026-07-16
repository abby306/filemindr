# RUN.md — running Filemindr on localhost

Day-to-day "start it up" guide for a machine that's already set up (Postgres +
pgvector installed, Python venv created, Node installed, `.env`/secrets in
place). For a **from-scratch install** on a new machine, see
[`README.md`](README.md#quickstart-native-no-docker) and
[`agent_guide/setup.md`](agent_guide/setup.md) instead — this file assumes
that's already done.

---

## 1. One-time checks (skip if you did these before)

```bash
# Postgres is up and pgvector is installed
psql "postgresql://filemindr:localdev@localhost:5432/filemindr" \
  -c "SELECT extversion FROM pg_extension WHERE extname='vector';"

# .env exists with real keys (never commit this file)
test -f .env && echo ".env present" || echo "MISSING — copy .env.example and fill in keys"
```

`.env` needs `DATABASE_URL`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`,
`GOOGLE_APPLICATION_CREDENTIALS` (→ `secrets/vision-credentials.json`). See
`.env.example` for the full list.

**Node toolchain note:** in non-interactive shells `nvm` isn't auto-loaded, so
`node`/`npm`/`npx` must be symlinked into `~/.local/bin` pointing at
`~/.nvm/versions/node/<version>/bin`. If `node --version` fails in a fresh
shell, that's the symlink — see `agent_guide/setup.md`.

---

## 2. Start the backend (FastAPI, port 8000)

```bash
cd <repo-root>
source .venv/bin/activate
python -m scripts.seed          # idempotent — dev user + 2 accounts + system classes
uvicorn app.main:app --reload   # serves on :8000
```

Health check: `curl localhost:8000/health` → `{"status":"ok","database":"up"}`.

The dev-only testing UI (if `dev_ui/` exists — it's git-ignored) is mounted at
`localhost:8000/dev/`.

---

## 3. Start the frontend (Next.js, port 3000)

```bash
cd web
npm install     # first time only, or after a dependency change
npm run dev     # serves on :3000; /api/* rewrites to :8000
```

Open `http://localhost:3000`. Dev auth is baked into the web client (bearer +
`X-Account-Id`, see §5) — no login screen yet.

---

## 4. Run both together

Two terminals (or two background jobs):

```bash
# terminal 1
source .venv/bin/activate && uvicorn app.main:app --reload

# terminal 2
cd web && npm run dev
```

The frontend's dev server proxies `/api/*` to `:8000` via a Next.js rewrite,
so you only ever open `localhost:3000` in the browser — CORS doesn't come
into play until a prod deploy (separate origins).

---

## 5. Auth while there's no login screen

The bearer token **is** the dev user's UUID; the account is picked via a
header (the user belongs to both accounts, so it's ambiguous without one).
`python -m scripts.seed` prints all three UUIDs — put them in
`web/.env.local` (copy `web/.env.local.example`) for the web app, and use
them directly when calling the API (`curl`, Postman, `scripts/*`):

```
Authorization: Bearer <dev-user-uuid>
X-Account-Id:  <personal-account-uuid>   # or the company account UUID
```

Example:
```bash
curl -s localhost:8000/api/v1/documents \
  -H "Authorization: Bearer <dev-user-uuid>" \
  -H "X-Account-Id: <personal-account-uuid>"
```

---

## 6. Tests

```bash
source .venv/bin/activate
pytest -q                          # 252 tests, offline (all network/model seams mocked)

cd web
npm run build && npm run lint      # both must be clean
```

Tests run against your **live local Postgres** (not a separate test DB), but
never make real network calls — DeepSeek, Vision, the bge encoder/reranker,
and the Gemini + GPT-4o synthesis seams are all mocked.

---

## 7. Useful scripts (all under `python -m scripts.<name>`, venv active)

| Script | What it does |
|---|---|
| `scripts.seed` | Idempotent: dev user, 2 accounts, system classes |
| `scripts.make_demo_corpus` | Generates 8 synthetic demo PDFs into `storage/samples/` |
| `scripts.seed_corpus [--account-name Personal]` | Ingests `storage/samples/*` through the live pipeline |
| `scripts.reprocess [--statuses ...]` | Re-drives stuck/failed documents |
| `scripts.ask "<question>"` | One-shot agentic chat answer (live Gemini) |
| `scripts.chat [--conversation <id>]` | Interactive multi-turn chat |
| `scripts.retrieve "<question>"` | Retrieval-only (no synthesis), prints ranked facts |
| `scripts.eval_retrieval` | Scores retrieval vs `eval/gold/seed.yaml` |
| `scripts.eval_synthesis` | Scores full synthesis (live Gemini/GPT-4o) |

---

## 8. Common problems

- **`uvicorn` can't reach the DB** → Postgres isn't running, or `.env`'s
  `DATABASE_URL` doesn't match. `pg_isready` / `sudo systemctl status postgresql`.
- **Upload hangs on first request after a restart** → the bge embedding model
  (~400MB) and reranker lazy-load on first real use; expect ~20-30s once,
  then it's fast.
- **`node`/`npm` not found in a script/tool shell** → nvm isn't sourced
  non-interactively; use the `~/.local/bin` symlinks (see §1).
- **A background task seems stuck / doc never leaves `received`** →
  `BackgroundTasks` don't survive a server restart. Re-drive with
  `python -m scripts.reprocess`.
- **Pytest hangs with no output** → a previous stuck test run may be holding
  Postgres locks. Check `ps aux | grep pytest` and kill stragglers before
  re-running. (If you wrote a test using both `seeded_account` and `db`
  fixtures, declare them in that order — reversed, teardown deadlocks.)
