# LinkedIn technical announcement (draft)

**Where:** personal LinkedIn post. Optionally attach 2–3 screenshots (the
citation-highlight view, the Ask screen with its live trace, the auto-filed
archive), all of which use fictional demo data. Put the link in the post body;
LinkedIn shows a preview card from the docs site's Open Graph tags.
**Status:** draft — not published.

---

I've open-sourced Filemindr, a RAG and document intelligence platform for people
who need answers from their documents that they can verify.

Upload PDFs, scans, receipts or Word files. Filemindr reads them (OCR where
needed), extracts the key facts, files them into folders automatically, and
answers questions across everything. Each answer links to the exact page, and
highlights the clause when it can.

A few engineering decisions that made the biggest difference:

→ Extract once, retrieve over structure. Instead of searching raw text chunks,
each document is distilled at upload time into typed facts, dates, entities
and short self-contained statements, each tied to its page.

→ Hybrid search in a single PostgreSQL. Vector search (pgvector), full-text
search and structured lookups run side by side. Reciprocal Rank Fusion merges
them, and a local cross-encoder then refines the order.

→ Citations the model can't invent. The model can only cite facts it was
actually shown, and "this isn't in your documents" counts as a valid answer.

Built with FastAPI, PostgreSQL + pgvector, local BGE embeddings and Next.js.
It's AGPL-3.0 and self-hostable. It does rely on external LLM and OCR APIs, and
the bundled auth is for local and dev use. Both are documented up front.

Source: https://github.com/abby306/filemindr
Docs: https://abby306.github.io/filemindr/

#RAG #OpenSource #PostgreSQL #FastAPI #DocumentAI
