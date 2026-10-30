"""Bearer-token gate in front of the MCP app (SEC-MCP-AUTH, 16 Oct 2026; MCP-TOKEN-UI, 30 Oct 2026).

The token is set on the CRM's Settings > Integrations screen and lives encrypted in the backend
database; there is no env value for it any more. This server learns which tokens are valid by
asking the backend (`GET /api/v1/system/mcp-auth`, over the X-API-Key channel it already
uses). The answer holds SHA-256 digests of the valid tokens (current, plus the previous one
while it is in its rotation grace window) and the screen's Enforce switch, never a token.

- Enforce on: every request must carry `Authorization: Bearer <token>`; anything else is 401.
- Enforce off (including "no token set yet", the first deploy): a request with NO
  Authorization header passes and logs a warning (method and path only), so a release never
  takes the chatbot down. A request that does carry a bearer must match, or it is 401: that
  is what the release post-check's wrong-token probe relies on.
- The answer is cached for ``CACHE_TTL_SECONDS``. A bearer that matches nothing triggers one
  re-fetch (at most every ``MISS_REFRESH_SECONDS``) before it is refused, so a token rotated a
  second ago is not refused on a stale cache.
- Backend unreachable: the last answer is kept (an outage must not switch the gate off). If no
  answer has ever arrived, `/mcp` answers 503 until one does; the process does not exit.

`/healthz` is the one exempt path, so a probe can tell "up" from "refusing" without the token.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

HEALTH_PATH = "/healthz"
TOKEN_PATH = "/api/v1/system/mcp-auth"
CACHE_TTL_SECONDS = 30.0
MISS_REFRESH_SECONDS = 5.0
FETCH_TIMEOUT_SECONDS = 5.0
# Request headers that mean something only once the caller proved it holds the token.
AUTHENTICATED_ONLY_HEADERS = (b"x-mcp-scope", b"x-mcp-staff-user")

TokenFetcher = Callable[[], Awaitable[Any]]

# Indirection so tests can move time without sleeping.
_monotonic = time.monotonic


@dataclass(frozen=True)
class TokenState:
    digests: tuple[bytes, ...]
    enforce: bool


def _parse(answer: Any) -> TokenState:
    if not isinstance(answer, dict):
        raise ValueError("answer is not an object")
    enforce = answer.get("enforce")
    digests = answer.get("token_sha256")
    if not isinstance(enforce, bool) or not isinstance(digests, list):
        raise ValueError("answer has the wrong shape")
    if not all(isinstance(d, str) for d in digests):
        raise ValueError("answer has a non-text digest")
    return TokenState(tuple(d.strip().lower().encode() for d in digests), enforce)


def backend_fetcher(settings: Any, *, transport: httpx.AsyncBaseTransport | None = None) -> TokenFetcher:
    """The default fetcher: one GET to the backend with the server's X-API-Key."""
    url = settings.crm_base_url.rstrip("/") + TOKEN_PATH

    async def fetch() -> Any:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS, transport=transport) as client:
            resp = await client.get(
                url, headers={"X-API-Key": settings.external_api_key, "Accept": "application/json"}
            )
            resp.raise_for_status()
            return resp.json()

    return fetch


class TokenSource:
    """The backend's last answer, refreshed on a TTL and once on a miss."""

    def __init__(self, fetch: TokenFetcher) -> None:
        self._fetch = fetch
        self._state: TokenState | None = None
        self._fetched_at = float("-inf")  # last attempt, successful or not
        self._lock = asyncio.Lock()

    async def _refresh(self, *, min_age: float) -> None:
        async with self._lock:
            # Another request may have refreshed while this one waited for the lock.
            if _monotonic() - self._fetched_at < min_age:
                return
            self._fetched_at = _monotonic()
            try:
                self._state = _parse(await self._fetch())
            except Exception as exc:  # noqa: BLE001 - any failure keeps the last answer
                # The exception type only: a message could carry a URL or a body.
                logger.warning("could not refresh the MCP token list from the backend (%s)", type(exc).__name__)

    async def state(self) -> TokenState | None:
        if _monotonic() - self._fetched_at >= CACHE_TTL_SECONDS or (
            self._state is None and _monotonic() - self._fetched_at >= MISS_REFRESH_SECONDS
        ):
            await self._refresh(min_age=MISS_REFRESH_SECONDS if self._state is None else CACHE_TTL_SECONDS)
        return self._state

    async def accepts(self, presented: str) -> bool:
        wanted = hashlib.sha256(presented.encode()).hexdigest().encode()
        if self._matches(wanted):
            return True
        if _monotonic() - self._fetched_at < MISS_REFRESH_SECONDS:
            return False
        await self._refresh(min_age=MISS_REFRESH_SECONDS)
        return self._matches(wanted)

    def _matches(self, wanted: bytes) -> bool:
        state = self._state
        if state is None:
            return False
        # Every digest is compared, so the time taken does not say which one matched.
        found = False
        for digest in state.digests:
            found |= hmac.compare_digest(digest, wanted)
        return found


class BearerAuthMiddleware:
    def __init__(self, app: ASGIApp, source: TokenSource) -> None:
        self._app = app
        self._source = source

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            # lifespan must pass through so FastMCP's session manager starts.
            await self._app(scope, receive, send)
            return
        if scope["type"] != "http":
            # No websocket route exists; refuse anything that is not plain HTTP outright.
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return
        if scope["path"] == HEALTH_PATH:
            await PlainTextResponse("ok")(scope, receive, send)
            return
        state = await self._source.state()
        if state is None:
            await PlainTextResponse("MCP auth not ready", status_code=503)(scope, receive, send)
            return
        header = Headers(scope=scope).get("authorization")
        if header is None and not state.enforce:
            logger.warning(
                "unauthenticated MCP request allowed (Enforce is off): %s %s",
                scope.get("method", "-"),
                scope["path"],
            )
            # The staff scope opt-out (`scope.py`) is honoured only on an authenticated
            # request, so an unauthenticated one loses those headers before FastMCP sees it.
            scope = dict(scope)
            scope["headers"] = [
                (k, v) for k, v in scope["headers"] if k.lower() not in AUTHENTICATED_ONLY_HEADERS
            ]
        elif header is None or not await self._authorized(header):
            response = PlainTextResponse(
                "Unauthorized", status_code=401, headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)

    async def _authorized(self, header: str) -> bool:
        scheme, _, presented = header.partition(" ")
        presented = presented.strip()
        if scheme.lower() != "bearer" or not presented:
            return False
        return await self._source.accepts(presented)
