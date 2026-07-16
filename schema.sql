-- filemindr schema (canonical DDL)
-- Embedding model: BAAI/bge-base-en-v1.5  ->  vector(768)
-- Apply with:  psql "$DATABASE_URL" -f schema.sql   (or via the Alembic 0001 migration)

SET maintenance_work_mem = '1GB';

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- enum types
-- ---------------------------------------------------------------------------
CREATE TYPE account_type        AS ENUM ('personal', 'company');
CREATE TYPE member_role         AS ENUM ('member', 'admin', 'owner');
CREATE TYPE document_source     AS ENUM ('web_upload', 'email_in');
CREATE TYPE document_status     AS ENUM ('received', 'ocr_done', 'extracted', 'indexed', 'failed', 'needs_review');
CREATE TYPE ocr_engine          AS ENUM ('pdf_text_layer', 'google_vision', 'docx');
CREATE TYPE assigned_by         AS ENUM ('model', 'user');
CREATE TYPE entity_type         AS ENUM ('person', 'organization', 'place');
CREATE TYPE date_role           AS ENUM ('issued', 'due', 'expiry', 'event', 'mentioned');
CREATE TYPE value_type          AS ENUM ('money', 'number', 'date', 'id', 'string');
CREATE TYPE message_role        AS ENUM ('user', 'assistant');
CREATE TYPE event_stage         AS ENUM ('received', 'ocr', 'extraction', 'embedding', 'indexing');
CREATE TYPE event_status        AS ENUM ('started', 'succeeded', 'failed');
CREATE TYPE rating_value        AS ENUM ('up', 'down');
CREATE TYPE subscription_status AS ENUM ('active', 'past_due', 'canceled');

-- ---------------------------------------------------------------------------
-- shared updated_at trigger
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- identity & tenancy
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounts (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  type        account_type NOT NULL,
  name        text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text UNIQUE NOT NULL,
  name          text,
  password_hash text,
  is_active     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS account_members (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role        member_role NOT NULL DEFAULT 'member',
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (account_id, user_id)
);

CREATE TABLE IF NOT EXISTS classes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  slug        text NOT NULL,
  name        text NOT NULL,
  description text,
  is_system   boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (account_id, slug)
);

-- ---------------------------------------------------------------------------
-- documents & extracted card
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id        uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  uploaded_by       uuid REFERENCES users(id) ON DELETE SET NULL,
  source            document_source NOT NULL,
  original_filename text NOT NULL,
  mime_type         text,
  byte_size         bigint,
  file_hash         text NOT NULL,
  storage_path      text NOT NULL,
  title             text,
  summary           text,
  summary_long      text,
  language          text,
  page_count        int,
  status            document_status NOT NULL DEFAULT 'received',
  error             text,
  ocr_text          text,
  ocr_engine        ocr_engine,
  extraction_raw    jsonb,
  extraction_model  text,
  summary_embedding vector(768),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (account_id, file_hash)
);
CREATE INDEX IF NOT EXISTS documents_account_status_idx  ON documents (account_id, status);
CREATE INDEX IF NOT EXISTS documents_account_created_idx ON documents (account_id, created_at DESC);
-- Stage 1 of two-stage vector retrieval: pick candidate documents by summary.
CREATE INDEX IF NOT EXISTS documents_summary_embedding_hnsw
  ON documents USING hnsw (summary_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE TABLE IF NOT EXISTS document_classes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  class_id    uuid NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  confidence  real,
  assigned_by assigned_by NOT NULL DEFAULT 'model',
  is_primary  boolean NOT NULL DEFAULT false,  -- the single class that owns the doc's folder placement
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, class_id)
);
CREATE INDEX IF NOT EXISTS document_classes_class_idx   ON document_classes (class_id);
CREATE INDEX IF NOT EXISTS document_classes_account_idx ON document_classes (account_id);
-- at most one primary class per document
CREATE UNIQUE INDEX IF NOT EXISTS document_classes_one_primary_idx ON document_classes (document_id) WHERE is_primary;

CREATE TABLE IF NOT EXISTS entities (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id      uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  name            text NOT NULL,
  normalized_name text NOT NULL,
  type            entity_type NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (account_id, type, normalized_name)
);

CREATE TABLE IF NOT EXISTS document_entities (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id    uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  document_id   uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  entity_id     uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  mention_count int NOT NULL DEFAULT 1,
  UNIQUE (document_id, entity_id)
);
CREATE INDEX IF NOT EXISTS document_entities_entity_idx ON document_entities (entity_id);

