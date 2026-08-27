"""Viewer-scoped byte proxy for chat attachments (UAC AC-N4).

An attachment bubble points at bytes on a host that sends no CORS headers - the
R2 CDN, CloudFront, or Respond's own media hosts. Images and PDFs render from a
direct URL regardless (the browser does not need to READ those bytes from
JavaScript), but the spreadsheet / csv preview does have to fetch them, and the
fetch is blocked. So the preview surface asks the backend for the bytes instead.

A backend that fetches a caller-supplied URL is an SSRF gadget. Two rules keep
this one from being that:

1. **Host allowlist, exact match.** Our configured storage hosts (from
   ``R2_CDN_DOMAIN`` / ``CLOUDFRONT_DOMAIN`` - the same env the storage layer
   reads, never hardcoded) plus Respond's media hosts, which were learnt by
   inspecting real attachment URLs on live threads (an inbound WhatsApp file
   arrives on ``cdn.chatapi.net``; a file uploaded from the Respond app arrives
   on ``production--bucket.s3-accelerate.amazonaws.com``). Comparison is host
   EQUALITY, never a suffix test: ``evil-cdn.chatapi.net.attacker.test`` ends
   with an allowlisted label and must still be refused.
2. **Redirects are re-validated, not followed.** ``follow_redirects`` stays off
   and each hop's ``Location`` goes back through the allowlist, so an
   allowlisted host cannot bounce us onto an internal address.

Plus the ordinary hardening: a size cap, a timeout, no request headers
forwarded (nothing of ours is sent to the upstream), and no response headers
forwarded except the content type and length.

``CHAT_MEDIA_PROXY_EXTRA_HOSTS`` (comma separated) is an operational escape
hatch for a deployment whose media sits on a host neither env var names - for
example a database copied from an environment with a different CDN domain.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional
from urllib.parse import unquote, urlparse

import httpx
from fastapi import status
from fastapi.responses import StreamingResponse

from app.services.error_handler import AppException
from app.utils.http import content_disposition

logger = logging.getLogger(__name__)

# 50 MB. Above this the preview is not a preview, and streaming it ties up a
# worker for as long as the upstream feels like taking.
MAX_BYTES = 50 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
TIMEOUT_SECONDS = 30.0
MAX_REDIRECTS = 3

# Learnt from live threads (2026-08-15), not guessed:
#   cdn.chatapi.net                                  inbound WhatsApp media
#   production--bucket.s3-accelerate.amazonaws.com   files sent from the Respond app
RESPOND_MEDIA_HOSTS = (
    "cdn.chatapi.net",
    "production--bucket.s3-accelerate.amazonaws.com",
)

_STORAGE_HOST_ENV = ("R2_CDN_DOMAIN", "CLOUDFRONT_DOMAIN")
_EXTRA_HOST_ENV = "CHAT_MEDIA_PROXY_EXTRA_HOSTS"


def _host_of(value: str) -> str:
    """The bare hostname of a configured domain, however it was written.

    Operators write ``cdn.example.com``, ``https://cdn.example.com`` and
    ``https://cdn.example.com/`` interchangeably in .env files; all three have
    to reduce to the same allowlist entry.
    """
    raw = (value or "").strip().rstrip("/")
    if not raw:
        return ""
    if "//" in raw:
        raw = urlparse(raw).netloc or raw
    return raw.split("/")[0].split("@")[-1].lower()


@lru_cache(maxsize=1)
def allowed_hosts() -> frozenset[str]:
    hosts = {h.lower() for h in RESPOND_MEDIA_HOSTS}
    for env in _STORAGE_HOST_ENV:
        host = _host_of(os.getenv(env) or "")
        if host:
            hosts.add(host)
    for chunk in (os.getenv(_EXTRA_HOST_ENV) or "").split(","):
        host = _host_of(chunk)
        if host:
            hosts.add(host)
    return frozenset(hosts)


def assert_allowed(url: str) -> str:
    """Return the URL, or raise 400. The only gate between a caller-supplied
    string and an outbound HTTP request."""
    raw = (url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="That attachment URL cannot be loaded.",
            detail="Only http(s) URLs on a known media host can be proxied.",
            code="media_proxy_host_not_allowed",
        )
    if parsed.hostname.lower() not in allowed_hosts():
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="That attachment URL cannot be loaded.",
            detail=f"Host '{parsed.hostname}' is not a known media host.",
            code="media_proxy_host_not_allowed",
        )
    return raw


def _filename_of(url: str) -> str:
    path = urlparse(url).path or ""
    return unquote(path.rsplit("/", 1)[-1]).strip() or "attachment"


def _client_factory(**kwargs) -> httpx.AsyncClient:
    """Seam for tests: patched with a MockTransport-backed factory so the proxy
    is exercised end to end without touching the network."""
    return httpx.AsyncClient(**kwargs)


async def stream(url: str) -> StreamingResponse:
    """Proxy the bytes at ``url`` back to the caller.

    Authorisation is the CALLER's job - both routes that reach here have
    already applied their gate (ticket scope for the drawer, the
    ``conversations.view`` permission for the inbox). This function only decides
    whether the URL itself is one we are willing to fetch.
    """
    target = assert_allowed(url)
    client = _client_factory(timeout=TIMEOUT_SECONDS, follow_redirects=False)

    try:
        response = await _send_following_allowlisted_redirects(client, target)
    except AppException:
        await client.aclose()
        raise
    except httpx.HTTPError as exc:
        await client.aclose()
        logger.warning("media proxy upstream error for %s: %s", target, exc)
        raise AppException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            message="That attachment could not be loaded right now.",
            detail=str(exc),
            code="media_proxy_upstream_error",
        )

    async def _fail(status_code: int, message: str, detail: str, code: str):
        await response.aclose()
        await client.aclose()
        return AppException(
            status_code=status_code, message=message, detail=detail, code=code
        )

    if response.status_code >= 400:
        raise await _fail(
            response.status_code,
            "That attachment could not be loaded.",
            f"The media host answered {response.status_code}.",
            "media_proxy_upstream_status",
        )

    declared = response.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise await _fail(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "That attachment is too large to preview.",
            f"{int(declared)} bytes exceeds the {MAX_BYTES} byte preview cap.",
            "media_proxy_too_large",
        )

    headers = {"Content-Disposition": content_disposition(_filename_of(target), inline=True)}
    if declared and declared.isdigit():
        headers["Content-Length"] = declared

    async def body():
        sent = 0
        try:
            async for chunk in response.aiter_bytes(CHUNK_BYTES):
                sent += len(chunk)
                if sent > MAX_BYTES:
                    # The status line is long gone, so the only honest thing
                    # left is to stop and say so in the log.
                    logger.warning(
                        "media proxy truncated %s at the %s byte cap", target, MAX_BYTES
                    )
                    break
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(
        body(),
        status_code=status.HTTP_200_OK,
        media_type=response.headers.get("content-type") or "application/octet-stream",
        headers=headers,
    )


async def _send_following_allowlisted_redirects(
    client: httpx.AsyncClient, url: str
) -> httpx.Response:
    """GET ``url``, re-validating every redirect hop against the allowlist."""
    target = url
    for _hop in range(MAX_REDIRECTS + 1):
        response = await client.send(client.build_request("GET", target), stream=True)
        if response.status_code not in (301, 302, 303, 307, 308):
            return response
        location: Optional[str] = response.headers.get("location")
        await response.aclose()
        if not location:
            raise AppException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                message="That attachment could not be loaded.",
                detail="The media host sent a redirect with no destination.",
                code="media_proxy_bad_redirect",
            )
        target = str(httpx.URL(target).join(location))
        # The whole point: an allowlisted host must not be able to bounce us
        # somewhere we would never have fetched directly.
        assert_allowed(target)
    raise AppException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        message="That attachment could not be loaded.",
        detail="Too many redirects from the media host.",
        code="media_proxy_redirect_loop",
    )
