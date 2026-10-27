Filemindr is an open-source (AGPL-3.0) retrieval-augmented generation (RAG) application and document intelligence platform. Source: https://github.com/abby306/filemindr

Key facts:

- Stack: Python 3.12 + FastAPI backend; PostgreSQL 16 with pgvector (HNSW) and Postgres full-text search (GIN); Next.js 16 + React + TypeScript web app.
- Ingest: PDF (text layer via PyMuPDF; scanned pages via Google Cloud Vision OCR), DOCX, PNG, JPEG. One JSON-mode LLM pass (DeepSeek by default, OpenAI-compatible) extracts a structured card: classes, entities, dates, typed facts and atomic facts with page and bounding box.
- Retrieval: hybrid. Structured + lexical (full-text search) + two-stage vector search, fused with weighted Reciprocal Rank Fusion (k=60) and reranked by a local cross-encoder (BAAI/bge-reranker-base). Embeddings are local (BAAI/bge-base-en-v1.5, 768-d).
- Answering: an agentic loop (Gemini 2.5 Flash function calling with find_documents, search, read_page and finish tools), with enforced citations to candidate facts and an explicit "not supported" outcome. Optional GPT-4o escalation.
- Deployment: self-hostable on one Linux server; not offline (extraction, answering and OCR of scans call hosted APIs). Auth is dev-grade; not intended for direct public-internet exposure without added authentication.
