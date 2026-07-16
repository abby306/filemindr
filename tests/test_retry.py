"""Retry utility: success, flaky-then-success, fail-fast, and exhaustion.

`sleep`/`rng` are injected so the tests run instantly and deterministically — no
real backoff waits.
"""

from __future__ import annotations

import pytest

from app.core.retry import with_retry

_ALWAYS = lambda exc: True  # noqa: E731
_NEVER = lambda exc: False  # noqa: E731


def _no_sleep() -> tuple[list[float], dict]:
    slept: list[float] = []
    return slept, {"sleep": slept.append, "rng": lambda: 1.0}


def test_returns_immediately_on_success() -> None:
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    slept, inject = _no_sleep()
    assert with_retry(fn, attempts=3, base_delay=0.5, is_retryable=_ALWAYS, **inject) == "ok"
    assert calls["n"] == 1
    assert slept == []


def test_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("transient")
        return "recovered"

    slept, inject = _no_sleep()
    result = with_retry(flaky, attempts=3, base_delay=0.5, is_retryable=_ALWAYS, **inject)
    assert result == "recovered"
    assert calls["n"] == 3
    # Backed off between the two failures: 0.5*2^0, 0.5*2^1 (rng pinned to 1.0).
    assert slept == [0.5, 1.0]


def test_non_retryable_fails_fast() -> None:
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ValueError("4xx-ish")

    slept, inject = _no_sleep()
    with pytest.raises(ValueError):
        with_retry(fn, attempts=3, base_delay=0.5, is_retryable=_NEVER, **inject)
    assert calls["n"] == 1  # never retried
    assert slept == []


def test_exhausts_attempts_and_reraises() -> None:
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise TimeoutError("still down")

    slept, inject = _no_sleep()
    with pytest.raises(TimeoutError):
        with_retry(always_fail, attempts=3, base_delay=0.5, is_retryable=_ALWAYS, **inject)
    assert calls["n"] == 3  # attempts total
    assert len(slept) == 2  # slept between attempts, not after the last


def test_backoff_is_capped_by_max_delay() -> None:
    def fail():
        raise TimeoutError("down")

    slept, inject = _no_sleep()
    with pytest.raises(TimeoutError):
        with_retry(fail, attempts=5, base_delay=10.0, is_retryable=_ALWAYS, max_delay=15.0, **inject)
    assert all(s <= 15.0 for s in slept)
