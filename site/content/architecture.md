---
title: "Filemindr Architecture: FastAPI, PostgreSQL and pgvector RAG"
nav_title: Architecture
description: "Filemindr's architecture: a FastAPI backend, PostgreSQL 16 with pgvector and full-text search, local BGE models, hosted LLMs and a Next.js thin client."
---

# Architecture: FastAPI, PostgreSQL, pgvector and the RAG pipeline

Filemindr is one FastAPI service, one PostgreSQL database and one Next.js web app. There is no separate vector database, search engine or message broker. This page explains how the parts fit together and why they're arranged that way. The design docs in [`agent_guide/`](https://github.com/abby306/filemindr/tree/main/agent_guide) go further.

## Design principle: retrieve over structure, not raw text

At ingest, each document is turned **once** into a *document card* (typed metadata) and *atomic facts* (self-contained sentences with page and bounding box). Raw OCR text is kept for citation checks and `read_page`, but retrieval runs over the structured data. Query-time context stays small, which keeps token costs down, and specific, which keeps answers accurate.

## Components

```text
               ┌──────────────────────── Next.js web app (thin client) ────────────────────────┐
               │ upload · archive · review · document view · ask (SSE) · analytics             │
               └───────────────────────────────┬────────────────────────────────────────────────┘
                                               │ JSON + SSE over /api/v1 (bearer + X-Account-Id)
┌──────────────────────────────────── FastAPI (app/) ────────────────────────────────────────────┐
│ api/        documents · conversations · classes · analytics · billing (mock)                    │
│ core/       config · auth seam · AccountScope tenancy · retry · bounded concurrency             │
│ services/   ocr → extraction → embeddings        (bounded background pipeline)                  │
│             retrieval → reranking → synthesis    (per question)                                 │
└───────┬──────────────────────────┬─────────────────────────────┬───────────────────────────────┘
        │                          │                             │
  PostgreSQL 16              local CPU models               hosted APIs
  pgvector HNSW              bge-base-en-v1.5               Google Vision (OCR, scans)
  tsvector + GIN             bge-reranker-base              DeepSeek (extraction)
  typed tables + logs                                       Gemini 2.5 Flash (answers)
  STORAGE_DIR (files)                                       GPT-4o (optional escalation)
```

## Request flows

**Upload (Flow A).** `POST /api/v1/documents` validates the type and size, hashes the bytes (SHA-256), deduplicates per account, stores the file under `STORAGE_DIR`, creates a `received` row and returns. A bounded thread pool then runs OCR → extraction → embedding. Each stage advances the status and appends a `processing_events` row. Details: [OCR and document processing](features/ocr-document-processing.md).

**Question (Flow B).** `POST /api/v1/conversations/{id}/messages/stream` stores the user message, runs [hybrid retrieval](features/hybrid-search.md) for the initial candidates, then the [agentic synthesis loop](features/agentic-rag-citations.md). Progress streams over SSE. The assistant message and a `retrieval_traces` row are written together.

## Data model highlights

| Table | Role |
|---|---|
| `accounts`, `users`, `account_members` | Personal (one member) and company (many members) accounts |
| `documents` | File metadata, status, OCR text, summary, `summary_embedding vector(768)` |
| `document_facts` | Atomic facts: text, page, bbox, `embedding vector(768)`, generated `fts tsvector` |
| `typed_facts`, `document_dates`, `entities` | Structured card data used by structured retrieval and aggregates |
| `classes`, `document_classes` | Hierarchical class catalog (system + per-account) and multi-label assignments with confidence |
| `processing_events` | Append-only per-stage pipeline log |
| `conversations`, `messages`, `retrieval_traces`, `answer_ratings` | Chat history, per-answer traces, and user feedback |
| `usage_events`, `usage_counters`, `plans`, `subscriptions`, `invoices` | Metering for analytics; quotas are off by default when self-hosting |

The schema is managed by **Alembic** (`alembic upgrade head`); `schema.sql` is the canonical DDL. Both HNSW indexes use `vector_cosine_ops` with `m = 16, ef_construction = 64`.

## Tenancy and isolation

Every table carries a denormalized `account_id`. HTTP routes resolve an `AccountScope` (authenticated user + an `X-Account-Id` they belong to), and services filter by `account_id` explicitly. Querying a model that lacks `account_id` through the scope raises an error at the call site, so a cross-account leak shows up as a programming error instead of a silent runtime risk. The test suite includes isolation tests.

## Why this shape

- **One database.** pgvector and Postgres full-text search live next to the relational data, so hybrid retrieval is a few SQL queries with joins and account filters, and there's no index sync between systems to keep consistent.
- **Local embeddings and reranking.** No per-token cost for indexing or reranking, and the vectors don't depend on a hosted embedding API.
- **One seam per external dependency.** Each provider call (`call_extraction_model`, `_gemini_turn`, `_encode`, `_score`, Vision) sits behind a single function. Tests stub these, which is why the suite of 285 tests runs offline in CI.
- **Thin client.** The web app holds no business logic; derived numbers come from the API, so other clients can reuse it unchanged.

## Known architectural limits

- The background pipeline is in-process (`ThreadPoolExecutor`). Jobs don't survive restarts; `scripts.reprocess` re-drives them. `REDIS_URL` is reserved for a future durable queue and is unused today.
- Authentication is a dev-grade bearer token (the user's UUID), behind a single seam: `app/core/auth.py::get_current_user`.
- Files are stored on the local filesystem with no encryption at rest.

Related: [Self-hosting](self-hosting.md) · [Configuration](configuration.md)
