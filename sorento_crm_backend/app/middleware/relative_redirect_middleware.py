"""Trailing-slash tolerance for the API, without a redirect.

The router declares list routes as ``@router.get("/")`` and most frontend
services call them without the slash (quick-access on every page, products,
warehouses, orders, spo-allocations). Starlette's default answer is a 307 to
the slashed path, built from the Host the backend saw. Behind the Next dev
rewrite that is ``http://localhost:8000``, the wrong machine for a browser on
another laptop, and even a path-only redirect loops with Next's own
trailing-slash handling or is dropped by some browsers.

Two layers, both cheap:

1. ``SlashTolerantPathMiddleware`` fixes the path in the ASGI scope before
   routing: if ``/x`` is not a static route but ``/x/`` is, the request is
   served as ``/x/`` in one round trip. Static paths only (no ``{param}``),
   computed once from the flat route table on first request, O(1) after.
2. ``RelativeRedirectMiddleware`` makes any remaining own-host redirect
   Location path-only, so it resolves against the origin the browser used.
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from starlette.datastructures import URL, MutableHeaders
from starlette.routing import BaseRoute
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def static_route_paths(routes: list[BaseRoute]) -> frozenset[str]:
    """Every literal route path (no ``{param}`` segment) in the flat route table."""
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str) and "{" not in path:
            paths.add(path)
    return frozenset(paths)


class SlashTolerantPathMiddleware:
    """``routes`` is the live app route list; it is read on first request, after
    every include_router has run, so the table is complete."""

    def __init__(self, app: ASGIApp, routes: list[BaseRoute]) -> None:
        self.app = app
        self._routes = routes
        self._static: frozenset[str] | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            if self._static is None:
                self._static = static_route_paths(self._routes)
            path = scope["path"]
            if not path.endswith("/") and path not in self._static and path + "/" in self._static:
                scope["path"] = path + "/"
                scope["raw_path"] = scope["path"].encode()
        await self.app(scope, receive, send)


class RelativeRedirectMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        own_host = URL(scope=scope).netloc

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] in (301, 302, 307, 308):
                headers = MutableHeaders(scope=message)
                location = headers.get("location")
                if location:
                    parts = urlsplit(location)
                    if parts.netloc and parts.netloc == own_host:
                        headers["location"] = urlunsplit(("", "", parts.path, parts.query, parts.fragment))
            await send(message)

        await self.app(scope, receive, send_wrapper)
