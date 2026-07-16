"""Bounded retry with exponential backoff for transient network failures.

Provider-agnostic: callers pass an `is_retryable` predicate so only transient
errors (timeouts, connection drops, HTTP 429/5xx) are retried — never 4xx, auth,
or validation errors, which fail fast. Backoff is exponential with full jitter,
capped at `max_delay`. `sleep`/`rng` are injectable so tests run instantly and
deterministically.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def with_retry(
    func: Callable[[], T],
    *,
    attempts: int,
    base_delay: float,
    is_retryable: Callable[[Exception], bool],
    max_delay: float = 30.0,
    sleep: Callable[[float], None] | None = None,
    rng: Callable[[], float] | None = None,
) -> T:
    """Call `func`, retrying transient failures up to `attempts` total tries.

    Sleeps ``min(max_delay, base_delay * 2**(n-1)) * random()`` between attempts
    (full jitter). A non-retryable exception, or the final attempt, re-raises.
    """
    _sleep = sleep or time.sleep
    _rng = rng or random.random
    attempt = 0
    while True:
        attempt += 1
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 — re-raised unless transient + retries remain
            if attempt >= attempts or not is_retryable(exc):
                raise
            backoff = min(max_delay, base_delay * (2 ** (attempt - 1)))
            _sleep(backoff * _rng())
