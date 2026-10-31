"""Test double for the backend's `GET /api/v1/system/mcp-auth` answer (MCP-TOKEN-UI).

The MCP server no longer reads its token from env: it asks the backend which tokens are valid
and gets SHA-256 digests back. Tests hand `create_http_app` a fetcher built here instead of
letting it call a backend that does not exist.
"""
from __future__ import annotations

import hashlib


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class FakeBackend:
    """A mutable stand-in for the backend: change `tokens` / `enforce` / `down` mid-test."""

    def __init__(self, tokens: list[str] | None = None, *, enforce: bool = True) -> None:
        self.tokens = list(tokens or [])
        self.enforce = enforce
        self.down = False
        self.calls = 0

    async def __call__(self) -> dict:
        self.calls += 1
        if self.down:
            raise ConnectionError("backend unreachable")
        return {"enforce": self.enforce, "token_sha256": [digest(t) for t in self.tokens]}
