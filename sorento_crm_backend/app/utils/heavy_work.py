"""BACKEND-MEM-2 S2: at most `HEAVY_HANDLER_CONCURRENCY` heavy requests at once per worker (default 1, 0 = no limit).

Since API-NONBLOCKING (#1951) a `def` handler runs in anyio's 40-thread pool, so one worker could build several
exports, reports or PDFs at the same time. A worker keeps the memory of its busiest moment until it exits: the same
work kept +160 MB one at a time, +528 MB eight at once, +900-1,170 MB 24 at once, and ran no faster (the GIL), see
documentation/plans/deploy/PLAN-backend-mem-2-30oct.md. Routes marked `@heavy` take turns.

The limit is the ASGI middleware below, not a lock around the handler: FastAPI validates and serializes what a
handler returns (a 15k-row export) after the handler has returned, and an upload's body is read before it starts, so
a lock around the handler alone left most of the memory unbounded (measured: 566 -> 543 MB). The middleware holds
the turn for the whole request, body to last byte sent, and waits on an asyncio semaphore: a queued request holds no
thread and never blocks the event loop.

Only the routes that build or parse a large file or result wear it. Not the whole pool: `def chat_turn` and the AI
extractors wait on an LLM, and would queue behind an export for nothing.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Callable, Optional, TypeVar

from starlette.routing import BaseRoute, Match
from starlette.types import ASGIApp, Receive, Scope, Send

F = TypeVar("F", bound=Callable[..., Any])


def heavy(fn: F) -> F:
    """Mark a route handler as heavy (see the module doc). Put it under the router decorator."""
    fn.heavy = True  # type: ignore[attr-defined]
    return fn


def concurrency() -> int:
    """`HEAVY_HANDLER_CONCURRENCY`, read when a worker's middleware first runs; 0 (or less) = no limit."""
    return int(os.getenv("HEAVY_HANDLER_CONCURRENCY", "1") or "1")


class HeavyRouteLimit:
    """``routes`` is the live app route list; it is read on the first request, after every include_router has run."""

    def __init__(self, app: ASGIApp, routes: list[BaseRoute]) -> None:
        self.app = app
        self._routes = routes
        self._heavy: Optional[list[BaseRoute]] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._limit: Optional[int] = None

    def _is_heavy(self, scope: Scope) -> bool:
        if self._heavy is None:
            self._heavy = [r for r in self._routes if getattr(getattr(r, "endpoint", None), "heavy", False)]
        return any(r.matches(scope)[0] == Match.FULL for r in self._heavy)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._is_heavy(scope):
            await self.app(scope, receive, send)
            return
        if self._limit is None:
            # Created here, in the worker and on its event loop, never in the preloading master.
            self._limit = concurrency()
            self._semaphore = asyncio.Semaphore(self._limit) if self._limit > 0 else None
        if self._semaphore is None:
            await self.app(scope, receive, send)
            return
        async with self._semaphore:
            await self.app(scope, receive, send)
