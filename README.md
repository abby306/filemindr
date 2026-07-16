# Filemindr

**Open-source intelligent document archivist.** Drop in PDFs, images, or Word docs — Filemindr OCRs them, extracts structured metadata (type, key facts, people, dates), files them into a browsable archive, and lets you ask questions over everything with **cited, click-to-source answers**.

> Every answer cites its source down to the page (and bounding box where available). No cross-account data leakage by construction. Built to run on a budget: local embeddings, a cheap extraction tier, strong models only where they matter.

---

## What it does

```
Upload (PDF/image/docx)
  → OCR (PyMuPDF text layer → Google Vision fallback)
  → Structured extraction (type, facts, entities, dates) — one cheap LLM pass (DeepSeek)
  → Vector + FTS index (bge-base-en-v1.5, 768-dim, local, CPU)
  → Hybrid retrieval (structured + lexical + vector, fused with RRF) → cross-encoder rerank
  → Agentic chat Q&A with citations (Gemini 2.5 Flash; GPT-4o escalation on hard misses)
```

Each document runs a four-stage pipeline: `received → ocr_done → extracted → indexed`, append-only logged in `processing_events` — debugging is a SELECT, not a re-run. The **Next.js web app** covers the full loop: upload (never-wait background processing), archive browse, human-in-the-loop review, document view with provenance highlighting, grounded chat with a live retrieval trace, and analytics.

---

## Architecture overview

| Layer | Technology |
|---|---|
| API | FastAPI (Python 3.12) |
| Database | PostgreSQL 16 + pgvector |
| Web app | Next.js (App Router, TS) + Tailwind — a pure thin client over the JSON+SSE API |
| Embeddings | `bge-base-en-v1.5` — local, 768-dim, CPU, zero per-token cost |
| Reranking | `bge-reranker-base` — local cross-encoder, CPU, blended with RRF |
| OCR | PyMuPDF (text-layer probe) + Google Vision (fallback / images) |
| Extraction | DeepSeek `deepseek-chat` (cheap structured-output pass) |
| Synthesis | Gemini 2.5 Flash (agentic, grounded, cited); GPT-4o escalation on `supported=false` |

The web tier holds **no business logic** — every derived number and grouping is computed server-side, so the same API can serve other clients unchanged. Full design docs live in [`agent_guide/`](agent_guide/) — start with [`ARCHITECTURE.md`](agent_guide/ARCHITECTURE.md).

---

## Quickstart (native — Ubuntu 22+)

### 1. Prerequisites

```bash
# PostgreSQL 16 + pgvector (PGDG repo)
sudo apt install -y postgresql-16 postgresql-16-pgvector

# Python 3.12 (pyenv or system) and Node 20+ for the web app
```

### 2. Database

```bash
sudo -u postgres psql <<SQL
CREATE ROLE filemindr WITH LOGIN PASSWORD 'localdev';
CREATE DATABASE filemindr OWNER filemindr;
GRANT ALL ON DATABASE filemindr TO filemindr;
SQL

psql "postgresql://filemindr:localdev@localhost:5432/filemindr" \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 3. Backend

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in: DEEPSEEK_API_KEY (extraction), GEMINI_API_KEY (synthesis),
# OPENAI_API_KEY (GPT-4o escalation), GOOGLE_APPLICATION_CREDENTIALS (Vision OCR).

alembic upgrade head          # full schema (incl. pgvector indexes + plan seed)
python -m scripts.seed        # dev user + personal/company accounts; PRINTS YOUR UUIDS
uvicorn app.main:app --reload # http://localhost:8000 (interactive docs at /docs)
```

### 4. Web app

```bash
cd web
npm install
cp .env.local.example .env.local   # paste the three UUIDs scripts.seed printed
npm run dev                        # http://localhost:3000 (/api/* proxies to :8000)
```

### 5. Try it with the demo corpus

```bash
python -m scripts.make_demo_corpus   # 8 synthetic PDFs (invoice, receipt, NDA, spec, …)
python -m scripts.seed_corpus        # ingest through the live OCR→extraction→embedding pipeline
python -m scripts.ask "What is the total amount due on the Acme invoice?"
```

Or just open the web app and drag files in. Day-to-day commands live in [`RUN.md`](RUN.md).

> Auth is intentionally minimal (single-user dev bearer). Real auth slots in at the single `get_current_user` seam in [`app/core/auth.py`](app/core/auth.py). Plan quotas are **off by default** (`ENFORCE_QUOTAS=false`) — a self-hosted install is unlimited.

---

## Project structure

```
filemindr/
├── app/
│   ├── api/            # HTTP routes: documents, conversations (chat/SSE), classes, analytics, billing
│   ├── core/           # config, auth (the seam), AccountScope tenancy, retry/concurrency
│   ├── db/             # SQLAlchemy ORM (maps the existing schema; Alembic owns DDL)
│   ├── services/       # ocr, extraction, embeddings, retrieval, reranking, synthesis,
│   │                   #   catalog, conversations, usage (metering/quota), billing (provider seam)
│   └── main.py
├── web/                # Next.js thin client (upload, archive, review, document, ask, analytics)
├── alembic/            # Migrations — schema source of truth (schema.sql is the canonical DDL)
├── scripts/            # seed, make_demo_corpus, seed_corpus, reprocess, ask, chat, evals
├── eval/               # Retrieval/synthesis eval harness + gold set for the demo corpus
├── tests/              # 250+ tests, fully offline (every network/model seam mocked)
└── agent_guide/        # Design docs (PRD, ARCHITECTURE, TECH_SPEC, API_CONTRACTS, …)
```

---

## Tenancy & security model

Every table carries a denormalized `account_id`. **All queries go through `AccountScope`**, which enforces `WHERE account_id = :active` and raises at the call site if a model lacks `account_id` — cross-account leakage is a programming error, not a silent runtime risk. Request auth resolves the user from the bearer token and verifies account membership (401/403 otherwise).

---

## Tests

```bash
pytest -q                        # against your local Postgres; zero network calls
cd web && npm run build && npm run lint
```

The suite covers the whole pipeline offline: OCR routing, extraction parsing + fan-out, embeddings, hybrid retrieval + RRF + reranking, the agentic synthesis loop (incl. escalation), conversation memory, usage metering + quotas, analytics, billing, and every HTTP route. DeepSeek, Vision, the bge encoder/reranker, and the Gemini + GPT-4o seams are all mocked.

---

## Key design docs

| Doc | What's in it |
|---|---|
| [`ARCHITECTURE.md`](agent_guide/ARCHITECTURE.md) | System design, pipeline flows |
| [`TECH_SPEC.md`](agent_guide/TECH_SPEC.md) | Schema, runtime models, retrieval algorithm |
| [`API_CONTRACTS.md`](agent_guide/API_CONTRACTS.md) | Endpoint shapes |
| [`AGENTS.md`](agent_guide/AGENTS.md) | Rules for AI coding agents working in this repo |
| [`CODING_STANDARDS.md`](agent_guide/CODING_STANDARDS.md) | Conventions: style, seams, scoping, tests |
| [`STATUS.md`](STATUS.md) | Live development handoff (current state, file-by-file map) |

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). The short version: read `agent_guide/AGENTS.md` first; schema changes go through Alembic only; every query stays account-scoped; keep the suite offline and green.

## License

[AGPL-3.0](LICENSE). You can self-host, modify, and redistribute freely; if you offer a modified Filemindr as a network service, you must release your changes under the same license. For commercial licensing, open an issue.
