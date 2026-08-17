"""Short-lived tokens that let the PDF worker open a print page.

The worker drives headless Chromium at a URL. Chromium has no CRM session, so
the print page cannot be behind normal auth - and it must not be reachable by
anyone who guesses a download id either, because the rendered page may carry
prices the guesser is not entitled to.

So the print URL carries a token: an HMAC over the download id and an expiry,
signed with the app's JWT secret. It proves the URL came from the enqueue path,
it cannot be forged without the secret, and it stops mattering minutes later.

Deliberately NOT a JWT: there is no principal here and no claims worth carrying.
The download id already points at an `export_request`, which is the single
source of truth for who the render is for. A token that carried an audience of
its own would be a second answer to that question.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

from app.config import settings

# Long enough for a queue backlog, short enough that a leaked URL is stale by
# the time anyone finds it.
DEFAULT_TTL_SECONDS = 15 * 60


def _secret() -> bytes:
    secret = getattr(settings, "jwt_secret", None) or ""
    if not secret:
        raise RuntimeError("JWT_SECRET is required to sign render tokens")
    return secret.encode("utf-8")


def _sign(download_id: str, expires_at: int) -> str:
    payload = f"{download_id}:{expires_at}".encode("utf-8")
    return hmac.new(_secret(), payload, hashlib.sha256).hexdigest()


def issue(download_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS, now: Optional[int] = None) -> str:
    expires_at = int(now if now is not None else time.time()) + ttl_seconds
    return f"{expires_at}.{_sign(download_id, expires_at)}"


def verify(download_id: str, token: Optional[str], now: Optional[int] = None) -> bool:
    """True when ``token`` was issued for ``download_id`` and has not expired."""
    if not token or "." not in token:
        return False

    raw_expiry, _, signature = token.partition(".")
    try:
        expires_at = int(raw_expiry)
    except ValueError:
        return False

    current = int(now if now is not None else time.time())
    if expires_at < current:
        return False

    # compare_digest, not ==, so a wrong token cannot be discovered a byte at a
    # time by timing the response.
    return hmac.compare_digest(signature, _sign(download_id, expires_at))
