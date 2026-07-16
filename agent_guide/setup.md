# filemindr — Local Setup (agent context)

Orientation for coding agents (Claude Code, Antigravity) working on this project.
Describes the **current** machine and environment. Read before running commands or assuming tooling.

---

## Project

**filemindr** — intelligent document archivist. Users dump documents (scan/upload PDFs, images, Word docs, or email-in); each is OCR'd if needed and processed into a structured "card" (class/type, summary, typed facts, people, dates) plus atomic facts for retrieval. A chat + voice agent does grounded retrieval over the documents with citations.

- **Phase:** v1 = core intelligence + retrieval engine. No frontend polish yet.
- **Tenancy:** scoped by `account_id` (one **personal** + one **company** account). No RBAC yet — any member can read/query/move within an account.
- **Status:** environment is set up. Schema, app code, and embedding model are **not done yet** (next steps).

---

## Machine

| | |
|---|---|
| Device | Lenovo ThinkPad T480s |
| OS | Ubuntu 26.04 LTS (Resolute) |
| RAM | 8 GB (constraint — see Notes) |
| Disk | 256 GB SSD |
| User@host | `<user>@<host>` (developer laptop) |
| Project root | `~/projects/Filemindr` |

---

## Stack — native, no Docker (this phase)

Everything runs natively as `systemd` services. **Do not** start Docker or assume containers in this phase. (Docker is the MVP/deploy path, later.)

### PostgreSQL 16 + pgvector
- Installed from the **PGDG** apt repo. Pinned to **16** to match the future `pgvector/pgvector:pg16` image.
- Extension SQL name is `vector` (not `pgvector`).
- Connection (matches `.env`):
  - host `localhost`, port `5432`
  - role `filemindr`, password `localdev`, database `filemindr`
  - URL: `postgresql+psycopg://filemindr:localdev@localhost:5432/filemindr`
- Inspect directly: `psql "postgresql://filemindr:localdev@localhost:5432/filemindr"`
- Service: `sudo systemctl status postgresql`

### Redis
- Native `redis-server`, `localhost:6379`, URL `redis://localhost:6379/0`.
- Optional until the background worker exists.

---

## Python

- Managed by **pyenv**, version **3.12.x**, pinned via `.python-version` in the project root.
- Virtualenv at `~/projects/Filemindr/.venv` (stdlib `venv` + `pip`).
- Activate: `source ~/projects/Filemindr/.venv/bin/activate`

### Installed libraries (core)
`fastapi`, `uvicorn[standard]`, `sqlalchemy`, `psycopg[binary]`, `pgvector`,
`alembic`, `pydantic`, `pydantic-settings`, `python-multipart`, `httpx`,
`openai`, `google-cloud-vision`, `pymupdf`, `python-docx`

**Import-name gotchas:** `pymupdf` → `import fitz`; `python-docx` → `import docx`; `google-cloud-vision` → `import google.cloud.vision`.

### Deferred on purpose (NOT installed yet)
- `sentence-transformers` + the embedding model. Installing it pulls PyTorch and **fixes the vector dimension**, so it waits until the embedding model is locked (right before the schema).
- Planned embedding model: **`bge-base-en-v1.5`** (768-dim, local, CPU, zero per-token cost) — chosen for retrieval quality (the ThinkPad has RAM headroom). Vector columns are `vector(768)`.

---

## External providers (planned roles)

- **Google Vision** — OCR fallback when a PDF has no usable text layer; images go straight to Vision. Credentials JSON at `secrets/vision-credentials.json` (git-ignored), referenced by `GOOGLE_APPLICATION_CREDENTIALS`.
- **GPT-4o / GPT-4o-mini** (OpenAI) — `mini` for the cheap structured-extraction pass; full `4o` reserved for answer synthesis and low-confidence cases.
- **DeepSeek** (optional) — alternative cheap tier; reached via the OpenAI-compatible client (`openai` lib + custom `base_url`).
- Keys live in `.env` (git-ignored). Never commit or hardcode.

---

## Directory layout

```
filemindr/
├─ app/
│  ├─ api/         # HTTP route handlers
│  ├─ core/        # settings, config, app wiring
│  ├─ db/          # session + models (TBD)
│  ├─ services/    # ocr, extraction, retrieval, llm clients
│  ├─ workers/     # background jobs (TBD)
│  └─ main.py      # FastAPI entry point (TBD)
├─ alembic/        # migrations
├─ tests/
├─ storage/        # raw uploaded files (git-ignored)
├─ secrets/        # vision-credentials.json (git-ignored)
├─ .env            # secrets (git-ignored); .env.example committed
├─ .python-version # pyenv pin (committed)
└─ docker-compose.yml  # for the later Docker phase
```

---

## Agent / model routing (developer workflow)

The human drives the build using two agentic IDEs plus a model tier strategy:

- **Claude Code** + **Antigravity** — combined, for hands-on coding.
- **Gemini Flash** — trivial / mechanical tasks.
- **Claude Sonnet** — significant implementation work.
- **Claude Opus** — the hardest reasoning / architecture / debugging.

(This is workflow context, not something to configure in the repo.)

---

## Conventions & constraints

- **8 GB RAM:** run **one** Electron IDE at a time (Antigravity *or* VS Code, not both with a browser). A 4 GB swapfile is configured as OOM insurance.
- **PDFs:** use **PyMuPDF (`fitz`)** for the text-layer probe and rasterization — no poppler dependency.
- **Paths:** use `pathlib`; never hardcode separators.
- **Provenance from the first pass:** keep page numbers (and Vision bounding boxes where available) — citations depend on it and it's painful to retrofit.
- **OCR caching:** cache OCR output keyed by file hash; never re-OCR the same file.
- **Cost discipline:** cheap model for classification/extraction, strong model only for synthesis/hard cases; prefer local embeddings.

---

## Deploy target (later)

Contabo Linux VPS, **Dockerized at MVP**. The same `docker-compose.yml` (Postgres 16 + pgvector + Redis) runs there. Role/db/ports are identical to the native setup, so `.env` is unchanged across the switch.

> ⚠️ Native and container data stores are **separate** — switching to Docker does not migrate data. Re-run migrations / re-ingest, or `pg_dump` first to carry data over.

---

## Quick health check

```bash
# DB + pgvector
psql "postgresql://filemindr:localdev@localhost:5432/filemindr" -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
# Redis
redis-cli ping
# Python stack
source ~/projects/Filemindr/.venv/bin/activate
python -c "import fastapi, sqlalchemy, pgvector, fitz, openai; print('stack ok')"
```

---

## Next steps (not yet done)

1. Lock the embedding model (`bge-base-en-v1.5`, 768-dim) → install `sentence-transformers`.
2. Database schema: conventional tables + vector + observability/debug views (DDL + Alembic migration).
3. Build phases: ingest (web + email-in) → OCR routing → structured extraction → retrieval engine → grounded synthesis → eval harness.
