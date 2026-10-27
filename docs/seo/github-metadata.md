# GitHub repository metadata

Current values, read from the GitHub API on 2026-10-27, and proposed replacements. **Not yet applied.**

## Current

- **Description:** "Open-source intelligent document archivist — OCR, structured extraction, hybrid
  retrieval, and cited chat answers over your documents. AGPL-3.0."
- **Website:** *(none)*
- **Topics (8):** ai, document-management, fastapi, nextjs, ocr, pgvector, rag, self-hosted

## Proposed

**Description** (220 chars; GitHub's limit is 350):

> Open-source, self-hostable RAG for your documents: OCR, LLM structured extraction, hybrid search (pgvector + Postgres full-text, RRF, cross-encoder reranking) and agentic Q&A with page-level citations. FastAPI + Next.js.

**Website:** `https://abby306.github.io/filemindr/`. Set this only after the docs site is deployed.

**Topics (20, the maximum):**

| Topic | Why |
|---|---|
| `rag` | Primary category; used by every comparable project |
| `retrieval-augmented-generation` | Long form of the category; separate topic page |
| `agentic-rag` | Tool-using answer loop |
| `hybrid-search` | Core retrieval differentiator |
| `semantic-search` | Vector side of retrieval |
| `vector-search` | Used by comparable projects (Onyx) |
| `pgvector` | Exact stack term people browse |
| `postgresql` | Stack |
| `fastapi` | Stack |
| `nextjs` | Stack |
| `ocr` | Scanned PDFs and photos |
| `pdf` | Most common input format |
| `document-ai` | Category |
| `document-management` | Archive side |
| `document-management-system` | Topic used by paperless-ngx; reaches DMS browsers |
| `intelligent-document-processing` | Extraction / IDP audience |
| `question-answering` | Used by R2R; document Q&A intent |
| `reranking` | Cross-encoder stage |
| `self-hosted` | Deployment model |
| `llm` | Broad, high-traffic topic |

Dropped: `ai`, which is too generic to help ranking. Considered and rejected: `open-source` (adds
nothing on GitHub), `chatbot` and `pdf-chat` (undersell the archive), `embeddings`
(lower priority than the 20 above).

## Applying it (requires your approval)

```bash
gh repo edit abby306/filemindr \
  --description "Open-source, self-hostable RAG for your documents: OCR, LLM structured extraction, hybrid search (pgvector + Postgres full-text, RRF, cross-encoder reranking) and agentic Q&A with page-level citations. FastAPI + Next.js."

gh repo edit abby306/filemindr --remove-topic ai \
  --add-topic retrieval-augmented-generation,agentic-rag,hybrid-search,semantic-search,vector-search,postgresql,pdf,document-ai,document-management-system,intelligent-document-processing,question-answering,reranking,llm

# After the docs site is live:
gh repo edit abby306/filemindr --homepage https://abby306.github.io/filemindr/
```

## Social preview image

GitHub doesn't expose the repository social preview through the API. Upload
`docs/assets/social-preview.png` (1280×640) under **Settings → General → Social preview**.