CREATE TABLE IF NOT EXISTS document_dates (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  value       date,
  raw_text    text,
  role        date_role NOT NULL DEFAULT 'mentioned',
  page        int,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS document_dates_account_value_idx ON document_dates (account_id, value);
CREATE INDEX IF NOT EXISTS document_dates_document_idx      ON document_dates (document_id);

CREATE TABLE IF NOT EXISTS typed_facts (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id    uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  document_id   uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  label         text NOT NULL,
  value         text,
  value_numeric numeric,
  value_type    value_type NOT NULL DEFAULT 'string',
  unit          text,
  page          int,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS typed_facts_account_label_idx ON typed_facts (account_id, label);
CREATE INDEX IF NOT EXISTS typed_facts_numeric_idx       ON typed_facts (value_numeric);
CREATE INDEX IF NOT EXISTS typed_facts_document_idx      ON typed_facts (document_id);

-- ---------------------------------------------------------------------------
-- atomic facts (primary retrieval unit)
-- ---------------------------------------------------------------------------
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
CREATE INDEX IF NOT EXISTS document_facts_document_idx ON document_facts (document_id);
CREATE INDEX IF NOT EXISTS document_facts_account_idx  ON document_facts (account_id);
CREATE INDEX IF NOT EXISTS document_facts_fts_gin      ON document_facts USING gin (fts);
CREATE INDEX IF NOT EXISTS document_facts_embedding_hnsw
  ON document_facts USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------------
-- chat & retrieval observability
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
  title       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id      uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role            message_role NOT NULL,
  content         text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_conversation_idx ON messages (conversation_id, created_at);

CREATE TABLE IF NOT EXISTS retrieval_traces (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id        uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  message_id        uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  query_text        text,
  intent            text,
  retrieval_plan    jsonb,
  candidates        jsonb,
  reranked          jsonb,
  context_sent      jsonb,
  answer            text,
  citations         jsonb,
  model             text,
  prompt_tokens     int,
  completion_tokens int,
  latency_ms        int,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS retrieval_traces_message_idx ON retrieval_traces (message_id);
CREATE INDEX IF NOT EXISTS retrieval_traces_account_idx ON retrieval_traces (account_id, created_at DESC);

CREATE TABLE IF NOT EXISTS processing_events (
  id          bigserial PRIMARY KEY,
  account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  stage       event_stage NOT NULL,
  status      event_status NOT NULL,
  detail      jsonb,
  error       text,
  duration_ms int,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS processing_events_document_idx ON processing_events (document_id, created_at);
CREATE INDEX IF NOT EXISTS processing_events_account_idx  ON processing_events (account_id, status);

-- ---------------------------------------------------------------------------
-- feedback, usage & billing
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS answer_ratings (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  message_id  uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
  rating      rating_value NOT NULL,
  stars       int CHECK (stars BETWEEN 1 AND 5),
  reasons     text[],
  comment     text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS answer_ratings_account_idx ON answer_ratings (account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS answer_ratings_message_idx ON answer_ratings (message_id);

CREATE TABLE IF NOT EXISTS usage_events (
  id          bigserial PRIMARY KEY,
  account_id  uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
  type        text NOT NULL,
  metadata    jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS usage_events_account_created_idx ON usage_events (account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS usage_events_account_type_idx    ON usage_events (account_id, type);

CREATE TABLE IF NOT EXISTS plans (
  slug        text PRIMARY KEY,
  name        text NOT NULL,
  price_cents int NOT NULL DEFAULT 0,
  currency    text NOT NULL DEFAULT 'USD',
  limits      jsonb NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS subscriptions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  plan_slug    text NOT NULL REFERENCES plans(slug),
  status       subscription_status NOT NULL DEFAULT 'active',
  period_start timestamptz,
  period_end   timestamptz,
  external_ref text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS subscriptions_one_active_idx
  ON subscriptions (account_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS invoices (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id   uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  amount_cents int NOT NULL,
  currency     text NOT NULL DEFAULT 'USD',
  status       text NOT NULL,
  period       text,
  external_ref text,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS invoices_account_idx ON invoices (account_id, created_at DESC);

CREATE TABLE IF NOT EXISTS usage_counters (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id    uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  period        text NOT NULL,
  documents     int NOT NULL DEFAULT 0,
  queries       int NOT NULL DEFAULT 0,
  storage_bytes bigint NOT NULL DEFAULT 0,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (account_id, period)
);

-- ---------------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------------
CREATE TRIGGER trg_accounts_updated       BEFORE UPDATE ON accounts       FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_users_updated          BEFORE UPDATE ON users          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_classes_updated        BEFORE UPDATE ON classes        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_documents_updated      BEFORE UPDATE ON documents      FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_conversations_updated  BEFORE UPDATE ON conversations  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_plans_updated          BEFORE UPDATE ON plans          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_subscriptions_updated  BEFORE UPDATE ON subscriptions  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_usage_counters_updated BEFORE UPDATE ON usage_counters FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- debug view: one row per document with pipeline state + counts
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_document_pipeline AS
SELECT
  d.id,
  d.account_id,
  d.original_filename,
  d.title,
  d.status,
  d.error,
  d.page_count,
  d.created_at,
  d.updated_at,
  le.stage  AS last_stage,
  le.status AS last_event_status,
  le.created_at AS last_event_at,
  (SELECT count(*) FROM document_facts    f WHERE f.document_id = d.id) AS fact_count,
  (SELECT count(*) FROM document_classes  c WHERE c.document_id = d.id) AS class_count,
  (SELECT count(*) FROM document_entities e WHERE e.document_id = d.id) AS entity_count
FROM documents d
LEFT JOIN LATERAL (
  SELECT pe.stage, pe.status, pe.created_at
  FROM processing_events pe
  WHERE pe.document_id = d.id
  ORDER BY pe.created_at DESC
  LIMIT 1
) le ON true;

-- ---------------------------------------------------------------------------
-- seed: subscription plans
-- ---------------------------------------------------------------------------
INSERT INTO plans (slug, name, price_cents, limits) VALUES
  ('free', 'Free', 0,      '{"documents": 100,  "queries_per_month": 50,   "storage_gb": 1,  "features": []}'),
  ('pro',  'Pro',  1500,   '{"documents": 5000, "queries_per_month": 2000, "storage_gb": 25, "features": ["priority_ocr"]}'),
  ('team', 'Team', 5000,   '{"documents": null, "queries_per_month": null, "storage_gb": 250,"features": ["shared_accounts", "audit"]}')
ON CONFLICT (slug) DO NOTHING;
