# TASKS.md — filemindr

Live backlog. Move items between sections; keep entries one line. `[ ]` todo, `[~]` in progress, `[x]` done.

## Done
- [x] Dev environment: Ubuntu 26.04, pyenv 3.12, project scaffold.
- [x] Native PostgreSQL 16 + pgvector (PGDG); role/db `filemindr`; extension enabled.
- [x] Native Redis.
- [x] Core Python libraries installed (FastAPI, SQLAlchemy, psycopg, pgvector, alembic, openai, google-cloud-vision, pymupdf, python-docx).
- [x] `setup.md` + project docs (AGENTS/PRD/ARCHITECTURE/TECH_SPEC/TASKS/CODING_STANDARDS/API_CONTRACTS).

## In progress
- [x] Apply baseline schema (Alembic `0001` / `schema.sql`) at `vector(768)` — applied (21 tables + `v_document_pipeline`, `vector` 0.8.3, plans seeded).

## Done (recent)
- [x] Lock embedding model → `bge-base-en-v1.5`, `vector(768)`; install `sentence-transformers`.

## Next up
- [x] Schema as Alembic migration: identity/tenancy + documents/card + vector + observability tables + `v_document_pipeline`.
- [x] Account scoping at data layer — **mandatory scoping function** (`AccountScope`/`get_current_account`); RLS deferred.
- [x] FastAPI skeleton: settings (pydantic-settings), DB session, health endpoint.
- [x] Phase 1 foundations: ORM models (document-core), minimal bearer-token auth, `GET /api/v1/me`, seed script (personal + company + default classes), unit tests (config/DB/scoping/routes — 19 passing).

### Phase 1 follow-ups
- [ ] Map remaining tables in `models.py` (chat, observability, billing) as their phases arrive.
- [ ] Replace dev bearer-token auth with a real mechanism (session/JWT); decide on RLS as defence-in-depth.
- [ ] Add `CODING_STANDARDS.md` (referenced by AGENTS/CLAUDE but missing on disk).
- [ ] Fix `ARCHITECTURE.md` embeddings line (says `bge-small`/384-d; should be `bge-base`/768-d).

## Backlog — by build phase
**Ingest**
- [x] Web upload endpoint (PDF/PNG/JPG/docx); persist raw file (sha256, atomic write); hash dedup; `received` status; `GET /documents` + `GET /documents/{id}` (account-scoped, keyset paginated).
- [ ] Email-in pipeline (per-account alias; parse attachments + body).

**OCR**
- [x] PDF text-layer probe (fitz) → Google Vision fallback; docx extract; image → Vision. Runs as a FastAPI BackgroundTask (Redis worker later).
- [x] OCR cache keyed by file hash; language detection (langdetect / Vision locale); keep Vision block bboxes; `processing_events` logged; status → `ocr_done` (or `failed`).

**Extraction**
- [x] Structured-output schema + cheap LLM pass (DeepSeek, page-window chunked) → card + atomic facts.
- [x] Write card tables; store `extraction_raw`; confidence routing to `needs_review`.
- [x] Embed atomic facts + summary (`bge-base`, local); `indexed` status; both HNSW stages indexed.

**Retrieval** (service layer ✅)
- [x] Intent router (rules); structured-first (typed_facts/dates/entities); FTS + typed-fact/entity exact-match; two-stage vector; RRF fusion (`retrieval.py`).
- [x] Cross-encoder reranker (`bge-reranker-base`) blended with RRF, α=0.4 (`reranking.py`).
- [x] Optional scoping (`document_ids`/`class_slug`); account-scoped throughout. Validated on a real 13-doc corpus (`doc_recall 1.00`).

**Synthesis** (service layer ✅)
- [x] Agentic, corpus-aware grounded answers with citations + `supported` path (`synthesis.py`, Gemini 2.5 Flash + `find_documents`/`search`/`finish` tools).
- [x] Conversation memory + `chat()` (`conversations.py`); document catalog (`catalog.py`); CLIs (`ask`, `chat`, `retrieve`, `eval_retrieval`, `seed_corpus`).
- [x] Chat HTTP endpoints (`POST /conversations`, `POST /conversations/{id}/messages` incl. `scope="document"`, `GET /conversations/{id}/messages`); map `RetrievalTrace` ORM + write one `retrieval_traces` row per answer (`conversations.record_trace`).
- [x] SSE streaming (`POST /conversations/{id}/messages/stream` via `synthesize_iter`); GPT-4o hard-synthesis escalation on `supported=false`; `scripts/eval_synthesis.py` (answer_correctness); fuller trace cols (candidates/context_sent). **Phase 5 complete.**
- [x] Ratings endpoint `POST /messages/{id}/rating` + `AnswerRating` ORM (pulled forward from Phase 7 for testing); dev-only testing UI at `/dev/` (uncommitted `dev_ui/`).
- [x] Class-catalog API: `GET/POST/DELETE /classes` (custom classes, system immutable) + `GET /documents?class=<slug>` filter (per `API_CONTRACTS.md`). New classes apply to the *next* extraction; existing docs need re-extraction to be re-classified.

**Quality**
- [x] Eval harness scaffold: gold queries, recall@k, answer correctness (`eval/`); `scripts/eval_retrieval.py` scores live retrieval.
- [ ] Wire `synthesize` into eval for `answer_correctness`; refresh gold set to real corpus UUIDs.

**Frontend (design system in `FRONTEND.md` / design PDF)**
- [ ] Design tokens → Tailwind/CSS vars (light + dark); Inter + Geist Mono; base components on Radix.
- [ ] Upload screen: dropzone + optimistic cards + live pipeline fill.
- [ ] Document view: card, classification + confidence, typed facts with provenance jump, add/label classes.
- [ ] Ask screen: streaming answer + retrieval trace reveal + click-to-source citations + scope toggle.
- [ ] Ratings: thumb + diagnostic reasons on each answer.
- [ ] Framer Motion: the 3 signature motions; honor reduced-motion.

**Analytics & billing (fast-follow)**
- [ ] `usage_events` + `usage_counters`; analytics endpoints (usage + quality).
- [ ] Analytics page: usage + quality dashboards (Recharts/Visx).
- [ ] Plans/subscriptions/invoices tables; billing endpoints; checkout (provider-hosted).
- [ ] Billing page: plan card, usage meters, pricing cards, invoices.
- [ ] Quota enforcement on write paths (402/429 + upgrade hint).

**Later (post-v1)**
- [ ] Voice agent, WhatsApp ingest, PDF compilation, smart collections, expiry reminders, share links.
- [ ] Dockerize + deploy to Contabo.
