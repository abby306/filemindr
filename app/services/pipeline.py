"""Bounded in-process execution for the document pipeline.

FastAPI `BackgroundTasks` run each task on the server's shared request
threadpool with no concurrency cap — a 30-file drop used to start 30
simultaneous OCR→extraction→embedding chains, each holding a DB connection
for minutes, exhausting the connection pool (500s on uploads, chains dying
mid-flight and stranding documents at `received`). All pipeline work now
funnels through one small dedicated executor: uploads enqueue instantly,
`PIPELINE_WORKERS` documents process at a time, and the rest wait their turn.

`PIPELINE_WORKERS=0` runs submissions inline on the caller's thread — the
test suite uses this so an upload's whole chain completes synchronously
under TestClient, exactly as before. (A Redis-backed worker replaces this
module when durability across restarts matters; the seam is `submit`.)
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from app.core.config import get_settings

_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def _get_executor(workers: int) -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        with _lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=workers, thread_name_prefix="pipeline"
                )
    return _executor


def submit(fn: Callable[..., Any], *args: Any) -> None:
    """Run `fn(*args)` on the bounded pipeline pool (inline when workers<=0).

    Fire-and-forget: the entry points own their errors (they mark the document
    `failed` and log a processing event rather than raising).
    """
    workers = get_settings().pipeline_workers
    if workers <= 0:
        fn(*args)
        return
    _get_executor(workers).submit(fn, *args)
