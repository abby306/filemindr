---
title: "Building an Open-Source RAG Document Management System with FastAPI and pgvector"
description: "How Filemindr turns uploads into a structured, cited, searchable archive: FastAPI, PostgreSQL + pgvector, local BGE embeddings and an agentic answer loop."
tags: [rag, fastapi, postgresql, pgvector, document-management, python, open-source]
canonical_url: "TODO — set to the docs-site copy (e.g. https://abby306.github.io/filemindr/...) or the first place this is published"
status: draft — not published
---

# Building an Open-Source RAG Document Management System with FastAPI and pgvector

Most "chat with your PDFs" demos follow the same recipe: split the text into
fixed-size chunks, embed the chunks, put them in a vector store, and at question
time stuff the nearest chunks into a prompt. It works well enough for a single
long document. It works badly for an *archive* — hundreds of invoices, leases,
receipts, statements and scans — where the questions are things like "how much
did we pay Kestrel Print this year?", "when does the office lease end?" or
"which invoices are still unpaid?".

This article walks through how [Filemindr](https://github.com/abby306/filemindr),
an open-source RAG system and document management app, approaches that problem.
It is a FastAPI + PostgreSQL/pgvector backend with a Next.js client, licensed
AGPL-3.0. The interesting part is not any single library; it's the shape of the
data the pipeline produces and how the rest of the system leans on it.

## The core idea: extract once, retrieve over structure

Filemindr does not retrieve over raw text chunks. At ingest, each document goes
through one structured-extraction LLM pass that produces a **document card**:

- a title and a short summary,
- multi-label classes with confidences (which folder it belongs in),
- entities (people, organizations, places),
- dates with a role (`issued`, `due`, `expiry`, `event`, `mentioned`),
- **typed facts** — `label`, `value`, `value_numeric`, `value_type`
  (`money | number | date | id | string`), `unit`, `page`,
- **atomic facts** — self-contained sentences, each with the page it came from
  and, where possible, a bounding box.

Retrieval then runs over those rows. An atomic fact like *"The lease term ends
on February 28, 2029"* is a better retrieval unit than a 512-token chunk that
happens to contain it: it embeds cleanly, it ranks cleanly, and because it
carries `page` and `bbox`, **a retrieval hit is already a citation**.

The trade-off is cost and latency at ingest (one or more LLM calls per document)
in exchange for cheaper, more precise answers later. For an archive that is read
far more than it is written, that's usually the right trade.

## Architecture at a glance

```
Upload (PDF / PNG / JPEG / DOCX)
  → OCR          PyMuPDF text layer; Google Vision for scans and images
  → Extraction   one structured-output LLM pass (DeepSeek, OpenAI-compatible client)
  → Embedding    BAAI/bge-base-en-v1.5, local, CPU, 768-d
  → Retrieval    structured + Postgres FTS + two-stage vector, fused with RRF,
                 then a local cross-encoder rerank
  → Answer       agentic loop on Gemini 2.5 Flash with validated citations
```

| Layer | Choice |
|---|---|
| API | FastAPI (Python 3.12) |
| Database | PostgreSQL 16 + pgvector (HNSW indexes) + built-in full-text search |
| Embeddings | `BAAI/bge-base-en-v1.5`, local CPU, 768 dimensions |
| Reranker | `BAAI/bge-reranker-base`, local CPU cross-encoder |
| OCR | PyMuPDF + Google Cloud Vision |
| Extraction | DeepSeek `deepseek-chat` via the OpenAI SDK |
| Answering | Gemini 2.5 Flash (function calling); optional GPT-4o escalation |
| Web | Next.js (App Router, TypeScript), a thin client over JSON + SSE |

Everything lives in one Postgres database: relational card tables, vector
columns, and `tsvector` columns side by side. There is no separate vector
database to keep in sync, and a single SQL query can join a vector shortlist
against typed facts.

## The schema is the design

The canonical DDL is in
[`schema.sql`](https://github.com/abby306/filemindr/blob/main/schema.sql)
(Alembic owns migrations). Two tables carry the retrieval load.

`documents` holds the file, its pipeline status, the OCR text, and a summary
embedding:

```sql
CREATE TABLE IF NOT EXISTS documents (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id        uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  ...
  file_hash         text NOT NULL,
  status            document_status NOT NULL DEFAULT 'received',
  ocr_text          text,
  ocr_engine        ocr_engine,
  extraction_raw    jsonb,
  summary_embedding vector(768),
  ...
  UNIQUE (account_id, file_hash)
);
CREATE INDEX IF NOT EXISTS documents_summary_embedding_hnsw
  ON documents USING hnsw (summary_embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

`document_facts` is the primary retrieval unit. Note the generated `fts`
column — Postgres keeps the full-text vector in sync with `text` for free:

```sql
CREATE TABLE IF NOT EXISTS document_facts (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  text        text NOT NULL,
  page        int,
  bbox        jsonb,
  embedding   vector(768),
  fts         tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS document_facts_fts_gin ON document_facts USING gin (fts);
CREATE INDEX IF NOT EXISTS document_facts_embedding_hnsw
  ON document_facts USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
```

Alongside these sit `typed_facts` (with a `numeric` column, so "how much"
questions can work with real numbers), `document_dates`, `entities` /
`document_entities`, and `document_classes`.

Two details worth copying into your own design:

1. **`UNIQUE (account_id, file_hash)`** — uploads are deduplicated by SHA-256
   per account. Re-uploading the same file returns the existing document.
2. **Every table carries `account_id`**, even where it could be derived through
   a join. That makes tenancy filtering a single predicate everywhere, which
   matters in the next section.

## Tenancy as a programming error, not a runtime risk

A document tool that supports more than one account has one unforgivable bug:
showing account A's documents to account B. Filemindr handles this with a small
wrapper in
[`app/core/scoping.py`](https://github.com/abby306/filemindr/blob/main/app/core/scoping.py):

```python
@dataclass(frozen=True)
class AccountScope:
    db: Session
    user: User
    account: Account

    def _require_scoped(self, model: type) -> None:
        if not hasattr(model, "account_id"):
            raise ValueError(
                f"{model.__name__} has no account_id; it cannot be account-scoped. "
                "Query it explicitly only when there is no tenancy boundary."
            )

    def select(self, model: type) -> Select:
        """A `SELECT` over `model` pre-filtered to the active account."""
        self._require_scoped(model)
        return select(model).where(model.account_id == self.account_id)
```

Routes depend on `get_current_account`, which resolves the user from the bearer
token, picks the account from an `X-Account-Id` header, and verifies
membership (401/403 otherwise). Background services that run outside a request
(OCR, extraction, embedding, retrieval) take `account_id` explicitly and filter
on it in every query.

An honest caveat: the bundled authentication is **dev-grade**. The bearer token
is the user's UUID. It is a seam
([`app/core/auth.py`](https://github.com/abby306/filemindr/blob/main/app/core/auth.py),
`get_current_user`) where real auth is meant to slot in. Don't expose a
self-hosted instance to the internet without putting proper authentication in
front of it.

## The ingest pipeline: four stages, logged

Each upload moves through `received → ocr_done → extracted → indexed` (or
`needs_review`, or `failed`). Every stage appends a row to `processing_events`
with its duration and a JSON `detail` — engine used, cache hit or miss, failed
pages, facts embedded. When something goes wrong, debugging is a `SELECT`, not
a re-run.

The stages chain: `run_ocr` calls `run_extraction` on success, which calls
`run_embedding`. Each opens its own session, re-checks the document's
`account_id`, and records its own failure rather than raising, so a bad
document marks itself `failed` without taking down a worker.

Concurrency is bounded on purpose. The docstring in
[`app/services/pipeline.py`](https://github.com/abby306/filemindr/blob/main/app/services/pipeline.py)
explains why: FastAPI `BackgroundTasks` have no concurrency cap, and dropping
30 files used to start 30 simultaneous OCR→extraction→embedding chains, each
holding a DB connection for minutes, which exhausted the pool. The fix is one
small executor:

```python
def submit(fn: Callable[..., Any], *args: Any) -> None:
    workers = get_settings().pipeline_workers
    if workers <= 0:
        fn(*args)
        return
    _get_executor(workers).submit(fn, *args)
```

Uploads return immediately; `PIPELINE_WORKERS` (default 3) documents process at
a time. `PIPELINE_WORKERS=0` runs inline, which is what the test suite uses so
an upload's whole chain completes synchronously.

The limitation: this is an in-process thread pool. **Queued work does not
survive a server restart.** Documents stranded mid-pipeline are re-driven with
`python -m scripts.reprocess`. A durable queue (the code comment names
Redis as the intended replacement behind the same `submit` seam) is future work.

## OCR and extraction, briefly

OCR routing is covered in depth in a separate article, but the summary is:
PDFs are probed for a usable text layer with PyMuPDF (at least 100 characters
total and 20 per page). If present, the text is read directly with block-level
bounding boxes. If not, each page is rasterized at 200 DPI and sent to Google
Vision. Images go straight to Vision; DOCX is read with `python-docx`. OCR
results are cached on disk by file hash.

Extraction
([`app/services/extraction.py`](https://github.com/abby306/filemindr/blob/main/app/services/extraction.py))
sends the OCR text, marked up with `===== PAGE n =====` separators, to an
OpenAI-compatible chat endpoint with `response_format={"type": "json_object"}`
and `temperature=0`. Long documents are split into page windows of up to 14,000
characters, extracted in parallel, and merged (classes keep the max confidence
per slug; facts are unioned and deduplicated).

The parser is deliberately lenient. Every field goes through a Pydantic model
with `extra="ignore"` and coercing validators: unknown enum values fall back to
defaults, unparseable dates become `null`, and entity lists tolerate the model
returning `[{"name": "..."}]` instead of `["..."]`. A noisy model response
degrades one field instead of failing the document.

Classification confidence decides where a document lands. Below 0.5 top
confidence, or when the top two classes are close (gap ≤ 0.15, runner-up
≥ 0.30, top < 0.80), the document goes to a `needs_review` queue that the web
app presents as a review deck. It is still embedded and searchable while it
waits.

## Embeddings: local, normalized, asymmetric

Embeddings run locally with `sentence-transformers` and
`BAAI/bge-base-en-v1.5` on CPU — no per-token cost, and the vectors never leave
the host. Two details in
[`app/services/embeddings.py`](https://github.com/abby306/filemindr/blob/main/app/services/embeddings.py)
are easy to get wrong:

```python
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed documents/facts for indexing — no instruction prefix."""
    ...

def embed_query(query: str) -> list[float]:
    """Embed a search query — with the bge retrieval instruction prefix."""
    return _encode([QUERY_INSTRUCTION + query])[0]
```

BGE v1.5 expects the retrieval instruction on the **query side only**. And
vectors are encoded with `normalize_embeddings=True`, so cosine distance — the
operator the HNSW indexes use — behaves as intended.

The model (~400 MB) is a lazy, double-checked-lock singleton. Optionally,
`WARMUP_MODELS=true` loads it in a background thread at startup so the first
query doesn't stall.

## Retrieval and answering

Retrieval is hybrid: a structured retriever over typed facts, dates and
entities; Postgres full-text search plus exact-ish matching on identifiers; and
a two-stage vector search (summary embeddings shortlist documents, fact
embeddings rank facts within them). The three lists are fused with weighted
Reciprocal Rank Fusion, and a local cross-encoder reranks the top 30. The
details — and why the reranker is blended rather than trusted outright — are in
the hybrid-search article.

Answering is agentic. Instead of handing the model a fixed top-k, Filemindr
gives Gemini 2.5 Flash a bounded corpus overview, an initial candidate pool, the
conversation history, and four tools:

- `find_documents` — resolve "the NDA" or "the March invoice" to real documents,
- `search` — retrieve more facts, optionally scoped to a document or class,
- `read_page` — read the raw OCR text of one page when the extracted facts lack
  detail,
- `finish(answer, cited_fact_ids, supported)` — commit the answer.

The loop is capped at five model turns and forced to `finish` on the last one.
Citations are validated: the model sees short ids (`f3`, `d2`) and any id it
cites that wasn't actually handed to it is dropped. `supported=false` is the
honest "not in your documents" path. If Flash can't ground an answer, a
single-shot GPT-4o pass re-reasons over the same candidate pool; it is adopted
only if it finds support, and skipped silently if the OpenAI key is missing.

The streaming endpoint (`POST /api/v1/conversations/{id}/messages/stream`)
forwards the loop's step events over Server-Sent Events, which is how the web
app shows a live retrieval trace. Every turn also writes a `retrieval_traces`
row: plan, candidates, citations, model, tokens, latency.

## Testing a system made of network calls

Every network or model dependency sits behind exactly one function:
`call_extraction_model`, `_vision_ocr_image_bytes`, `_encode`, `_score`,
`_gemini_turn`, `_openai_resynthesize`. Tests monkeypatch those seams, so the
suite runs against a real local Postgres with **zero network calls and no model
downloads**. As of 2026-10-27 it is 285 tests, run in GitHub Actions against a
`pgvector/pgvector:pg16` service container alongside the web build and lint.

There is also an `eval/` harness with `doc_recall@k`, `fact_recall@k` and
`answer_correctness` scorers and a small gold set written against a synthetic
demo corpus (`python -m scripts.make_demo_corpus`). It is a tool for catching
regressions while tuning, not a published benchmark.

## What it does not do (yet)

Being clear about limits is part of evaluating any open-source RAG system:

- **Not offline.** Embeddings, reranking and the database are local, but
  extraction (DeepSeek or another OpenAI-compatible endpoint), answering
  (Gemini) and OCR of scans/images (Google Vision) are external APIs. Document
  text is sent to those providers. Pointing `DEEPSEEK_BASE_URL` at a
  self-hosted OpenAI-compatible server is possible in configuration but not a
  tested path.
- **Dev-grade auth**, as noted above.
- **English-first search.** Full-text search uses the `english` configuration
  and BGE base is an English model.
- **Not a durable job queue.** In-process workers; re-drive with
  `scripts.reprocess` after a restart.
- **Supported inputs:** PDF, PNG, JPEG, DOCX (50 MB default limit). No
  spreadsheets or slide decks.
- **Storage is unencrypted** on disk and in Postgres; encryption at rest is the
  deployment's job.

## Takeaways

If you're building a RAG document management system yourself, the parts of this
design that carry over regardless of stack:

1. Spend LLM budget once at ingest to produce structured, page-anchored facts;
   retrieve over those instead of raw chunks.
2. Keep vectors, full-text indexes and relational data in one Postgres so
   hybrid queries are joins, not cross-system orchestration.
3. Make tenancy a constructor-level guarantee.
4. Put every external call behind one stubbable seam and keep the test suite
   offline.
5. Log each pipeline stage to a table.

---

**About Filemindr.** Filemindr is an open-source (AGPL-3.0), self-hostable RAG and
document intelligence platform built with FastAPI, PostgreSQL + pgvector and
Next.js. Source: <https://github.com/abby306/filemindr> · Docs:
<https://abby306.github.io/filemindr/architecture/> ·
Getting started: <https://abby306.github.io/filemindr/getting-started/>
