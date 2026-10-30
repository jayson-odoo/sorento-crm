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
extractors wait on an LLM, and would queue behind an export for nothing; nor the reports the chatbot calls as MCP
tools, nor public portal routes (see tests/test_heavy_work.py WRAPPED). A request that waits `HEAVY_WAIT_SECONDS`
(default 60) for its turn is answered 503 with Retry-After. A queued request whose client has gone still runs when its
turn comes (uvicorn reports a disconnect only through `receive`); the wait bound keeps that queue short.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Optional, TypeVar

from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Match
from starlette.types import ASGIApp, Receive, Scope, Send

F = TypeVar("F", bound=Callable[..., Any])
logger = logging.getLogger(__name__)


def heavy(fn: F) -> F:
    """Mark a route handler as heavy (see the module doc). Put it under the router decorator."""
    fn.heavy = True  # type: ignore[attr-defined]
    return fn


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    try:
        return int(raw) if raw.strip() else default
    except ValueError:
        logger.warning("%s=%r is not a whole number; using %d", name, raw, default)
        return default


def concurrency() -> int:
    """`HEAVY_HANDLER_CONCURRENCY`, read when a worker's middleware first runs; 0 (or less) = no limit."""
    return _int_env("HEAVY_HANDLER_CONCURRENCY", 1)


def wait_seconds() -> int:
    """`HEAVY_WAIT_SECONDS`: how long a heavy request waits for its turn before it is answered 503 (security review,
    30 Oct: one slow upload body, read inside the turn and before auth, must not queue every other export forever,
    and a short queue also drains inside a recycle's graceful shutdown)."""
    return _int_env("HEAVY_WAIT_SECONDS", 60)


class HeavyRouteLimit:
    """``routes`` is the live app route list; it is read on the first request, after every include_router has run."""

    def __init__(self, app: ASGIApp, routes: list[BaseRoute]) -> None:
        self.app = app
        self._routes = routes
        self._heavy: Optional[list[BaseRoute]] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._limit: Optional[int] = None
        self._wait = 0

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
            self._wait = wait_seconds()
            self._semaphore = asyncio.Semaphore(self._limit) if self._limit > 0 else None
        if self._semaphore is None:
            await self.app(scope, receive, send)
            return
        try:
            if self._semaphore.locked():
                await asyncio.wait_for(self._semaphore.acquire(), timeout=self._wait)
            else:
                await self._semaphore.acquire()  # free: taken at once, no wait (and no timeout at 0)
        except asyncio.TimeoutError:
            busy = JSONResponse(
                {"detail": "The server is busy with another export or import. Try again in a moment."},
                status_code=503, headers={"Retry-After": "5"},
            )
            await busy(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            self._semaphore.release()
