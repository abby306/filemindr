# TECH_SPEC.md — filemindr

Schema, environment, and implementation detail. Living document — add/adjust columns and tables at a low level without restructuring.

## Environment
- OS: Ubuntu 26.04 LTS. Python 3.12 (pyenv), venv at `.venv`.
- DB: PostgreSQL 16 + pgvector (extension name `vector`). Native now → `pgvector/pgvector:pg16` at MVP.
- Cache/queue: Redis (`localhost:6379`), used once workers exist.
- Stack (backend): FastAPI, SQLAlchemy + psycopg, Alembic, Pydantic / pydantic-settings.
- OCR libs: PyMuPDF (`fitz`) for text-layer probe + rasterization, `google-cloud-vision`, `python-docx`; `langdetect` for language detection (Vision locale preferred when available).
- Stack (frontend): Next.js + TypeScript, Tailwind (design tokens as CSS vars), Radix UI, Framer Motion, Recharts/Visx, TanStack Query. Tokens & specs in `FRONTEND.md`.
- Connection: `postgresql+psycopg://filemindr:localdev@localhost:5432/filemindr`.

## Runtime models
| Role | Model | Notes |
|---|---|---|
| OCR | Google Vision | ✅ live (Phase 2); fallback when no PDF text layer; images always |
| Extraction | DeepSeek `deepseek-chat` | ✅ live (Phase 3); cheap structured-output pass (OpenAI-compatible client) |
| Synthesis | **Gemini 2.5 Flash** | ✅ live (Phase 5); agentic loop w/ tools + citations (`google-genai`). GPT-4o reserved as hard/low-confidence escalation (seam exists; not yet wired) |
| Reranking | `BAAI/bge-reranker-base` | ✅ live (Phase 5); local cross-encoder, CPU. Blended with RRF (α=0.4, consensus-primary) — see `reranking.py` |
| Embeddings | `bge-base-en-v1.5` | ✅ live (Phase 4); local, **768-dim**, CPU, zero per-token cost |

> Vector columns are `vector(768)`. If the embedding model changes, the new model must also output 768 dims — otherwise re-embed the corpus and rebuild the HNSW index.

## Schema (outline — full DDL lives in Alembic migrations)
Every table carries `account_id` (denormalized onto children) + `created_at` / `updated_at`.

**Identity & tenancy**
- `accounts` — type (`personal`|`company`), name.
- `users` — email (unique), name, auth fields.
- `account_members` — (account_id, user_id, role=`member`), unique pair. (`role` reserved for future RBAC.)
- `classes` — (account_id, slug, name, description, is_system); seeded per account. `description` feeds the classifier.

**Documents & card**
- `documents` — spine. source, original_filename, mime_type, byte_size, file_hash, storage_path; title, summary, summary_long, language, page_count; **status** (`received`→`ocr_done`→`extracted`→`indexed`, +`failed`/`needs_review`), error, `ocr_text`, ocr_engine, `extraction_raw` (jsonb), extraction_model, `summary_embedding vector(768)`. Unique `(account_id, file_hash)`.
- `document_classes` — (document_id, class_id, confidence, assigned_by). Multi-label; empty allowed.
- `entities` — (account_id, name, normalized_name, type `person|organization|place`), unique per account+type+normalized.
- `document_entities` — (document_id, entity_id, mention_count).
- `document_dates` — (document_id, value, raw_text, role `issued|due|expiry|event|mentioned`, page).
- `typed_facts` — (document_id, label, value, `value_numeric`, value_type, unit, page). Numeric queries use `value_numeric`, never the LLM.

**Vector / retrieval**
- `document_facts` — atomic facts; (document_id, text, page, bbox jsonb, `embedding vector(768)`, generated `tsvector` + GIN). Primary retrieval unit. HNSW index, cosine ops.

**Chat & observability**
- `conversations` — (account_id, user_id, title).
- `messages` — (conversation_id, role, content).
- `retrieval_traces` — (message_id, query_text, intent, retrieval_plan, candidates, reranked, context_sent, answer, citations, model, prompt_tokens, completion_tokens, latency_ms).
- `processing_events` — append-only; (document_id, stage, status, detail jsonb, error, duration_ms).

**Debug views**
- `v_document_pipeline` — one row/doc: status, error, latest event, counts of facts/classes/entities.

**Feedback, usage & billing**
- `answer_ratings` — (message_id, account_id, user_id, rating `up|down`, stars int?, reasons text[] from `not_grounded|missing_doc|wrong_number|wrong_document`, comment). Joins to the answer's `retrieval_traces` row; feeds Quality analytics + eval.
- `usage_events` — append-only; (account_id, user_id, type `upload|query|export|…`, metadata jsonb, created_at). Source for Usage analytics. (Most metrics also derive from `processing_events` / `retrieval_traces`.)
- `plans` — (slug `free|pro|team`, name, price, limits jsonb: `{documents, queries_per_month, storage_gb, features[]}`).
- `subscriptions` — (account_id, plan_slug, status `active|past_due|canceled`, period_start, period_end, external_ref). One active per account.
- `invoices` — (account_id, amount, currency, status, period, external_ref, created_at).
- `usage_counters` — (account_id, period, documents, queries, storage_bytes). Cheap quota checks without scanning; reset per period.

## Indexing
- `document_facts.embedding`: HNSW (`vector_cosine_ops`).
- `document_facts` tsvector: GIN.
- `documents`: `(account_id, status)`, `(account_id, created_at)`, unique `(account_id, file_hash)`.
- `typed_facts`: `(account_id, label)`, `value_numeric`.

## Retrieval implementation
1. Intent router (rules/cheap model) → `metadata | semantic | hybrid | aggregate`.
2. Metadata/SQL: typed_facts, dates, entities, classes (no LLM).
3. Lexical: Postgres FTS / BM25 for exact identifiers & names.
4. Vector: two-stage — `summary_embedding` to pick docs, then `document_facts` within.
5. Rerank: cross-encoder (e.g. bge-reranker) over merged candidates.
6. Synthesis: top reranked facts + metadata → answer with mandatory citations.

## Constraints
- 8 GB RAM: small local embedding model; conservative Postgres memory defaults.
- OCR cached by file hash; never re-OCR.
- Provenance (page/bbox) captured from the first pass.
- Account isolation enforced at the data layer (RLS or mandatory scoping function).
- Encryption-at-rest + access/audit log (sensitive corpus).

## Eval harness (v1 priority)
Gold set of 50–100 queries with expected doc/answer. Track recall@k + answer correctness. Run on every change to retrieval, chunking, or prompts.
