"""Bounded parallelism for the network phase of document processing.

Large documents fan out into many independent network calls (per-chunk
extraction, per-page OCR). `map_bounded` runs them over a small thread pool with
a hard concurrency cap, preserving input order. It is deliberately minimal: each
call site already owns its retry/error-tolerance, so the mapped function is
expected not to raise — it returns a result the caller can classify. Only truly
unexpected exceptions propagate.

Threads (not processes) are right here: the work is I/O-bound (HTTP), so the GIL
is released during the calls, and there is nothing to pickle.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


def map_bounded(
    func: Callable[[T], R], items: Sequence[T], *, max_workers: int
) -> list[R]:
    """Apply `func` to `items` over at most `max_workers` threads, in input order.

    Falls back to a plain serial map for an empty input or a single worker, so
    there is no pool overhead in the common (short-document) case.
    """
    if not items:
        return []
    workers = max(1, min(max_workers, len(items)))
    if workers == 1:
        return [func(item) for item in items]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(func, items))
