# API_CONTRACTS.md — filemindr

Interface contracts for the v1 API. **Draft** — shapes will firm up as endpoints are built. Add/adjust fields at a low level; keep the overall shape stable.

## Conventions
- Base path `/api/v1`. JSON in/out. Auth required (mechanism TBD); the authenticated request resolves a **user** + **active account**.
- All resources are implicitly scoped to the active `account_id`; it is never passed by the client for scoping.
- IDs are UUID strings. Timestamps are ISO-8601 UTC.
- Errors: `{ "error": { "code": str, "message": str } }` with appropriate HTTP status.
- CORS: the API allows configured origins (`cors_origins`) so the web/native client can call it directly. Dev uses a same-origin rewrite, so CORS only matters in prod.

## Documents

### POST /documents (upload)
Multipart file upload. Returns the created document in `received` state.
- Req: `multipart/form-data` — `file` (pdf/png/jpg/docx).
- Res `201`: `{ id, status, original_filename, mime_type, byte_size, created_at }`
- Dedup: identical `(account, file_hash)` returns the existing document (`200`).

### GET /documents
List documents (paginated, filterable).
- Query: `status?`, `class?`, `primary?` (bool), `q?` (text), `limit?`, `cursor?`
- Res `200`: `{ items: [DocumentCard], next_cursor }`
- `class` matches any label by default (recall). With `primary=true` it matches only documents whose **primary** class falls under that slug — one document → one folder (the archive browse view). Subclass-aware either way (a parent slug includes its children).
- Each item carries `primary_class: { slug, name } | null` — the document's folder for list views (batch-loaded server-side; null until extraction assigns a class). Also present on the detail card.

### GET /documents/{id}
- Res `200`: full `DocumentCard` (see schema below).

