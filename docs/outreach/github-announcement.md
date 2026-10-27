# GitHub announcement (draft)

**Where:** a pinned GitHub Discussion (Announcements category; Discussions is
currently disabled on the repo) or release notes for the first tagged release.
**Status:** draft — not published.

---

## Filemindr: open-source RAG & document intelligence platform

Filemindr is a self-hostable document archive with retrieval-augmented question
answering. You upload PDFs, scans, photos or Word files. It OCRs them, extracts a
structured card for each one (title, summary, classes, entities, dates, typed
facts, atomic facts), files them into an auto-built folder taxonomy, and answers
questions across the archive with citations down to the page, and to the
highlighted region where one is available.

**How it differs from a typical "chat with your PDF" app**

- Retrieval runs over **structured facts extracted once at ingest**, not raw text
  chunks. That's what makes questions like "how much is still unpaid?" or "when
  does the lease end?" work across many documents.
- **Hybrid retrieval in one PostgreSQL:** pgvector HNSW (two-stage: document
  summaries, then facts), Postgres full-text search plus identifier matching,
  and a structured retriever over typed facts. These are fused with weighted
  Reciprocal Rank Fusion and refined by a local cross-encoder
  (`bge-reranker-base`).
- **Agentic answering** (Gemini 2.5 Flash function calling) with
  `find_documents`, `search`, `read_page` and `finish` tools. Cited ids are
  validated, and "not in your documents" is an explicit outcome.
- **It's an archive, not only a chat box:** a review queue for low-confidence
  classifications, a document view with provenance highlighting, folder-scoped
  chat, and analytics.

**Stack:** FastAPI (Python 3.12), PostgreSQL 16 + pgvector, local BGE
embeddings, PyMuPDF + Google Vision OCR, Next.js + TypeScript.

**Please read before deploying**

- It needs external APIs. DeepSeek (or another OpenAI-compatible endpoint)
  handles extraction, Gemini handles answers, Google Vision handles scans and
  images, and GPT-4o is an optional escalation. Document text is sent to these
  providers. Embeddings and reranking run locally.
- Bundled auth is dev-grade (single-user bearer). Don't expose an instance to
  the internet without real authentication in front of it.
- The processing queue is in-process. Re-drive interrupted documents with
  `python -m scripts.reprocess`.

**Try it:** [Getting started](https://abby306.github.io/filemindr/getting-started/)
· [Architecture](https://abby306.github.io/filemindr/architecture/) ·
[Source](https://github.com/abby306/filemindr)

The test suite (285 tests at the time of writing) runs fully offline in CI.
Issues and PRs are welcome. [`CONTRIBUTING.md`](https://github.com/abby306/filemindr/blob/main/CONTRIBUTING.md)
lists the invariants. Licensed AGPL-3.0.
