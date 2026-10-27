---
title: "Getting Started with Filemindr (Local Install)"
nav_title: Getting started
description: "Install Filemindr locally: PostgreSQL + pgvector, the FastAPI backend and the Next.js web app, then ingest a demo corpus and ask cited questions."
---

# Getting started with Filemindr

This guide runs Filemindr on one Linux machine for development or evaluation. It takes about 15 minutes, most of it spent on dependency downloads. For a longer-lived install, read [Self-hosting](self-hosting.md) afterwards.

## What you need

- **Ubuntu 22.04+** (other Linux distributions work if you can install the same packages)
- **PostgreSQL 16 with pgvector**, installed natively or with the included `docker compose`
- **Python 3.12** and **Node.js 20+**
- Enough RAM for two small local models (about 400 MB once loaded, downloaded from Hugging Face on first use). The project is developed on an 8 GB laptop
- API keys: **DeepSeek** (extraction) and **Gemini** (answers). Add a **Google Cloud Vision** service account if you'll upload scanned PDFs or photos. See [Configuration](configuration.md).

## 1. Get the code

```bash
git clone https://github.com/abby306/filemindr.git
cd filemindr
```

## 2. Start PostgreSQL with pgvector

Native install (PGDG apt repository):

```bash
sudo apt install -y postgresql-16 postgresql-16-pgvector
sudo -u postgres psql <<SQL
CREATE ROLE filemindr WITH LOGIN PASSWORD 'localdev';
CREATE DATABASE filemindr OWNER filemindr;
GRANT ALL ON DATABASE filemindr TO filemindr;
SQL
psql "postgresql://filemindr:localdev@localhost:5432/filemindr" \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Or with Docker, using the `pgvector/pgvector:pg16` image:

```bash
docker compose up -d db
```

## 3. Run the FastAPI backend

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in the API keys
alembic upgrade head          # creates tables, pgvector HNSW + GIN indexes
python -m scripts.seed        # dev user + personal/company accounts; prints 3 UUIDs
uvicorn app.main:app --reload # http://localhost:8000
```

Check it's up:

```bash
curl localhost:8000/health
# {"status":"ok","env":"development","database":"up"}
```

The interactive OpenAPI docs are at `http://localhost:8000/docs`.

## 4. Run the Next.js web app

```bash
cd web
npm install
cp .env.local.example .env.local   # paste the three UUIDs printed by scripts.seed
npm run dev                        # http://localhost:3000
```

The dev server proxies `/api/*` to the backend on port 8000, so you only open `localhost:3000`.

## 5. Ingest documents and ask a question

Drag files into the **Upload** screen. Each document moves through `received → ocr_done → extracted → indexed` in the background. Or use the scripted demo corpus:

```bash
python -m scripts.make_demo_corpus   # 8 synthetic PDFs: invoice, receipt, NDA, spec, …
python -m scripts.seed_corpus        # run them through the live pipeline
python -m scripts.ask "What is the total amount due on the Acme invoice?"
```

In the web app, open **Ask** and type a question. The answer streams in with a live retrieval trace. Click a citation to open the source page with the cited region highlighted.

![A citation opens the source page with the clause highlighted](../../docs/assets/screenshots/citation-provenance.webp)

## Useful commands

| Command | What it does |
|---|---|
| `python -m scripts.retrieve "<question>"` | Retrieval only (no LLM answer): prints ranked facts with sources |
| `python -m scripts.chat` | Interactive multi-turn chat in the terminal |
| `python -m scripts.reprocess` | Re-drive documents stuck in a stage (for example after a restart) |
| `python -m scripts.eval_retrieval` | Score retrieval against the gold set in `eval/gold/seed.yaml` |
| `pytest -q` | Run the offline test suite (no network calls, no model downloads) |

## Troubleshooting

- **First query takes 20–60 seconds.** The local models load lazily. Set `WARMUP_MODELS=true` to preload them at startup.
- **A document never leaves `received`.** Background jobs don't survive a server restart. Run `python -m scripts.reprocess`.
- **Scanned PDFs fail at OCR.** Check that `GOOGLE_APPLICATION_CREDENTIALS` points at a valid Vision service-account file.

Next: [Configuration](configuration.md) · [Architecture](architecture.md)
