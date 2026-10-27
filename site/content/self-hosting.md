---
title: "Self-Hosting Filemindr: Deployment and Security Guide"
nav_title: Self-hosting
description: "How to self-host Filemindr on your own server: services, process management, reverse proxy, storage, backups and the security limits to address first."
---

# Self-hosting Filemindr

Filemindr is designed to be self-hosted: one FastAPI process, one PostgreSQL database with pgvector, and a Next.js app, on a single Linux server. This guide covers moving from the [local setup](getting-started.md) to a server you keep running. **Read the security section before exposing anything to the internet.**

## What "self-hosted" means here

| Runs on your server | Calls hosted APIs |
|---|---|
| PostgreSQL 16 + pgvector (all data, vectors, full-text index) | DeepSeek or another OpenAI-compatible endpoint: structured extraction (required) |
| FastAPI backend and background pipeline | Google Gemini: answers (required for chat) |
| `bge-base-en-v1.5` embeddings and `bge-reranker-base` reranker (CPU) | Google Cloud Vision: OCR of scans and images (only if you upload them) |
| Uploaded files and OCR cache (`STORAGE_DIR`) | OpenAI GPT-4o: optional escalation |

So Filemindr is **self-hostable, not air-gapped**: document text is sent to the providers in the right-hand column. If that's unacceptable for your documents, Filemindr isn't the right fit today. See the [FAQ](faq.md).

## Sizing

The two local models need roughly 400 MB of RAM once loaded, on top of PostgreSQL, Python and Node. The project is developed on an 8 GB laptop. Embedding and reranking run on CPU, so no GPU is needed. Disk usage is your documents plus the OCR cache plus PostgreSQL (768 floats per fact).

## Services

1. **PostgreSQL 16 + pgvector.** Install natively (PGDG `postgresql-16-pgvector`) or run the `db` service from `docker-compose.yaml` (`pgvector/pgvector:pg16`). Set a real password: the compose file reads `POSTGRES_PASSWORD`.
2. **Backend.** Create the venv, `pip install -r requirements.txt`, `alembic upgrade head`, then run Uvicorn under a process manager (systemd or similar):

   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

   Set `APP_ENV=production`, which also disables the dev-only `/dev` UI mount, and `WARMUP_MODELS=true` if you have the memory.
3. **Web app.** `npm ci && npm run build && npm run start`. In production, set `NEXT_PUBLIC_API_ORIGIN` to the backend's public origin, and add that web origin to the backend's `CORS_ORIGINS`.
4. **Reverse proxy.** Put both behind nginx or Caddy with TLS. Allow upload bodies of at least `MAX_UPLOAD_MB`, and disable response buffering for the SSE route (`/api/v1/conversations/*/messages/stream`) so answers stream.

## Security checklist

- [ ] **Replace or front the auth.** The bundled bearer token is the user's UUID and is meant for development. Implement real authentication at `app/core/auth.py::get_current_user` (the single seam every route depends on), or put the instance behind an authenticating proxy or VPN.
- [ ] **Never commit secrets.** `.env` and `secrets/` are git-ignored; keep it that way. Use a service account with only the Vision permission.
- [ ] **Encrypt at rest** at the disk or volume level. Filemindr stores files, OCR text and facts unencrypted.
- [ ] **Restrict the database** to localhost or a private network.
- [ ] **Review provider data policies** for DeepSeek, Google (Gemini, Vision) and OpenAI against the documents you plan to upload.

Security issues in Filemindr itself: please report them privately (see [`SECURITY.md`](https://github.com/abby306/filemindr/blob/main/SECURITY.md)).

## Operations

- **Health check:** `GET /health` returns 200 only if the database answers `SELECT 1`, so it's suitable for uptime monitors.
- **Restarts:** in-flight pipeline jobs are lost on restart. Run `python -m scripts.reprocess` afterwards to re-drive documents stuck in `received` / `ocr_done`.
- **Debugging a document:** `SELECT * FROM processing_events WHERE document_id = '…' ORDER BY created_at;`
- **Debugging an answer:** look at the matching `retrieval_traces` row (plan, candidates, tokens, latency).
- **Upgrades:** `git pull`, `pip install -r requirements.txt`, `alembic upgrade head`, rebuild the web app, restart.
- **Backups:** back up PostgreSQL (`pg_dump`) **and** `STORAGE_DIR`, which holds the original files and the OCR cache, together.

## Quotas and billing

Plan quotas are **off** by default (`ENFORCE_QUOTAS=false`), so a self-hosted install is unlimited. Usage is still metered for the analytics screen. The billing endpoints are a mock with a Stripe-shaped seam, and the Billing screen is hidden unless `NEXT_PUBLIC_ENABLE_BILLING=1`.

Related: [Configuration](configuration.md) · [Architecture](architecture.md)
