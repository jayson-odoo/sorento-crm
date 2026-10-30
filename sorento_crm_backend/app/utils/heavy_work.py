"""BACKEND-MEM-2 S2: at most `HEAVY_HANDLER_CONCURRENCY` heavy handlers at once per worker (default 1, 0 = no limit).

Since API-NONBLOCKING (#1951) a `def` handler runs in anyio's 40-thread pool, so one worker could build several
exports, reports or PDFs at the same time. A worker keeps the memory of its busiest moment until it exits: the same
work kept +160 MB one at a time, +528 MB eight at once, +900-1,170 MB 24 at once, and ran no faster (the GIL), see
documentation/plans/deploy/PLAN-backend-mem-2-30oct.md. `@heavy` makes those handlers take turns.

Only the handlers that build or parse a large file or result wear it. Not the whole pool: `def chat_turn` runs in the
same pool and waits on the LLM, so a global limit would queue chat turns behind an export. A handler waiting for its
turn blocks one pool thread, never the event loop. Re-entrant per thread: a heavy handler that calls another one does
not wait for itself.
"""
from __future__ import annotations

import functools
import inspect
import os
import threading
from typing import Any, Callable, Optional, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def _from_env() -> Optional[threading.BoundedSemaphore]:
    n = int(os.getenv("HEAVY_HANDLER_CONCURRENCY", "1") or "1")
    return threading.BoundedSemaphore(n) if n > 0 else None


_semaphore = _from_env()
_held = threading.local()


def heavy(fn: F) -> F:
    """Mark a sync route handler as heavy (see the module doc). Put it under the router decorator."""
    if inspect.iscoroutinefunction(fn):
        raise TypeError(f"@heavy on async def {fn.__name__}: it would wait on the event loop")

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        sem = _semaphore
        if sem is None or getattr(_held, "on", False):
            return fn(*args, **kwargs)
        with sem:
            _held.on = True
            try:
                return fn(*args, **kwargs)
            finally:
                _held.on = False

    wrapper.heavy = True  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]