### GET /documents/{id}/file
- Streams the original stored file (`Content-Type` = the document's mime; `Content-Disposition` filename = original). For download / pdf.js. `404` unknown/foreign or missing file.

### GET /documents/{id}/facts
- Atomic facts with a page + normalized bbox for provenance overlay (SourceGlow).
- Res `200`: `[{ id, page, text, bbox: [x, y, w, h] | null }]` — `bbox` is in [0,1] (PDFs only; null → page-level highlight).

### GET /documents/{id}/pages/{page}
- Renders one page as an image for the source pane / thumbnails. PDFs are rasterized (PNG) and cached; raster images pass through as-is (single page). Query `dpi?` (72–300, default 144).
- Res `200`: image bytes. `404` unknown/foreign/missing or out-of-range page; `415` for a type with no page image (e.g. docx).

### DELETE /documents/{id}
- Res `204`.

## Classes

### GET /classes — list predefined + custom classes.
### POST /classes — create custom class `{ name, description }` → `201`.
### PATCH /classes/{id} — rename a custom class `{ name }` (slug stays stable; system classes `409`).
### DELETE /classes/{id} — remove a custom class (system classes immutable).

### POST /documents/{id}/classes — assign classes (human-in-the-loop).
- Req: `{ class_ids?: [uuid], new_class?: { name, description?, parent_id? }, mode?: "add"|"replace"|"set_primary" }`
- `mode="replace"` (default) swaps in the picked classes (review/move); `mode="add"` appends them alongside existing labels; `mode="set_primary"` makes the first picked class the primary while keeping the document's other labels (drag-to-folder move without losing secondary labels). Clears the review flag and advances `needs_review → indexed`. Res `200`: full `DocumentCard`.

## Chat / query

### GET /conversations
List the account's conversations (most-recently-updated first) for the chat rail / continue-any-chat.
- Res `200`: `[{ id, title, preview, message_count, created_at, updated_at }]` — `title` is derived server-side from the first user message; `preview` is the last message.

### POST /conversations → `{ id }`
### POST /conversations/{id}/messages
Send a user message; get a grounded answer.
- Req: `{ content, scope?: "account"|"document", document_id? }`
- Res `200`:
```json
{
  "message_id": "uuid",
  "answer": "text",
  "citations": [
    { "document_id": "uuid", "title": "…", "page": 3, "fact_id": "uuid" }
  ],
  "citation_groups": [
    { "document_id": "uuid", "title": "…", "pages": [3, 7], "fact_ids": ["uuid", "uuid"] }
  ],
  "supported": true
}
```
- `citation_groups` collapses repeated same-document citations into one source (server-side; also on the SSE `done` event) so clients render one pill per document.
- `supported=false` ⇒ answer states the documents don't contain it; `citations` may be empty.

### POST /conversations/{id}/messages/stream (SSE)
Same request body; `text/event-stream` narrating the real work, then the answer:
- `conversation` `{conversation_id}` → `intent` `{intent}` → `retrieved` (initial candidate pool) → `thinking` `{step}` (before **every** model turn — fills the otherwise-silent seconds) → any of `find_documents` / `searching` / `escalating` `{model}` → `done` (payload above + `conversation_id`) or `error` `{message}` (the user message is already saved).
- Retrieval steps are **transparent**: `retrieved` and `searching` carry `{found, documents?, query?, sources: [{title, facts}], more_documents, highlights: [str]}` — the matched documents (best-first, per-doc hit counts) and trimmed matched-fact snippets, display-ready; `find_documents` carries `{query, found, sources: [{title}]}`. Clients render these so the user sees exactly which files were read and what matched.

### GET /conversations/{id}/messages — message history.

## Email-in (webhook)

### POST /ingest/email
Inbound email handler (provider webhook). Resolves account by recipient alias, ingests attachments + body as documents.
- Auth: provider signature / shared secret (not user auth).
- Res `200` on accept.

## Ratings

### POST /messages/{id}/rating
Attach feedback to an answer.
- Req: `{ rating: "up"|"down", stars?: 1-5, reasons?: ["not_grounded"|"missing_doc"|"wrong_number"|"wrong_document"], comment?: string }`
- Res `200`: `{ ok: true }`. Writes `answer_ratings` linked to the message's retrieval trace.

## Analytics

All numbers are derived server-side (thin-client contract) and account-scoped.

### GET /analytics/usage
- Query: `range?` — `7d` | `30d` | `90d` (default `30d`; anything else `422`).
- Res `200`: `{ range_days, documents, queries, storage_bytes, token_spend, series: { documents_over_time: [SeriesPoint], queries_per_day: [SeriesPoint] }, top_classes: [{slug, name, count}], most_asked_documents: [{document_id, title, count}] }`
- `documents`/`storage_bytes` are **archive totals** (it's an archive); `queries`/`token_spend` are within the range. `SeriesPoint = { date, count, cumulative? }` — series are zero-filled per day; `documents_over_time.cumulative` is the running archive size (seeded with pre-range uploads). `top_classes` counts **primary** classes (matches the archive's one-doc-one-folder view); `most_asked_documents` counts distinct answers citing each doc (from `retrieval_traces.citations`).

### GET /analytics/quality
- Res `200`: `{ answer_rating_pct, grounded_pct, avg_retrieval_ms, extraction_success_pct, ratings_count, answers_count }`
- All-time. A metric is `null` (not 0) until there is data behind it; the `*_count` fields let clients caption the percentages honestly.

## Billing

### GET /billing/plans → list `plans` with limits (cheapest first). `limits` values of `null` mean unlimited.
### GET /billing/subscription
- Res `200`: `{ plan, status, period_end, usage: { documents, queries, storage_bytes }, limits: {...} }`
- No subscription row ⇒ the implicit **free** plan (`status: "active"`, `period_end: null`). `usage` comes from the same source quota enforcement reads, so meters and 402s always agree (`queries` is the current calendar month; documents/storage are account totals).
### POST /billing/checkout
- Req: `{ plan_slug }` → Res `200`: `{ checkout_url, session_id }` (provider-hosted page). `404` unknown plan, `400` for the free plan (no checkout needed).
### POST /billing/checkout/complete
- Req: `{ session_id }` → Res `200`: the updated subscription (activates the plan + writes a paid invoice). **Mock-provider stand-in for the payment webhook**: with real Stripe this is replaced by a signature-verified `POST /billing/webhook` calling the same `billing.activate_plan` (see `app/services/billing.py`). `400` invalid session.
### GET /billing/invoices → `{ items: [Invoice] }` (newest first).

> Quota: write paths (`POST /documents`, message creation) enforce plan limits and return **402** with `{ code: "quota_exceeded", message, kind, limit, current, plan, upgrade_hint: "/billing" }`. Document-count and storage caps are account totals (deleting a document frees quota); `queries_per_month` is a calendar-month counter (`usage_counters`). A dedup re-upload consumes no quota and is not metered.

### DocumentCard
```json
{
  "id": "uuid",
  "status": "received|ocr_done|extracted|indexed|failed|needs_review",
  "title": "string",
  "summary": "string",
  "language": "en",
  "page_count": 4,
  "classes": [{ "slug": "invoice", "confidence": 0.97, "is_primary": true, "parent_slug": "financial" }],
  "entities": { "people": [], "organizations": [], "places": [] },
  "dates": [{ "value": "2025-04-01", "role": "due" }],
  "typed_facts": [{ "label": "invoice_total", "value": "1240", "value_numeric": 1240, "type": "money", "unit": "USD" }],
  "created_at": "iso-8601"
}
```

## Not in v1 (placeholders)
- PDF compilation, smart collections, share links, voice endpoints, RBAC/permission fields.