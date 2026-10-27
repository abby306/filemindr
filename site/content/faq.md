---
title: "Filemindr FAQ: Open-Source RAG Requirements and Limits"
nav_title: FAQ & limitations
description: "Answers about Filemindr: what it is, whether it's free and self-hosted, which APIs it needs, offline use, formats, and current limitations."
---

# Frequently asked questions

## What is Filemindr?

Filemindr is an open-source RAG (retrieval-augmented generation) application and document intelligence platform. It ingests PDFs, scans, photos and Word files, OCRs them, extracts structured facts with an LLM, files them into an archive, and answers questions with page-level citations. The source is at [github.com/abby306/filemindr](https://github.com/abby306/filemindr).

## Is Filemindr free and open source?

Yes. It is licensed under **AGPL-3.0**. You can use, modify and self-host it. If you run a modified version as a network service, you must publish your changes under the same license. For other licensing terms, open an issue on GitHub.

## What is it built with?

A Python 3.12 / FastAPI backend, PostgreSQL 16 with pgvector and built-in full-text search, local BGE embedding and reranker models via sentence-transformers, and a Next.js / React / TypeScript web app. See [Architecture](architecture.md).

## Is it self-hosted? Does it work offline?

It is **self-hostable** but **not offline**. The database, files, embeddings and reranking run on your server. Structured extraction (DeepSeek or another OpenAI-compatible endpoint), answering (Google Gemini) and OCR of scans and images (Google Cloud Vision) call hosted APIs, so document text is sent to those providers. GPT-4o escalation is optional.

## Can I use a local LLM (Ollama, vLLM, llama.cpp)?

Partly, and untested. Extraction goes through the OpenAI-compatible client, so `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` can point at any compatible server that supports JSON mode. Answering is written against the Gemini SDK's function calling. There's a single seam for it (`_gemini_turn` in `app/services/synthesis.py`), but there's no local-model implementation yet. Contributions are welcome.

## Which file formats are supported?

PDF (text-layer and scanned), DOCX, PNG and JPEG, up to 50 MB by default. See [OCR and document processing](features/ocr-document-processing.md).

## What makes its retrieval different from basic vector search?

It combines structured lookups over extracted typed facts, Postgres full-text search, and two-stage pgvector search. The results are fused with weighted Reciprocal Rank Fusion and reranked by a cross-encoder. See [Hybrid search](features/hybrid-search.md).

## How are answers kept grounded?

The model can only cite fact ids that retrieval handed it. Invalid ids are dropped, and every citation resolves to a real document and page (plus a bounding box for atomic facts). The model has an explicit "not supported" outcome and is told not to use outside knowledge. See [Agentic RAG and citations](features/agentic-rag-citations.md).

## Is it production-ready?

Not for exposure to the public internet as shipped. The backend and web app are tested (285 offline tests and CI on every push), but authentication is dev-grade, background jobs aren't durable across restarts, and data at rest isn't encrypted. It suits evaluation, development, and trusted single-team deployments behind your own authentication. See the [self-hosting security checklist](self-hosting.md#security-checklist).

## Does it support multiple users or teams?

There are personal and company accounts with full data isolation by `account_id`. Members of a company account have equal rights (no RBAC yet), and real login is not implemented in the open-source build.

## How good is retrieval quality?

There's an evaluation harness (`eval/`) with `doc_recall@k`, `fact_recall@k` and `answer_correctness` metrics and a gold set for the demo corpus. No benchmark numbers are published. Run it on your own documents to judge.

## Which languages does it handle?

OCR (Google Vision) handles many languages, but retrieval is tuned for English: `bge-base-en-v1.5` embeddings and the `english` full-text configuration.

## How do I contribute?

Read [`CONTRIBUTING.md`](https://github.com/abby306/filemindr/blob/main/CONTRIBUTING.md). Keep every query account-scoped, make schema changes through Alembic only, and keep the test suite offline. Open an issue before large changes.
