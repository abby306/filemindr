"""Gold-query and retrieval-result schemas for the eval harness.

A `GoldQuery` states what a good answer must surface: the documents that should
be retrieved, fact substrings that should appear among the retrieved facts, and
phrases the final answer must contain. A `RetrievedAnswer` is what a retrieval
implementation returns for one query — ranked doc ids, ranked fact texts, and a
synthesized answer. The scorers compare the two.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Query intents, mirroring the retrieval router in TECH_SPEC.md.
QUERY_TYPES = frozenset({"metadata", "semantic", "lexical", "aggregate"})


@dataclass(frozen=True)
class GoldQuery:
    id: str
    query: str
    type: str
    expected_doc_ids: list[str] = field(default_factory=list)
    expected_fact_substrings: list[str] = field(default_factory=list)
    answer_contains: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.type not in QUERY_TYPES:
            raise ValueError(f"{self.id}: unknown query type {self.type!r}")


@dataclass(frozen=True)
class RetrievedAnswer:
    """A retrieval implementation's output for one query (ranked best-first)."""

    doc_ids: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    answer: str = ""


def load_gold(path: str | Path) -> list[GoldQuery]:
    """Load and validate a gold query set from a YAML file."""
    data = yaml.safe_load(Path(path).read_text()) or []
    return [GoldQuery(**row) for row in data]
