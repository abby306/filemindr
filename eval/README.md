# Retrieval eval harness

A small, dependency-light harness to measure retrieval quality. It exists **before**
Phase 5 so the retrieval engine is built against a metric from the first commit.

## What it measures

For each gold query the scorers compute (all in `eval/scorers.py`, pure functions):

- **`doc_recall@k`** — did the expected document(s) appear in the top-k retrieved docs?
- **`fact_recall@k`** — did the expected fact substrings appear among the top-k retrieved facts?
- **`answer_correctness`** — does the synthesized answer contain the required phrases?

Matching is substring-based on normalized text (casefold + collapsed whitespace). A
metric returns `None` when a query declares no expectation of that kind, so it is
excluded from the average rather than scored 0/1. The `normalize` function and the
None-aware aggregation are the seam for swapping in an **LLM judge** later without
touching the runner.

## Run it

```bash
python -m eval.run          # built-in stub fixtures
python -m eval.run --k 3    # tighter top-k cutoff
python -m eval.run --gold path/to/other.yaml
```

This prints per-type (`metadata | semantic | lexical | aggregate`) and overall scores.
Out of the box it runs against `_stub_retrieve` (fixtures in `eval/run.py`) so the runner
and scorers are exercised end to end.

## Add a gold query

Append to `eval/gold/seed.yaml`:

```yaml
- id: unique_snake_case_id
  query: "the user's natural-language question"
  type: metadata | semantic | lexical | aggregate
  expected_doc_ids: ["doc-slug"]            # docs that should be retrieved
  expected_fact_substrings: ["exact text"]   # substrings expected among facts
  answer_contains: ["phrase"]                # phrases the answer must contain
```

`expected_doc_ids` are **slugs** (placeholders). When a seeded eval corpus exists, map
each slug to its real document UUID.

## Wire in Phase 5 retrieval

The runner needs a callable `retrieve(query: str) -> RetrievedAnswer`. The real engine
will expose `retrieve(query, account_id)`; adapt it by binding the eval account id:

```python
from functools import partial
from app.services.retrieval import retrieve          # Phase 5
from eval.run import run_eval
from eval.schema import load_gold

gold = load_gold("eval/gold/seed.yaml")
scores = run_eval(partial(retrieve, account_id=EVAL_ACCOUNT_ID), gold, k=5)
```

`RetrievedAnswer(doc_ids=[...], facts=[...], answer="...")` is the only contract the
scorers depend on, so the retrieval internals can change freely.
