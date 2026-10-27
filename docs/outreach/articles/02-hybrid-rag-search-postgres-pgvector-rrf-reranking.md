---
title: "Implementing Hybrid RAG Search with PostgreSQL, pgvector, RRF, and Reranking"
description: "A working hybrid retrieval pipeline in one Postgres: pgvector HNSW, full-text search, structured facts, weighted Reciprocal Rank Fusion and a blended cross-encoder."
tags: [rag, hybrid-search, pgvector, postgresql, reranking, information-retrieval, python]
canonical_url: "TODO — set to the docs-site copy (e.g. https://abby306.github.io/filemindr/...) or the first place this is published"
status: draft — not published
---

# Implementing Hybrid RAG Search with PostgreSQL, pgvector, RRF, and Reranking

Pure vector search is a good default for retrieval-augmented generation, and a
bad one for documents full of identifiers and numbers. Ask an embedding model
for "invoice KP-58213" and it will find invoices. It will not reliably find
*that* invoice. Ask "how much did we spend on printing?" and semantic
similarity will surface prose about printing, not the `total_due` field you
need to answer the question.

Hybrid search fixes this by running several retrievers and combining their
results. This article walks through the real hybrid retrieval pipeline in
[Filemindr](https://github.com/abby306/filemindr), an open-source RAG and
document intelligence app, built entirely on PostgreSQL: pgvector for
semantic search, built-in full-text search for lexical matches, plain SQL
over extracted typed facts for structured lookups, **Reciprocal Rank Fusion**
to merge them, and a **cross-encoder reranker** for precision. The code is
[`app/services/retrieval.py`](https://github.com/abby306/filemindr/blob/main/app/services/retrieval.py)
and
[`app/services/reranking.py`](https://github.com/abby306/filemindr/blob/main/app/services/reranking.py).

## What is being searched

Filemindr doesn't retrieve over raw text chunks. At ingest, an LLM extraction
pass turns each document into rows:

- `document_facts` — self-contained sentences ("The lease term ends on
  February 28, 2029") with `page`, optional `bbox`, a 768-d `embedding`, and a
  generated `tsvector` column,
- `typed_facts` — `label`/`value`/`value_numeric`/`unit`/`page`,
- `document_dates`, `entities`,
- `documents.summary_embedding` — one vector per document.

Both vector columns have HNSW indexes with `vector_cosine_ops`; the `tsvector`
has a GIN index. All of it lives in the same database, which turns out to be
the main simplification: no syncing between a vector store and a search
engine, and each retriever is a SQL query.

## Step 0: route the query (cheaply)

Before retrieving anything, the query is classified into one of four intents
with plain regular expressions:

```python
def classify_intent(query: str) -> Intent:
    """Route a query to an intent. Pure; the first matching rule wins."""
    q = query.strip()
    if _AGGREGATE.search(q):
        return "aggregate"
    if _QUOTED.search(q) or _LONG_ID.search(q) or _ENTITYISH.search(q) or _LEXICAL.search(q):
        return "lexical"
    if _METADATA.search(q):
        return "metadata"
    return "semantic"
```

`aggregate` triggers on phrases like "how much", "total", "vat"; `lexical` on
quoted spans, long numeric ids, ALL-CAPS names and "... number"; `metadata` on
"who", "when", "expires", "due date"; anything else is `semantic`.

The important design choice is what the intent *does*. It does not pick a
retriever. Every retriever always runs; the intent only sets the **weights**
used during fusion:

```python
_WEIGHTS: dict[Intent, dict[str, float]] = {
    "aggregate": {"structured": 1.0, "vector": 0.5, "lexical": 0.4},
    "metadata":  {"structured": 0.8, "vector": 0.6, "lexical": 0.5},
    "lexical":   {"lexical": 1.0, "vector": 0.5, "structured": 0.4},
    "semantic":  {"vector": 1.0, "lexical": 0.6, "structured": 0.3},
}
```

A misclassified query therefore degrades gracefully: the right hit is still in
the candidate set, just tilted down a little. That's what makes a crude
rule-based router acceptable. A learned classifier could replace it behind the
same signature, but the regexes are free, deterministic and unit-tested.

## Retriever 1: two-stage vector search with pgvector

Searching every fact in the account by embedding is wasteful and noisy: a
fact-heavy document can flood the results. Filemindr does it in two stages.
First, shortlist the 12 most relevant documents by summary embedding. Then rank
facts only within those:

```python
doc_stmt = (
    select(Document.id)
    .where(Document.account_id == account_id, Document.summary_embedding.is_not(None))
    .order_by(Document.summary_embedding.cosine_distance(qvec))
    .limit(_DOC_SHORTLIST)          # 12
)
...
select(DocumentFact.id, DocumentFact.document_id, DocumentFact.text,
       DocumentFact.page, DocumentFact.bbox)
.where(
    DocumentFact.account_id == account_id,
    DocumentFact.document_id.in_(doc_ids),
    DocumentFact.embedding.is_not(None),
)
.order_by(DocumentFact.embedding.cosine_distance(qvec))
.limit(limit)                        # 20
```

`cosine_distance` is the `pgvector` SQLAlchemy comparator; it compiles to the
`<=>` operator that the HNSW index serves.

The query vector comes from **BGE embeddings** (`BAAI/bge-base-en-v1.5`, run
locally on CPU). Two details matter for BGE: the retrieval instruction
(`"Represent this sentence for searching relevant passages: "`) is prepended to
the query only, never to indexed passages, and all vectors are normalized so
cosine distance is meaningful.

## Retriever 2: lexical — full-text search plus identifier matching

The lexical retriever has two parts. The first is ordinary Postgres full-text
search over facts, using `websearch_to_tsquery` (which accepts user-style input
with quotes and `-` exclusions) and `ts_rank` for ordering:

```python
tsquery = func.websearch_to_tsquery("english", query)
fts = literal_column("fts")
select(..., func.ts_rank(fts, tsquery).label("rank"))
.where(DocumentFact.account_id == account_id, fts.op("@@")(tsquery))
.order_by(literal_column("rank").desc())
```

FTS alone misses something specific to documents: exact identifiers (invoice
numbers, serials, policy numbers) and party names often appear only in
`typed_facts` or `entities`, never in a prose fact. So the retriever also
pulls "terms worth an exact match" out of the query — quoted spans, 4+ digit
numbers, capitalized words and acronyms — and matches them with `ILIKE` against
typed-fact values and entity names.

This is the piece that makes "invoice KP-58213" work.

## Retriever 3: structured facts, coupled to relevant documents

The structured retriever answers questions like "what's the VAT on the Acme
invoice?" from `typed_facts`, `document_dates` and `entities`. The trap is
aggregation across the wrong documents: if you pull every `total` in the
account, the model will happily sum them.

So structured retrieval mines **only the top 4 documents** from the vector and
lexical shortlists, in their relevance order. Within each document, facts are
ordered by how well their label answers the query:

```python
def _label_priority(label: str) -> int:
    words = set(re.split(r"[^a-z0-9]+", label.lower()))
    if words & qwords:
        return 0  # the query names this label
    if intent == "aggregate" and _AMOUNT_LABEL.search(label):
        return 1  # amount-like, for "how much" with no named label
    return 2
```

On `aggregate` queries only numeric typed facts are considered; on `metadata`
queries dates and entities are added. A typed fact whose label the query names
directly ("gross margin" → `gross_margin`) is flagged `exact=True`.

## Fusing the lists: weighted Reciprocal Rank Fusion

We now have up to four ranked lists — vector, lexical, structured, and the
`exact` subset of structured — whose scores are not comparable. Cosine
distance, `ts_rank` and "position in a SQL ordering" live on different scales.
**Reciprocal Rank Fusion** sidesteps that by ignoring scores entirely and using
only rank:

```python
def rrf_merge(ranked_lists, *, weights, rrf_k=60):
    scores: dict[str, float] = {}
    chosen: dict[str, FactHit] = {}
    for source, hits in ranked_lists.items():
        weight = weights.get(source, 0.0)
        if weight == 0.0:
            continue
        for rank, hit in enumerate(hits):
            scores[hit.key] = scores.get(hit.key, 0.0) + weight / (rrf_k + rank)
            current = chosen.get(hit.key)
            if current is None or (current.fact_id is None and hit.fact_id is not None):
                chosen[hit.key] = hit
    ...
```

Each source contributes `weight / (k + rank)` to a hit; a hit found by several
sources sums its contributions. `k = 60` is the standard damping constant from
the original RRF paper — it keeps the top rank from dominating.

Three implementation details are worth noting:

- **Dedup prefers citable copies.** If the same fact appears from several
  sources, the copy with a `fact_id` (an atomic fact with page + bbox) is kept.
- **The `exact` list fuses with weight 1.2**, above every intent weight, so a
  field the user named surfaces even when verbose prose outranks it in vector
  space.
- **The function is pure**, which makes it trivial to unit-test with
  hand-built lists.

## The precision stage: cross-encoder reranking

RRF is a good candidate generator and a blunt final ranker. It scores a fact by
where it placed in each list, not by whether it answers the question. The
reranking module's docstring gives the real failure cases: a short generic fact
("the product is a journaling companion") or a thesis's front matter
("dedicated to my parents") outranking the fact the user wanted.

A **cross-encoder** reads the query and candidate together and scores relevance
directly. That's much more accurate than comparing two independently computed
embeddings, and much slower, so it only runs on the top 30 fused candidates.
Filemindr uses `BAAI/bge-reranker-base` through `sentence_transformers.CrossEncoder`,
locally on CPU.

The interesting choice is that the cross-encoder **doesn't get the final
say**:

```python
_RERANK_ALPHA = 0.4

def rerank(query, hits, *, top_k):
    ce = _minmax(_score([(query, hit.text) for hit in hits]))
    fused = _minmax([hit.score for hit in hits])  # RRF score carried in on arrival
    for hit, c, f in zip(hits, ce, fused):
        hit.score = _RERANK_ALPHA * c + (1 - _RERANK_ALPHA) * f
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]
```

Both scores are min-max normalized over the candidate set and blended 40/60.
The code comment explains why: a small CPU reranker is brittle. It under-scores
answers buried in a subordinate clause and can't read terse structured text
like `person: Jordan Ellis`. If a fact is strongly agreed on by several
retrievers, one weak relevance score shouldn't bury it. The reranker *refines*
the ranking rather than replacing it.

### When does reranking help?

From the design and the failure cases it was built for:

- It helps most when the candidate set contains **topically related but
  non-answering** facts — the common case for semantic queries over long
  documents, where vector similarity rewards being "about" the subject.
- It helps less for **structured and identifier lookups**, where the exact and
  lexical sources already put the answer on top, and where terse
  `label: value` strings are hard for a cross-encoder to read. The blend
  protects those cases.
- It costs CPU time proportional to the number of candidates, which is why it
  runs on 30, not on everything.

If you have a larger GPU reranker, a higher alpha would probably be justified.
Measure before changing it — which brings us to evaluation.

## Measuring instead of guessing

Retrieval tuning without a metric is guesswork. Filemindr ships a small
harness in [`eval/`](https://github.com/abby306/filemindr/tree/main/eval):

- `doc_recall@k` — did the expected document appear in the top-k?
- `fact_recall@k` — did expected fact substrings appear among the top-k facts?
- `answer_correctness` — does the synthesized answer contain required phrases?

Gold queries are typed (`metadata | semantic | lexical | aggregate`), so you can
see which intent a change helped or hurt.
`python -m scripts.eval_retrieval` scores the live engine against a seeded
synthetic corpus, and `retrieve(..., rerank=False)` gives you the raw fused
order for ablations. The project doesn't publish benchmark numbers; the harness
exists to catch regressions on your own data and gold set.

## The whole pipeline in one function

Put together, `retrieve()` is short:

```python
intent = classify_intent(query)
weights = _WEIGHTS[intent]
qvec = embed_query(query)
vector_hits  = _vector_search(db, account_id, qvec, limit=20, scope=scope)
lexical_hits = _lexical_search(db, account_id, query, limit=20, scope=scope)
ranked_docs  = _rank_doc_ids(vector_hits + lexical_hits)
structured_hits = _structured_search(db, account_id, intent, ranked_docs, query, limit=20)
exact_hits = [h for h in structured_hits if h.exact]
merged = rrf_merge(
    {"vector": vector_hits, "lexical": lexical_hits,
     "structured": structured_hits, "exact": exact_hits},
    weights={**weights, "exact": 1.2},
)
top = reranking.rerank(query, merged[:30], top_k=k)
```

Optional `document_ids` / `class_slug` arguments narrow every retriever to a
document or a folder, which is how the agent's scoped `search` tool and the
UI's "Ask this folder" work. The result also carries a `plan` dict (intent,
weights, per-source counts) that the UI shows as a retrieval trace.

## Limitations and trade-offs

- **English-only lexical config** (`to_tsvector('english', ...)`) and an English
  embedding model.
- **Rule-based intent routing** is a known simplification; it's tolerable
  because routing only weights sources.
- **Tuning constants are hand-set** (shortlist 12, structured docs 4, per-source
  20, rerank pool 30, alpha 0.4) for small-to-medium personal and team archives;
  very large corpora would need re-tuning.
- **`ILIKE '%term%'` identifier matching** doesn't use an index; fine at archive
  scale, not at millions of rows.

## Takeaways

1. Keep vector, full-text and relational data in one Postgres so hybrid
   retrieval is a few SQL queries.
2. Let intent weight retrievers, not select them.
3. Use RRF to fuse incomparable scores; prefer the citable copy when deduping.
4. Rerank a bounded candidate pool, and if your reranker is small, blend
   instead of overriding.
5. Build the eval harness before tuning.

---

**About Filemindr.** Filemindr is an open-source (AGPL-3.0), self-hostable RAG and
document intelligence platform with OCR, structured extraction, hybrid search
and cited answers. Source: <https://github.com/abby306/filemindr> · Hybrid search
docs: <https://abby306.github.io/filemindr/features/hybrid-search/>
