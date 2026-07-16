"""Eval scorers + runner: recall@k, answer-correctness, None-aware aggregation."""

from __future__ import annotations

import pytest

from eval import run
from eval.schema import GoldQuery, RetrievedAnswer, load_gold
from eval.scorers import answer_correctness, recall_at_k, score_dataset


# --- recall@k --------------------------------------------------------------
def test_recall_at_k_counts_hits_within_k() -> None:
    expected = ["doc-a", "doc-b"]
    retrieved = ["doc-a", "doc-x", "doc-b", "doc-y"]
    assert recall_at_k(expected, retrieved, k=2) == 0.5  # only doc-a in top-2
    assert recall_at_k(expected, retrieved, k=3) == 1.0  # doc-b now in top-3


def test_recall_at_k_substring_and_normalization() -> None:
    # A gold fact substring matches inside a longer, differently-cased fact.
    facts = ["The Total Amount is PHP 189.00 including change."]
    assert recall_at_k(["total amount is php 189.00"], facts, k=5) == 1.0


def test_recall_at_k_none_when_nothing_expected() -> None:
    assert recall_at_k([], ["whatever"], k=5) is None


# --- answer correctness ----------------------------------------------------
def test_answer_correctness_fraction_present() -> None:
    answer = "The parties are Meridian Energy Management and Alex Doe."
    assert answer_correctness(answer, ["Meridian Energy Management", "Alex Doe"]) == 1.0
    assert answer_correctness(answer, ["Meridian", "Globex"]) == 0.5
    assert answer_correctness(answer, []) is None


# --- aggregation -----------------------------------------------------------
def test_score_dataset_aggregates_and_ignores_none() -> None:
    gold = [
        GoldQuery(id="a", query="q1", type="aggregate", expected_doc_ids=["d1"], answer_contains=["x"]),
        GoldQuery(id="b", query="q2", type="semantic", expected_fact_substrings=["foo"]),
    ]
    results = {
        "a": RetrievedAnswer(doc_ids=["d1"], answer="contains x here"),
        "b": RetrievedAnswer(facts=["foo bar baz"]),
    }
    scores = score_dataset(gold, results, k=5)

    assert scores["n"] == 2 and scores["k"] == 5
    assert scores["overall"]["doc_recall"] == 1.0
    assert scores["overall"]["fact_recall"] == 1.0
    assert scores["overall"]["answer_correctness"] == 1.0
    # query "b" expected no docs -> excluded from the semantic doc_recall mean.
    assert scores["by_type"]["semantic"]["doc_recall"] is None


def test_missing_result_counts_as_miss() -> None:
    gold = [GoldQuery(id="a", query="q", type="metadata", expected_doc_ids=["d1"])]
    scores = score_dataset(gold, results={}, k=5)  # no result for "a"
    assert scores["overall"]["doc_recall"] == 0.0


def test_unknown_query_type_rejected() -> None:
    with pytest.raises(ValueError):
        GoldQuery(id="bad", query="q", type="not-a-type")


# --- runner end-to-end against the stub ------------------------------------
def test_runner_scores_stub_end_to_end() -> None:
    gold = load_gold(run.GOLD_PATH)
    scores = run.run_eval(run._stub_retrieve, gold, k=5)

    assert scores["n"] == len(gold) > 0
    # The stub answers every query well, so doc recall + answer correctness are perfect…
    assert scores["overall"]["doc_recall"] == 1.0
    assert scores["overall"]["answer_correctness"] == 1.0
    # …but one semantic query is deliberately degraded, so fact_recall dips.
    assert scores["by_type"]["semantic"]["fact_recall"] < 1.0
