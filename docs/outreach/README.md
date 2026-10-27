# Outreach drafts

Drafts for sharing Filemindr outside GitHub. **None of these have been
published.** Review, edit, and post them yourself.

| File | What it is | Where it fits |
|---|---|---|
| [`articles/01-open-source-rag-document-management-fastapi-pgvector.md`](articles/01-open-source-rag-document-management-fastapi-pgvector.md) | Architecture walkthrough: schema, tenancy, pipeline, embeddings, agentic answers | Personal blog / dev.to / Hashnode / Medium |
| [`articles/02-hybrid-rag-search-postgres-pgvector-rrf-reranking.md`](articles/02-hybrid-rag-search-postgres-pgvector-rrf-reranking.md) | Hybrid retrieval: intent weights, pgvector, FTS, structured facts, RRF, blended reranking | Same; also a good fit for r/PostgreSQL or a pgvector-focused newsletter |
| [`articles/03-ocr-pdf-rag-source-grounded-answers.md`](articles/03-ocr-pdf-rag-source-grounded-answers.md) | OCR routing, bbox provenance, citation validation | Same |
| [`github-announcement.md`](github-announcement.md) | Release notes / pinned Discussion | GitHub |
| [`community-post.md`](community-post.md) | Show HN / Reddit / dev-community intro | HN, r/selfhosted, r/Python, dev.to |
| [`linkedin-post.md`](linkedin-post.md) | Short technical announcement | LinkedIn |
| [`directory-listing.md`](directory-listing.md) | 100/150/300-char descriptions + form facts | awesome-lists, AlternativeTo, LibHunt, etc. |

## Publishing checklist

1. **Docs site live first.** The drafts link to
   `https://abby306.github.io/filemindr/...`. Enable GitHub Pages and confirm
   those URLs resolve before posting, or the links will 404.
2. **Canonical URL.** Each article has a `canonical_url: TODO`. Pick one home
   for each article (your blog or the docs site) and set every cross-post's
   canonical link to it. dev.to, Hashnode and Medium all support canonical URLs.
   This avoids duplicate-content dilution and points ranking signals at one page.
3. **Re-verify facts against `main`** on the day you publish: test count
   (285 on 2026-10-27), model names, thresholds, and the external-API list.
   Code links point at `blob/main/...`, so line-level details can drift.
4. **Keep the limitations sections.** They are what makes the posts credible to
   technical readers, and they head off "is it offline?" comments.
5. **Images.** Use only screenshots with fictional demo data. Add alt text.
6. **One community per day**, and stay to answer comments. Don't post the same
   text to several subreddits at once.
7. **Track results** in the measurement template that ships with the docs/SEO
   work, if present, so you can see which posts drive discovery.

## Review notes

- Keyword targets per article: (1) open source RAG system, FastAPI RAG,
  PostgreSQL pgvector RAG, RAG document management; (2) hybrid search RAG,
  reciprocal rank fusion, cross-encoder reranking, vector + full-text search,
  BGE embeddings; (3) OCR RAG pipeline, scanned PDF RAG, PDF RAG with citations,
  source-grounded document chat. Each one appears in the title, the intro and
  one or two headings. Don't add more.
- No benchmark numbers are claimed anywhere. The eval harness exists, but no
  published scores do. Don't add numbers unless you run the harness and
  describe the setup.
