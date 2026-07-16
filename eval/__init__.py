"""Retrieval evaluation harness.

Built before Phase 5 so the retrieval engine is developed against a metric from
line one. Pure scorers (`recall@k`, answer-correctness) grade a retrieval
callable against a gold query set; the runner (`python -m eval.run`) prints
per-type and overall scores. Phase 5 plugs its real `retrieve(query, account_id)`
into the runner — see `eval/README.md`.
"""
