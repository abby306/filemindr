# Project-directory listing copy (draft)

For awesome-lists (e.g. awesome-selfhosted, awesome-rag-style lists),
AlternativeTo, LibHunt, OpenAlternative and similar. Check each list's
inclusion rules first: several require a minimum project age, a tagged release,
a working demo, or a Docker install. Don't submit where Filemindr doesn't
qualify yet.

**Status:** draft — not submitted anywhere.

---

## Name

Filemindr

## One-liner (~100 chars)

Open-source, self-hostable RAG document archive: OCR, hybrid search and cited answers.

## Short description (~150 chars)

Self-hostable document archive with OCR, LLM fact extraction, hybrid pgvector +
full-text search and AI answers cited to the page. FastAPI + Next.js.

## Medium description (~300 chars)

Filemindr is an open-source RAG and document intelligence platform. It OCRs PDFs,
scans, photos and DOCX files, extracts typed facts, dates and entities, and files
documents into an auto-built folder taxonomy. It answers questions with hybrid
retrieval (pgvector, Postgres FTS, RRF, cross-encoder rerank) and page-level
citations.

## awesome-list line (Markdown)

```markdown
- [Filemindr](https://github.com/abby306/filemindr) - Document archive with OCR, LLM extraction, hybrid search and page-cited answers. ([Docs](https://abby306.github.io/filemindr/)) `AGPL-3.0` `Python/Nodejs`
```

## Facts for directory forms

| Field | Value |
|---|---|
| License | AGPL-3.0 |
| Language / stack | Python 3.12 (FastAPI), TypeScript (Next.js), PostgreSQL 16 + pgvector |
| Platforms | Self-hosted (Linux; native install documented for Ubuntu 22+) |
| Category | Document management / RAG / AI search |
| Tags | rag, document-management, ocr, hybrid-search, pgvector, self-hosted, fastapi, nextjs |
| Alternative to (honest framing) | "PDF chat" tools and DMS + AI add-ons. Do not claim feature parity with any specific product. |
| External services | DeepSeek (or OpenAI-compatible) for extraction; Gemini for answers; Google Vision for scanned PDFs and images; OpenAI optional |
| Offline? | No: embeddings and reranking are local, the LLMs and OCR are APIs |
| Pricing | Free (open source). Self-hosters pay their own API usage |
| Repo | https://github.com/abby306/filemindr |
| Docs | https://abby306.github.io/filemindr/ (once GitHub Pages is enabled) |

## Notes

- awesome-selfhosted typically expects a Docker or packaged install and some
  project maturity. Wait until there is a containerized app install and a
  tagged release.
- Use the same one-liner everywhere. Consistent wording across listings helps
  search engines and AI assistants associate the name with the category.
