---
title: "Configuration: Environment Variables and API Keys"
nav_title: Configuration
description: "Every Filemindr setting: database, storage, pipeline workers, model warmup, quotas, CORS, and the DeepSeek, Gemini, Google Vision and OpenAI API keys."
---

# Configuration reference

The backend reads settings from environment variables or a `.env` file in the repository root (copy `.env.example`). Names are case-insensitive. The source of truth is [`app/core/config.py`](https://github.com/abby306/filemindr/blob/main/app/core/config.py). The web app reads `web/.env.local`.

> Use placeholders in anything you share. Never commit `.env`, `web/.env.local` or files under `secrets/`.

## External providers

| Variable | Default | Used for | Required? |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | *(empty)* | Structured extraction | Yes, to ingest documents |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Extraction endpoint (OpenAI-compatible) | No |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Extraction model name | No |
| `GEMINI_API_KEY` | *(empty)* | Answers (Gemini 2.5 Flash, function calling) | Yes, for chat |
| `GOOGLE_APPLICATION_CREDENTIALS` | `./secrets/vision-credentials.json` | Google Cloud Vision service account (falls back to Application Default Credentials if the file is missing) | Only for scanned PDFs and images |
| `OPENAI_API_KEY` | *(empty)* | GPT-4o escalation when an answer is unsupported | No; failures are ignored |

**Other OpenAI-compatible extraction endpoints.** Because extraction uses the OpenAI client with `response_format={"type": "json_object"}`, you can point `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` at another compatible server. This is untested beyond DeepSeek: the model needs to follow a fairly long JSON schema reliably.

## Core settings

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://filemindr:localdev@localhost:5432/filemindr` | SQLAlchemy URL (psycopg 3). Change the password for anything but local dev |
| `STORAGE_DIR` | `./storage` | Uploaded files and the OCR cache (`ocr_cache/`). Relative paths resolve from the repo root |
| `APP_ENV` | `development` | `development` mounts the optional dev UI at `/dev` if present |
| `PIPELINE_WORKERS` | `3` | Documents processed concurrently. `0` runs the pipeline inline (used by tests) |
| `MAX_PARALLEL_CALLS` | `4` | Parallel network calls per document (per-page OCR, per-chunk extraction) |
| `MAX_UPLOAD_MB` | `50` | Uploads above this are rejected with 413 |
| `RETRY_MAX_ATTEMPTS` / `RETRY_BASE_DELAY` | `3` / `0.5` | Bounded retry with backoff for transient provider errors (timeouts, 429, 5xx) |
| `WARMUP_MODELS` | `false` (`.env.example` sets `true`) | Preload the embedding and reranker models (~400 MB RAM) at startup so the first query is fast |
| `ENFORCE_QUOTAS` | `false` | Enforce plan limits (402 when exceeded). Off for self-hosting; usage is metered either way |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated browser origins allowed to call the API directly |
| `REDIS_URL` | `redis://localhost:6379/0` | Reserved for a future durable job queue; unused today |

## Web app (`web/.env.local`)

| Variable | Meaning |
|---|---|
| `NEXT_PUBLIC_DEV_BEARER` | The seeded dev user's UUID (printed by `python -m scripts.seed`) |
| `NEXT_PUBLIC_PERSONAL_ACCOUNT_ID` / `NEXT_PUBLIC_COMPANY_ACCOUNT_ID` | The seeded account UUIDs (sent as `X-Account-Id`) |
| `NEXT_PUBLIC_API_ORIGIN` | Production only: absolute backend origin. When unset, `/api/*` is proxied to `BACKEND_ORIGIN` (default `http://localhost:8000`) |
| `NEXT_PUBLIC_ENABLE_BILLING` | `1` shows the (mock) Billing screen |

## Fixed model choices

These are constants in code, not settings. Changing them is a code change, and for embeddings a re-index:

| Component | Model | Where |
|---|---|---|
| Embeddings | `BAAI/bge-base-en-v1.5` (768-d). The schema uses `vector(768)` | `app/services/embeddings.py` |
| Reranker | `BAAI/bge-reranker-base` | `app/services/reranking.py` |
| Answering | `gemini-2.5-flash`, escalation `gpt-4o` | `app/services/synthesis.py` |

Retrieval tuning knobs (RRF `k = 60`, per-source weights, a 30-candidate rerank window, a 0.4 reranker blend) are also constants, documented in [Hybrid search](features/hybrid-search.md).

## Example `.env`

```bash
DATABASE_URL=postgresql+psycopg://filemindr:CHANGE_ME@localhost:5432/filemindr
STORAGE_DIR=./storage
DEEPSEEK_API_KEY=your-deepseek-key
GEMINI_API_KEY=your-gemini-key
GOOGLE_APPLICATION_CREDENTIALS=./secrets/vision-credentials.json
OPENAI_API_KEY=
PIPELINE_WORKERS=3
WARMUP_MODELS=true
ENFORCE_QUOTAS=false
APP_ENV=development
```

Related: [Self-hosting](self-hosting.md) · [Getting started](getting-started.md)
