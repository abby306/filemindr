# Community introduction (draft)

**Where:** r/selfhosted, r/LocalLLaMA (only if framed around the local
embedding/rerank parts and honest about the cloud LLMs), r/Python, Hacker News
"Show HN", dev.to. Read each community's self-promotion rules first. On Reddit,
post from an account with real participation, answer every comment, and don't
cross-post the same text everywhere on the same day.
**Status:** draft — not published.

---

## Title options

- Show HN: Filemindr – open-source document archive with cited RAG answers (FastAPI, pgvector)
- I built a self-hosted document archive that answers questions with page-level citations (open source)
- Hybrid RAG in one Postgres: pgvector + full-text + structured facts, fused with RRF. Open-source project write-up

## Body

I've been building Filemindr, an open-source (AGPL-3.0) document archive with
retrieval-augmented question answering, and I'd like feedback from people who
run this kind of thing.

What it does: you drop in PDFs, scans, phone photos of receipts, or .docx files.
It OCRs them (PyMuPDF text layer first, Google Vision for scans and images), runs
one structured-extraction LLM pass per document, and files everything into an
auto-built folder taxonomy. Then you can ask questions across the archive. Every
answer cites the page, and highlights the region when it can.

The part I think is interesting technically:

- **It doesn't retrieve over text chunks.** Extraction produces typed facts
  (`label/value/numeric/unit/page`), dates with roles, entities, and
  self-contained "atomic facts" with page + bounding box. Retrieval runs over
  those.
- **Hybrid search is all Postgres.** It runs two-stage pgvector HNSW (doc
  summaries → facts), `websearch_to_tsquery` full-text plus `ILIKE` on
  identifiers, and a structured retriever. A regex intent router only *weights*
  the sources; every retriever always runs. Results are fused with weighted RRF
  (k=60), then a local `bge-reranker-base` reranks the top 30. Its score is
  blended 40/60 with the fused score, because a small CPU reranker is too
  brittle to trust outright.
- **The answer loop is agentic** (Gemini 2.5 Flash function calling: find
  documents / search / read a page / finish). The model cites short ids, and
  ids it wasn't given are dropped. "Not in your documents" is a valid answer.

What it is *not*, so nobody wastes their time:

- Not offline or local-only. Embeddings and reranking are local, but
  extraction (DeepSeek/OpenAI-compatible), answers (Gemini) and OCR of scans
  (Google Vision) are API calls, so document text leaves the box.
- Auth is dev-grade. Put it behind real auth or keep it on localhost/VPN.
- No Docker image for the app yet. Compose only runs Postgres. Setup is native
  (Ubuntu, Python 3.12, Node 20+).

Repo: https://github.com/abby306/filemindr
Docs: https://abby306.github.io/filemindr/

I'd especially like feedback on:

1. Whether swapping the extraction/answer models for local ones (Ollama/vLLM via
   OpenAI-compatible endpoints) would be the most useful next step for you.
2. Whether the hybrid retrieval write-up is clear enough to reuse:
   https://abby306.github.io/filemindr/features/hybrid-search/

<!-- Reviewer note: drop question 1 or reword it if local-model support is
     not something you intend to work on soon. -->
