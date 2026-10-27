# Changelog

Notable changes to Filemindr. The project has no tagged releases yet; entries are
grouped by date on `main`. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## Unreleased

### Documentation
- README rewritten around what Filemindr is (open-source RAG and document intelligence), with verified
  capabilities, external API requirements, security considerations and limitations.
- Static documentation website (`site/`): getting started, self-hosting, configuration,
  architecture, hybrid search, OCR, agentic RAG and FAQ pages, with sitemap, structured data and an
  offline validation script; GitHub Actions workflow to build, check and (manually) deploy to Pages.
- Issue and pull request templates; technical article drafts in `docs/outreach/`.

## 2026-07-31

### Added
- Archive as a navigable directory: Explorer tree pane, Quick Look and selection preview,
  context menus with multi-select and bulk actions, drag-to-refile, Icons / List / Details views.
- "Ask this folder": chat scoped to a class (and its subclasses), docked in the archive.
- Motion pass: press feedback, origin-aware menus, overlay enter/exit.

## 2026-07-18

### Added
- `read_page` agent tool, so answers can recover detail that extraction dropped.
- Conversation-anchored follow-ups: retrieval stays on the documents being discussed.
- Live activity feed and retrieval transparency in chat (files read, facts matched).
- Delete chats and files, `@`-mention documents in the composer, model-generated conversation titles,
  collapsible sidebar.
- Reprocess endpoint and retry UI for stuck or failed documents.

### Fixed
- Bounded pipeline concurrency (large drops no longer exhaust the database connection pool).
- Retry transient Gemini errors; honest scoped misses and a focus guard so an unrelated document's
  fact is never passed off as the answer.

## 2026-07-17

### Added
- Initial open-source release under AGPL-3.0: OCR routing (PyMuPDF / Google Vision), structured
  extraction, local BGE embeddings, hybrid retrieval with RRF and cross-encoder reranking, agentic
  synthesis with citations, Next.js web app, offline test suite and CI.
- Optional model warmup at startup (`WARMUP_MODELS`).
- Design v2 for the web app, including a mobile pass.
