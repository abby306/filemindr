# Discoverability strategy and keyword map

Working notes for maintainers on how Filemindr is positioned in public text, and which page is
responsible for which search intent. No keyword-volume or ranking data was available when
this was written (2026-10-27), so the map is based on search-intent reasoning, not on
numbers.

## Positioning

- **Name and category:** Filemindr — Open-Source RAG & Document Intelligence Platform
- **One-liner:** Self-hostable document management with OCR, LLM structured extraction, hybrid
  retrieval (pgvector + Postgres full-text, RRF, cross-encoder reranking) and agentic answers
  with page-level citations.
- **Differentiator to repeat consistently:** it retrieves over *structured facts extracted at
  ingest* (typed facts, dates, entities, atomic facts with page + bbox) rather than raw chunks,
  and it is an archive (auto-filing, review queue) as well as a chatbot.
- **Honesty constraints:** self-hostable but not offline; dev-grade auth; no published benchmarks.
  Never use "production-ready", "enterprise-grade", "fully private" or "offline".

## What comparable projects do (observed 2026-10-27 via the GitHub API)

| Repository | Description pattern | Homepage | Topics include |
|---|---|---|---|
| infiniflow/ragflow | "open-source Retrieval-Augmented Generation (RAG) engine" up front | ragflow.io | rag, retrieval-augmented-generation, agentic-retrieval |
| Cinnamon/kotaemon | "An open-source RAG-based tool for chatting with your documents." | GitHub Pages docs | rag, open-source, chatbot |
| onyx-dot-app/onyx | "Open Source AI Platform …" | onyx.app | rag, self-hosted, vector-search, nextjs, python |
| SciPhi-AI/R2R | "Agentic Retrieval-Augmented Generation (RAG) with a RESTful API" | — | rag, retrieval-augmented-generation, question-answering |
| paperless-ngx/paperless-ngx | "document management system: scan, index and archive" | docs site | document-management-system, ocr, pdf, dms |

Takeaways applied here: put the category ("open-source RAG") in the first words of the
description; spell out `retrieval-augmented-generation` as a topic; have a crawlable docs
homepage; and claim the space between the DMS projects (paperless-style archiving and OCR) and
the RAG chat projects. Filemindr is small next to these projects, so it should compete on
specific long-tail technical queries (pgvector + FTS hybrid, RRF, citations, FastAPI) rather
than on the generic "RAG" head term.

## Keyword map (one primary owner per group)

| Keyword group | Primary page | Supporting |
|---|---|---|
| open source RAG, open source RAG application/system, open source document AI, AI document management system, open source knowledge base AI | README H1 + intro; docs home | GitHub description + topics; llms.txt |
| self-hosted RAG, self-hosted document AI | docs `/self-hosting/` | README "Configuration and external API requirements"; FAQ |
| hybrid search RAG, vector + full-text search, reciprocal rank fusion, cross-encoder reranking, BGE embeddings | docs `/features/hybrid-search/` | Article 2; README "How it works" |
| PostgreSQL pgvector RAG, FastAPI RAG, document retrieval pipeline | docs `/architecture/` | Article 1; README stack table |
| OCR RAG pipeline, scanned PDF RAG, intelligent document processing, AI document extraction | docs `/features/ocr-document-processing/` | Article 3 |
| agentic RAG, RAG with citations, source-grounded document chat, document question answering | docs `/features/agentic-rag-citations/` | Article 3; README "Why Filemindr" |
| PDF RAG chatbot, chat with documents open source, open source PDF AI | README "Why Filemindr" (the comparison with PDF chat apps) | docs home comparison table; community post |
| Filemindr (brand) | all | consistent name, repo link and license everywhere |

Rules: each page targets its own group in its `<title>`, H1 and first paragraph. Other pages
link to it instead of repeating the same phrasing. Don't add keyword lists, hidden text, or
pages that exist only to rank.

## AI-assistant discoverability

Assistants with search (Gemini, ChatGPT search, Perplexity, Claude) cite pages they can fetch
and parse. What helps, in order of importance:

1. Plain, crawlable statements of what Filemindr is, what it uses, and its limits: the README
   intro, the docs home and the FAQ answer these in single sentences that can be quoted.
2. Consistency: the same name, category, stack and license in the README, docs, GitHub
   description and outreach.
3. Third-party mentions (articles, awesome-lists, forum answers) that link to the repository.
4. Structured data (`SoftwareSourceCode`, `TechArticle`) and `llms.txt`: supplementary. Neither
   guarantees inclusion in any assistant's answers.
