"""Make the backend's own redirects path-only.

Starlette's trailing-slash 307 (``/x`` -> ``/x/``) carries an absolute Location
built from the Host the backend saw. Behind the Next dev rewrite, or any proxy
that rewrites Host, that is the backend's own address (``http://localhost:8000``),
which is the wrong machine for a browser on another laptop: it follows the
redirect to its own localhost and reports "Failed to fetch". Many frontend
services call list routes without the slash the router declares, so this is a
class of failure, not one caller.

A path-only Location resolves against whatever origin the browser used, so the
redirect goes back through the same proxy. Only a Location on the backend's own
host is rewritten; a redirect to another host is left alone.
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from starlette.datastructures import URL, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


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
