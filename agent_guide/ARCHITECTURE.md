# ARCHITECTURE.md — filemindr

High-level system design. Schema/implementation detail lives in `TECH_SPEC.md`.

## Principle
Retrieve against **structured data**, not raw text. At ingest, each document is turned once into a **document card** (typed metadata) + **atomic facts** (self-contained sentences with provenance). Raw OCR text is kept only for citation/verification. This keeps query-time context small (cheap tokens) and precise (accurate retrieval).

## Components
- **Frontend (Next.js)** — Apple-minimal web app: Upload, Document view, Ask, Ratings, Analytics, Billing. Talks to the API only; design tokens/specs in `FRONTEND.md`.
- **API (FastAPI)** — upload, email-in webhook, chat/query, document/class, ratings, analytics, billing endpoints.
- **Ingest** — accept files, dedup by hash, persist raw file, create document row.
- **OCR router** — PDF text-layer probe (PyMuPDF) → Google Vision fallback; docx direct; images → Vision. OCR cached by file hash.
- **Extraction** — one cheap structured-output LLM pass → card + atomic facts (with page/bbox).
- **Storage** — PostgreSQL 16 + pgvector. Typed tables + vector index + observability logs.
- **Retrieval** — intent router → metadata/SQL, lexical (FTS/BM25), two-stage vector, rerank.
- **Synthesis** — grounded answer with citations; explicit "unsupported" path.
- **Workers** — background processing (later, via Redis queue).
- **Feedback & metering** — `answer_ratings` close the quality loop (into eval); `usage_events` + `usage_counters` drive analytics and quota/billing.

## Pipeline
```
ingest → OCR routing → structured extraction → store (card + facts + embeddings)
                                                   ↓
chat query → intent router → [metadata SQL | FTS | vector ×2-stage] → rerank → grounded synthesis (+citations)
```

## Flow A — document uploaded
1. `documents` row created at status `received`; dedup via `(account_id, file_hash)`.
2. OCR (writes `ocr_text`, engine, page_count) → status `ocr_done`.
3. Extraction: one LLM call; raw response saved, then fanned into card tables + atomic facts → `extracted`.
4. Embeddings computed (facts + summary) → status `indexed`.
5. Each stage appends a row to `processing_events` (started/succeeded/failed). Trace a doc = read its status + events.

## Flow B — chat message
1. `messages(user)` row inserted.
2. Router picks intent; retrieval runs **account-scoped** (metadata / FTS / two-stage vector), merged + reranked.
3. Synthesis feeds only top facts (+typed metadata) to the model; answer carries citations.
4. `messages(assistant)` + one `retrieval_traces` row written together. Trace an answer = read its `retrieval_traces` row.

## Tenancy
- Boundary is `account_id`, present on every table. Personal = 1-member account; company = N members, equal rights. No RBAC yet.
- Isolation enforced at the **data layer** (RLS or a single mandatory scoping function) so unscoped queries are impossible.

## Observability spine
- Pipeline: `processing_events` (append-only) + `status` on `documents`.
- Retrieval: `retrieval_traces` (query, plan, candidates, reranked, context_sent, answer, citations, tokens, latency).
- Intermediate artifacts stored (`ocr_text`, `extraction_raw`, `context_sent`) so debugging is a SELECT, not a re-run.
- Token counts on both logs → cost-per-document and cost-per-query for free.

## Models (runtime)
- OCR: Google Vision. Extraction: GPT-4o-mini / DeepSeek (cheap). Synthesis: GPT-4o (+hard cases). Embeddings: local `bge-base-en-v1.5` (768-d). See `TECH_SPEC.md`.

## Deploy
Native services now → Docker (same compose) at MVP → Contabo VPS. Identical roles/ports across the move.
