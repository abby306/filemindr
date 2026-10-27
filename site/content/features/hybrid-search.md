---
title: "Hybrid Search RAG with pgvector, Full-Text Search and RRF"
nav_title: Hybrid search & reranking
description: "How Filemindr's hybrid RAG retrieval works: pgvector vector search, Postgres full-text search and structured facts, fused with RRF and a cross-encoder."
---

# Hybrid search: pgvector + full-text search + RRF + reranking

Filemindr answers questions about your documents with **hybrid retrieval** that runs entirely inside PostgreSQL, plus a local cross-encoder reranker. This page walks through the algorithm in [`app/services/retrieval.py`](https://github.com/abby306/filemindr/blob/main/app/services/retrieval.py) and [`app/services/reranking.py`](https://github.com/abby306/filemindr/blob/main/app/services/reranking.py), and explains why each piece is there.

## Why vector search alone isn't enough

Pure embedding similarity has well-known failure modes on business documents:

- **Identifiers.** "Invoice INV-20931" or an account number has little semantic content, so an embedding won't reliably find it. Lexical matching will.
- **Aggregates.** "How much did we spend on printing?" needs numeric fields from the *right* documents, not the passages that sound most like the question.
- **Short generic facts.** Something like "this document is a contract" scores well against many queries and crowds out the actual answer.

Filemindr therefore runs three kinds of retrievers on **every** query and fuses their results.

## What gets indexed

Retrieval runs over the structured output of [extraction](ocr-document-processing.md), not raw OCR text:

| Table | Contents | Index |
|---|---|---|
| `documents.summary_embedding` | Embedding of the document summary | pgvector HNSW, `vector_cosine_ops` |
| `document_facts` | Self-contained atomic facts with page + bbox | HNSW on `embedding`; GIN on a generated `tsvector` (`fts`) |
| `typed_facts` | Label / value / numeric value / unit / page | B-tree on `(account_id, label)` and `value_numeric` |
| `document_dates`, `entities` | Dated events with roles; people and organizations | B-tree on `(account_id, value)`; entities joined via `document_entities` |

Embeddings come from `BAAI/bge-base-en-v1.5` (768 dimensions, normalized), which runs locally on CPU. Queries get bge's retrieval instruction prefix and passages don't. That asymmetry is what the model was trained for.

## Step 1: intent routing (weights, not filters)

A small rule-based classifier assigns one of four intents: `aggregate` ("how much", "total"), `lexical` (quoted spans, long ids, ALL-CAPS names), `metadata` ("who", "when", "expires") or `semantic` (the default). The intent changes how much each retriever counts, but **no retriever is skipped**:

```python
_WEIGHTS = {
    "aggregate": {"structured": 1.0, "vector": 0.5, "lexical": 0.4},
    "metadata":  {"structured": 0.8, "vector": 0.6, "lexical": 0.5},
    "lexical":   {"lexical": 1.0, "vector": 0.5, "structured": 0.4},
    "semantic":  {"vector": 1.0, "lexical": 0.6, "structured": 0.3},
}
```

A misclassified query still reaches every source and only gets slightly worse ordering. Rules are fast, free and deterministic, and they are unit-tested. An LLM classifier could replace them behind the same function signature.

## Step 2: the three retrievers

**Vector (two-stage).** The query embedding first shortlists the 12 nearest documents by `summary_embedding`, then ranks atomic facts *within those documents* by `document_facts.embedding`. Shortlisting by document keeps a fact-heavy file from dominating and makes ranking within each document more precise.

**Lexical.** Postgres full-text search with `websearch_to_tsquery('english', query)` ranked by `ts_rank` over the GIN-indexed `tsvector`. It also runs case-insensitive matching of id-like and capitalized terms against `typed_facts.value` and entity names. Invoice numbers and party names often appear only there.

**Structured.** For the top 4 documents from the vector and lexical results, it pulls typed facts (numeric-only on aggregate queries), dates and entities. Facts whose *label* the query names (`vat`, `invoice number`) rank first. Tying structured results to the most relevant documents keeps "how much" from summing numbers across unrelated files.

## Step 3: weighted Reciprocal Rank Fusion

Scores from different retrievers (cosine distance, `ts_rank`, rule priority) aren't comparable. **Reciprocal Rank Fusion** sidesteps that by using only ranks:

```python
def rrf_merge(ranked_lists, *, weights, rrf_k=60):
    scores, chosen = {}, {}
    for source, hits in ranked_lists.items():
        weight = weights.get(source, 0.0)
        for rank, hit in enumerate(hits):
            scores[hit.key] = scores.get(hit.key, 0.0) + weight / (rrf_k + rank)
            ...
```

A fact found by two retrievers sums both contributions, so agreement is rewarded. When duplicates collide, the copy that carries a citation target (an atomic fact id) wins. Structured facts whose label the query names also go in as a fourth "exact" list with weight 1.2, so a directly named field surfaces regardless of intent.

## Step 4: cross-encoder reranking (blended)

RRF is a good candidate generator but a blunt ranker: it knows *where* a fact placed, not *whether it answers the question*. The top 30 fused candidates go to `BAAI/bge-reranker-base`, a cross-encoder that reads the query and fact together.

Filemindr doesn't replace the fused order with the reranker's. It **blends** them:

```text
final = 0.4 × minmax(cross_encoder) + 0.6 × minmax(rrf)
```

A small CPU reranker is brittle on terse structured text like `person: Jane Doe`. Blending lets it reorder near-ties and demote generic filler without burying a fact that all the retrievers agreed on. Use `retrieve(..., rerank=False)` for an ablation.

## When reranking helps (and when it doesn't)

- **Helps:** long-winded semantic questions where several plausible facts compete, and corpora with boilerplate (front matter, signature blocks) that embeds well but answers nothing.
- **Doesn't help much:** exact-identifier lookups, where lexical matching already ranks the answer first, and aggregates driven by typed facts.
- **Cost:** about 30 cross-encoder pairs per query on CPU, and the model stays loaded after the first use (`WARMUP_MODELS=true` preloads it).

## Output: every hit is a citation

Each `FactHit` carries `document_id`, `page` and (for atomic facts) `bbox` and `fact_id`, so the retrieval result is already the citation list. The retrieval plan, with intent, weights and per-source counts, is returned for the live trace in the UI and stored in `retrieval_traces`.

## Measuring it

[`eval/`](https://github.com/abby306/filemindr/tree/main/eval) contains a small harness that computes `doc_recall@k`, `fact_recall@k` and `answer_correctness` against a YAML gold set (`python -m scripts.eval_retrieval`). No benchmark figures are published yet; the harness exists so changes to weights or the reranker blend can be measured rather than guessed.

Related: [Architecture](../architecture.md) · [Agentic RAG and citations](agentic-rag-citations.md)
