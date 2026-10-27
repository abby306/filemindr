# Filemindr — Open-Source RAG & Document Intelligence Platform

[![CI](https://github.com/abby306/filemindr/actions/workflows/ci.yml/badge.svg)](https://github.com/abby306/filemindr/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-000000?logo=nextdotjs&logoColor=white)
![PostgreSQL + pgvector](https://img.shields.io/badge/PostgreSQL_16-pgvector-4169E1?logo=postgresql&logoColor=white)

**Filemindr is a self-hostable, open-source RAG application for your documents.** Upload PDFs, scans, photos, or Word files. Filemindr OCRs them, uses an LLM to extract a structured record of each one (type, key facts, people, dates), and files them into a browsable archive. You can then ask questions across everything and get **AI answers with page-level source citations**. Retrieval is **hybrid search** inside PostgreSQL: pgvector similarity, full-text search, and structured facts, fused with Reciprocal Rank Fusion and reranked by a cross-encoder.

📖 **Documentation:** [abby306.github.io/filemindr](https://abby306.github.io/filemindr/) · 🧭 [Architecture](site/content/architecture.md) · 🚀 [Quickstart](#quickstart)

![Filemindr answering a question across two documents, with a live retrieval trace and page-level citations](docs/assets/screenshots/agentic-answer-citations.webp)

<sub>Screenshots use a fictional demo company; every answer and citation was produced by the real pipeline.</sub>

---

## Why Filemindr (and how it differs from a "chat with your PDF" app)

Most PDF chatbots split raw text into chunks, embed them, and hope the right chunk comes back. Filemindr does more work up front, at ingest:

- **It reads the document once and stores what it means.** An LLM pass turns OCR text into a *document card*: classes with confidence, entities, dated events (issued / due / expiry), typed facts (`total_amount: 1,240.00 USD`), and self-contained *atomic facts*. Each fact keeps its **page number and bounding box**.
- **It retrieves over that structure, not raw chunks.** "How much did I spend on the Acme invoice?" goes to typed numeric facts. "Invoice INV-20931" goes to exact-match full-text search. "What does the NDA say about termination?" goes to vector search. All three always run, and an intent router only *weights* them.
- **It shows where each answer came from.** Each answer cites the exact facts it used. Clicking a citation opens the page with the source region highlighted. If the documents don't contain the answer, it says "not in your documents" instead of guessing.
- **It is a document archive as well as a chatbot.** Documents are auto-classified into a folder taxonomy. Low-confidence or ambiguous classifications go to a human review queue. Every processing step is logged.

## Who it's for

- **Developers and engineers** looking for a readable, tested **open-source RAG reference implementation**: hybrid retrieval, reranking, agentic tool use and citations, in about 7k lines of Python.
- **Technical founders and small teams** who want a **self-hosted AI document management system** for invoices, contracts, receipts, statements and policies, with an API they control.
- **Anyone evaluating RAG architectures** who wants to see how structured extraction + pgvector + Postgres full-text search behave on real documents.

## Key features

| Area | What you get |
|---|---|
| **Document processing** | PDF, DOCX, PNG, JPEG. PDFs with a text layer are read directly (PyMuPDF). Scanned PDFs and photos go through Google Cloud Vision OCR. OCR results are cached by file hash, and uploads are deduplicated per account. |
| **Structured extraction** | One JSON-mode LLM pass per document (or per page window on long documents) produces the card + atomic facts. Parsing is lenient, so a noisy model response degrades instead of failing. |
| **Auto-filing & review** | Multi-label classification into a hierarchical class catalog (customizable per account). Low-confidence or ambiguous documents land in a **Needs review** queue. |
| **Hybrid retrieval** | Structured (typed facts / dates / entities) + lexical (Postgres FTS + exact id/name matches) + two-stage vector (pgvector HNSW). Merged with weighted **RRF**, then a **cross-encoder reranker** (`bge-reranker-base`). |
| **Agentic RAG** | The answering model gets tools (`find_documents`, `search`, `read_page`, `finish`) and decides whether to locate a document first, search more narrowly, or read a raw page. The loop is bounded and multi-turn. |
| **Source citations** | The model can only cite candidate fact ids it was given, so a hallucinated citation can't get through. Citations resolve to document and page, plus the bounding box for atomic facts. |
| **Web app** | Next.js thin client: drag-and-drop upload with background processing, archive (folders, list/details views, drag to re-file), document view with provenance highlighting, chat with a live retrieval trace, "Ask this folder", review deck, analytics. |
| **Observability** | Append-only `processing_events` per pipeline stage and `retrieval_traces` per answer (plan, candidates, tokens, latency). You debug with a `SELECT` instead of re-running. |
| **Multi-account tenancy** | Every table carries `account_id`. All queries go through one scoping layer (`AccountScope`). Personal and shared company accounts. |

<table>
<tr>
<td width="50%"><img src="docs/assets/screenshots/citation-provenance.webp" alt="Clicking a citation opens the source page with the cited clause highlighted"><br><sub>A citation opens the exact clause on the page.</sub></td>
<td width="50%"><img src="docs/assets/screenshots/scanned-pdf-ocr.webp" alt="A scanned tax form with no text layer, OCR'd and turned into typed facts"><br><sub>A scan with no text layer, read by OCR and turned into typed facts.</sub></td>
</tr>
<tr>
<td><img src="docs/assets/screenshots/archive-auto-filed.webp" alt="The archive with an automatically built folder taxonomy"><br><sub>The archive files documents into folders automatically.</sub></td>
<td><img src="docs/assets/screenshots/review-queue.webp" alt="The human review deck showing an uncertain classification with candidate classes"><br><sub>Uncertain classifications go to a review queue.</sub></td>
</tr>
</table>

---

## How it works: the RAG pipeline

```mermaid
flowchart LR
    U[Upload<br/>PDF · DOCX · PNG · JPEG] --> O{Text layer?}
    O -- yes --> P[PyMuPDF<br/>text + block bboxes]
    O -- no / image --> V[Google Vision OCR<br/>per page, cached by hash]
    P --> E[LLM structured extraction<br/>card + typed facts + atomic facts]
    V --> E
    E --> R{Confident?}
    R -- no --> Q[Needs review queue]
    R -- yes --> I
    Q --> I[Embed locally<br/>bge-base-en-v1.5 → pgvector HNSW]
    I --> DB[(PostgreSQL 16<br/>pgvector + FTS)]

    A[Question] --> IR[Intent router]
    IR --> S1[Structured<br/>typed facts · dates · entities]
    IR --> S2[Lexical<br/>Postgres FTS + exact ids]
    IR --> S3[Vector, two-stage<br/>doc summaries → facts]
    DB -.-> S1 & S2 & S3
    S1 & S2 & S3 --> F[Weighted RRF fusion]
    F --> X[Cross-encoder rerank<br/>bge-reranker-base]
    X --> G[Agentic synthesis<br/>find_documents · search · read_page]
    G --> C[Answer + page-level citations]
```

**Ingest** runs per document as `received → ocr_done → extracted | needs_review → indexed` on a bounded background worker pool, so uploads return immediately.

**Retrieval** ([`app/services/retrieval.py`](app/services/retrieval.py)):

1. A rule-based **intent router** labels the query `aggregate`, `lexical`, `metadata` or `semantic`. The label only changes source weights, so a misrouted query still reaches every retriever.
2. **Vector search is two-stage.** The query embedding shortlists documents by `summary_embedding`, then ranks atomic facts within those documents by `document_facts.embedding` (both pgvector HNSW, cosine).
3. **Lexical search** uses `websearch_to_tsquery` over a generated `tsvector` column (GIN index). It also does exact-ish matching of ids and names against typed-fact values and entities.
4. **Structured search** mines typed facts, dates and entities from the top-ranked documents only, so an aggregate never sums across unrelated files.
5. **Weighted Reciprocal Rank Fusion** (`k = 60`) merges the lists. Each list contributes `weight / (60 + rank)`. Facts whose label the query names ("VAT", "invoice number") get an extra high-weight vote.
6. A **cross-encoder** rescores the top 30. Its score is *blended* with the fused score (0.4 / 0.6), so a small CPU reranker refines the ranking without overriding it.

**Answering** ([`app/services/synthesis.py`](app/services/synthesis.py)): Gemini 2.5 Flash runs a bounded (5-step) function-calling loop. It sees a corpus overview, the conversation history and an initial candidate pool, and must end with `finish(answer, cited_fact_ids, supported)`. If it can't ground an answer, a single GPT-4o pass may retry over the same candidates (best-effort, optional). Answers stream to the browser over SSE with a live trace.

More depth: [Architecture](site/content/architecture.md) · [Hybrid search & reranking](site/content/features/hybrid-search.md) · [OCR & document processing](site/content/features/ocr-document-processing.md) · [Agentic RAG & citations](site/content/features/agentic-rag-citations.md)

## Supported document formats

| Format | How text is obtained | Page-level citations | Bounding boxes |
|---|---|---|---|
| PDF with text layer | PyMuPDF (`get_text`) | ✅ | ✅ (text blocks) |
| Scanned PDF | Each page rasterized at 200 DPI → Google Vision | ✅ | ✅ (Vision blocks) |
| PNG / JPEG (photos, scans) | Google Vision | ✅ (single page) | ✅ |
| DOCX | python-docx paragraph text | treated as one page | ❌ |

Default upload limit: 50 MB (`MAX_UPLOAD_MB`). Other types are rejected with `415`.

## Technology stack

| Layer | Technology |
|---|---|
| API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 16 + pgvector (HNSW, cosine) + built-in full-text search (GIN) |
| Web app | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, TanStack Query. A thin client over the JSON + SSE API |
| Embeddings | `BAAI/bge-base-en-v1.5`: 768-d, runs **locally on CPU** via sentence-transformers |
| Reranking | `BAAI/bge-reranker-base` cross-encoder: **local, CPU** |
| OCR | PyMuPDF text layer; Google Cloud Vision for scans and images |
| Extraction LLM | DeepSeek `deepseek-chat` through the OpenAI-compatible client (base URL and model are configurable) |
| Answer LLM | Gemini 2.5 Flash (function calling); optional GPT-4o escalation |

## Quickstart

Tested natively on Ubuntu 22.04+. A `docker-compose.yaml` is included for PostgreSQL + pgvector (and Redis, which the app doesn't use yet); the API and web app run natively.

### 1. Prerequisites

```bash
# PostgreSQL 16 + pgvector (PGDG repo) — or: docker compose up -d db
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
# Fill in: DEEPSEEK_API_KEY (extraction), GEMINI_API_KEY (answers),
# GOOGLE_APPLICATION_CREDENTIALS (Vision OCR for scans/images),
# OPENAI_API_KEY (optional GPT-4o escalation).

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

Or open the web app and drag files in. Day-to-day commands are in [`RUN.md`](RUN.md); a full guide is in [Self-hosting](site/content/self-hosting.md).

## Configuration and external API requirements

Filemindr is **self-hostable but not offline**. PostgreSQL, embeddings and reranking run on your machine. Three steps call hosted APIs, so **document text is sent to those providers**:

| Step | Provider | Required? | Env var |
|---|---|---|---|
| Structured extraction | DeepSeek (or any OpenAI-compatible endpoint via `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`, untested beyond DeepSeek) | **Yes**, for ingest | `DEEPSEEK_API_KEY` |
| Answers (chat) | Google Gemini 2.5 Flash | **Yes**, for Q&A | `GEMINI_API_KEY` |
| OCR of scans and images | Google Cloud Vision | Only for scanned PDFs / images | `GOOGLE_APPLICATION_CREDENTIALS` |
| Escalation on unsupported answers | OpenAI GPT-4o | Optional (failures are ignored) | `OPENAI_API_KEY` |

Other settings (`.env`): `DATABASE_URL`, `STORAGE_DIR`, `PIPELINE_WORKERS` (concurrent documents, default 3), `MAX_UPLOAD_MB`, `WARMUP_MODELS` (preload the ~400 MB of local models at startup), `ENFORCE_QUOTAS` (off by default, so self-hosted installs are unlimited), `CORS_ORIGINS`. Full reference: [Configuration](site/content/configuration.md).

## Example workflows

- **Bookkeeping:** drop a month of invoices and receipts, then ask *"What did we spend at Kestrel Print this quarter?"* The aggregate intent pulls typed `money` facts from the matching documents.
- **Contract review:** *"When does the office lease end, and how much notice do we need to give to renew?"* The answer cites the term clause on page 2.
- **Cross-document checks:** *"Does our insurance meet the liability coverage the lease requires?"* The agent finds both documents, searches each, and cites both.
- **Scoped questions:** type `@` to point at a document, or use **Ask this folder** to restrict retrieval to one class.
- **API use:** everything the web app does goes through `/api/v1` (OpenAPI at `/docs`). For example, `POST /api/v1/conversations/{id}/messages/stream` streams an answer with its retrieval trace.

## Security and deployment considerations

Read these before exposing an instance:

- **Authentication is dev-grade.** The bearer token *is* the seeded user's UUID. Don't put a Filemindr instance on the public internet without real authentication in front of it. The seam is [`app/core/auth.py`](app/core/auth.py) (`get_current_user`).
- **Data at rest is unencrypted.** Files and the OCR cache live under `STORAGE_DIR`, and text and facts live in PostgreSQL. Disk and database encryption are up to your deployment.
- **Third-party processing.** Extraction, answering and (for scans) OCR send document content to the providers listed above. Review their data policies for your use case.
- **Background work is in-process.** Pipeline jobs run on a bounded thread pool and don't survive a server restart. Re-drive stuck documents with `python -m scripts.reprocess`.
- **Billing endpoints are a mock** (a Stripe-shaped seam), and quotas are disabled by default.

Vulnerabilities: see [`SECURITY.md`](SECURITY.md).

## Development and testing

```bash
pytest -q                        # 285 tests against your local Postgres; zero network calls
cd web && npm run build && npm run lint
```

The suite covers the whole pipeline offline: OCR routing, extraction parsing and fan-out, embeddings, hybrid retrieval + RRF + reranking, the agentic synthesis loop (including escalation), conversation memory, usage metering and quotas, analytics, billing, and every HTTP route. DeepSeek, Vision, the bge encoder/reranker and the Gemini/GPT-4o seams are all mocked. [CI](.github/workflows/ci.yml) runs the suite against a pgvector service container and builds and lints the web app on every push and PR.

Retrieval quality is measured with the harness in [`eval/`](eval/README.md) (`doc_recall@k`, `fact_recall@k`, `answer_correctness` against a gold set). No benchmark numbers are published yet.

### Project structure

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
├── tests/              # Offline pytest suite (every network/model seam mocked)
├── site/               # Documentation website source (static, GitHub Pages-ready)
├── docs/               # Images and outreach drafts
└── agent_guide/        # Design docs (PRD, ARCHITECTURE, TECH_SPEC, API_CONTRACTS, …)
```

## Documentation

| Doc | What's in it |
|---|---|
| [Documentation website](https://abby306.github.io/filemindr/) ([source](site/content/)) | Getting started, self-hosting, configuration, architecture, feature deep-dives, FAQ |
| [`ARCHITECTURE.md`](agent_guide/ARCHITECTURE.md) | System design, pipeline flows |
| [`TECH_SPEC.md`](agent_guide/TECH_SPEC.md) | Schema, runtime models, retrieval algorithm |
| [`API_CONTRACTS.md`](agent_guide/API_CONTRACTS.md) | Endpoint shapes |
| [`AGENTS.md`](agent_guide/AGENTS.md) | Rules for AI coding agents working in this repo |
| [`CODING_STANDARDS.md`](agent_guide/CODING_STANDARDS.md) | Conventions: style, seams, scoping, tests |
| [`STATUS.md`](STATUS.md) | Live development handoff (current state, file-by-file map) |
| [`CHANGELOG.md`](CHANGELOG.md) | Notable changes |

## Current limitations

- Requires hosted LLM APIs (DeepSeek-compatible extraction, Gemini answers); there is no local-LLM path for answering yet.
- Single-process deployment; no durable job queue; no Docker image for the API/web app yet.
- English-tuned retrieval (`bge-base-en-v1.5`, `english` FTS configuration).
- DOCX files have no page or bounding-box provenance.
- Auth is dev-grade (see above).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). In short: read `agent_guide/AGENTS.md` first, make schema changes through Alembic only, keep every query account-scoped, and keep the suite offline and green. Bug reports and focused PRs are welcome. Use the issue templates.

## License

[AGPL-3.0](LICENSE). You can self-host, modify and redistribute Filemindr freely. If you offer a modified Filemindr as a network service, you must release your changes under the same license. For commercial licensing, open an issue.
