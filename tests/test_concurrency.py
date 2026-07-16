"""Bounded parallel map: order preservation, fallbacks, and the concurrency cap."""

from __future__ import annotations

import threading
import time

from app.core.concurrency import map_bounded


def test_preserves_order() -> None:
    assert map_bounded(lambda x: x * 2, [1, 2, 3, 4], max_workers=3) == [2, 4, 6, 8]


def test_empty_and_single_worker_fallbacks() -> None:
    assert map_bounded(lambda x: x, [], max_workers=4) == []
    assert map_bounded(lambda x: x + 1, [1, 2, 3], max_workers=1) == [2, 3, 4]


def test_caps_concurrency_at_max_workers() -> None:
    active = {"now": 0, "max": 0}
    lock = threading.Lock()

    def work(x: int) -> int:
        with lock:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        time.sleep(0.02)  # hold the slot so overlap is observable
        with lock:
            active["now"] -= 1
        return x * 2

    out = map_bounded(work, list(range(12)), max_workers=4)

    assert out == [x * 2 for x in range(12)]  # order preserved despite parallelism
    assert active["max"] <= 4  # never exceeded the cap
    assert active["max"] > 1  # but did run in parallel
