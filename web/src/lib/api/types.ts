/**
 * API response types mirroring the backend Pydantic schemas (`app/api/schemas.py`).
 * These are transport shapes only — no derived fields. Anything computed lives
 * server-side per the thin-client contract.
 */

/** Document pipeline status enum (`documents.status`). */
export type DocumentStatus =
  | "received"
  | "ocr_done"
  | "extracted"
  | "indexed"
  | "failed"
  | "needs_review";

export type ReviewReason =
  | "no_class"
  | "low_confidence"
  | "ambiguous"
  | null;

/** Light list/ingest view — `DocumentOut`. */
export interface DocumentSummary {
  id: string;
  status: DocumentStatus;
  review_reason: ReviewReason;
  source: string;
  original_filename: string;
  mime_type: string | null;
  byte_size: number | null;
  title: string | null;
  summary: string | null;
  language: string | null;
  page_count: number | null;
  created_at: string;
}

/** `DocumentListOut`. */
export interface DocumentListResponse {
  items: DocumentSummary[];
  next_cursor: string | null;
}

/** A class as it appears on a document's card (`ClassCardOut`). */
export interface ClassCardInfo {
  slug: string;
  name: string | null;
  confidence: number | null;
  assigned_by: string | null;
  parent_slug: string | null;
  is_primary: boolean;
}

export interface EntitiesInfo {
  people: string[];
  organizations: string[];
  places: string[];
}

export interface DateInfo {
  value: string | null;
  raw_text: string | null;
  role: string;
}

export interface TypedFactInfo {
  label: string;
  value: string | null;
  value_numeric: number | null;
  type: string;
  unit: string | null;
  page: number | null;
}

/** `DocumentCardOut` — the detail view (list fields + extracted card). */
export interface DocumentCard extends DocumentSummary {
  classes: ClassCardInfo[];
  entities: EntitiesInfo;
  dates: DateInfo[];
  typed_facts: TypedFactInfo[];
  fact_count: number;
}

/** `FactRegionOut` — an atomic fact's location for provenance overlay.
 *  `bbox` is normalized `[x, y, w, h]` in [0,1], or null (→ page-level highlight). */
export interface FactRegion {
  id: string;
  page: number | null;
  text: string | null;
  bbox: number[] | null;
}

/** `ConversationListItem` — a chat in the rail. */
export interface ConversationListItem {
  id: string;
  title: string | null;
  preview: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

/** `MessageOut` — a stored turn (history; no citations replayed). */
export interface MessageHistoryItem {
  id: string;
  role: "user" | "assistant";
  content: string | null;
  created_at: string;
}

/** `CitationGroupOut` — citations grouped by document (one pill per source). */
export interface CitationGroup {
  document_id: string;
  title: string | null;
  pages: number[];
  fact_ids: string[];
}

/** `ClassOut` — a catalog class, with its place in the two-level taxonomy. */
export interface ClassInfo {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  parent_id: string | null;
  parent_slug: string | null;
  is_system: boolean;
  document_count: number;
}

/* --- analytics (Phase 7) --------------------------------------------------- */

/** `SeriesPointOut` — one zero-filled day of a time series. */
export interface SeriesPoint {
  date: string;
  count: number;
  cumulative: number | null;
}

export interface TopClass {
  slug: string;
  name: string;
  count: number;
}

export interface MostAskedDocument {
  document_id: string;
  title: string | null;
  count: number;
}

/** `AnalyticsUsageOut` — documents/storage are archive totals; queries/tokens in-range. */
export interface AnalyticsUsage {
  range_days: number;
  documents: number;
  queries: number;
  storage_bytes: number;
  token_spend: number;
  series: {
    documents_over_time: SeriesPoint[];
    queries_per_day: SeriesPoint[];
  };
  top_classes: TopClass[];
  most_asked_documents: MostAskedDocument[];
}

/** `AnalyticsQualityOut` — a metric is null until there is data behind it. */
export interface AnalyticsQuality {
  answer_rating_pct: number | null;
  grounded_pct: number | null;
  avg_retrieval_ms: number | null;
  extraction_success_pct: number | null;
  ratings_count: number;
  answers_count: number;
}

/* --- billing (Phase 7) ------------------------------------------------------ */

/** Plan `limits` jsonb — null means unlimited. */
export interface PlanLimits {
  documents: number | null;
  storage_gb: number | null;
  queries_per_month: number | null;
  features?: string[];
}

export interface Plan {
  slug: string;
  name: string;
  price_cents: number;
  currency: string;
  limits: PlanLimits;
}

export interface Subscription {
  plan: Plan;
  status: string;
  period_end: string | null;
  usage: {
    documents: number;
    queries: number;
    storage_bytes: number;
  };
  limits: PlanLimits;
}

export interface CheckoutSession {
  checkout_url: string;
  session_id: string;
}

export interface Invoice {
  id: string;
  amount_cents: number;
  currency: string;
  status: string;
  period: string | null;
  created_at: string;
}

export interface InvoiceList {
  items: Invoice[];
}
