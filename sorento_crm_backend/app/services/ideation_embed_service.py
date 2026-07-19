"""Ideas iframe embed-session mint (SSO) — sorento side of §5.3 (D7/D17).

A logged-in sorento user opening ``/ideas`` (board) or ``/ideas/{id}`` (detail) needs
to iframe the shared-service ideation UI with seamless auth. This service:

  1. mints a short-lived **signed assertion** for the user
     (``ideation_embed_signing_secret``, audience ``"ideation-embed"``, carrying the
     ``ideation_embed_connection_id``);
  2. POSTs it to ``{ideation_shared_service_url}/embed/session`` (server-to-server httpx)
     which returns an embed token (``typ="embed"``);
  3. returns ``{ iframe_url, token, expires_at }`` where ``iframe_url`` =
     ``{shared}/embed/ideas[/{id}]`` — the FE iframes that URL and passes the token per
     the embed framework.

DORMANT when any of the three settings is blank (``IdeationEmbedNotConfigured`` → the
router returns a clean 4xx, never a 500). A shared-service outage raises
``IdeationEmbedUpstreamError`` → the router returns a clean 502 the FE turns into a
retry state (AC-44). **Secrets** (signing secret, the minted assertion, the embed token)
are never logged.

The shared-service ``/embed/session`` endpoint is in the DEFERRED capture-spine set
(embed framework not built yet); this service is built + tested against the §5.3 contract
with that POST stubbed. Live-iframe verification (AC-43/45) is DEFERRED to that dependency.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from jose import jwt

from app.config import settings

logger = logging.getLogger(__name__)

_EMBED_SESSION_PATH = "/embed/session"
_EMBED_IDEAS_PATH = "/embed/ideas"
_ASSERTION_AUDIENCE = "ideation-embed"
_ASSERTION_TTL_SECONDS = 120  # short-lived — exchanged immediately for an embed token
_TIMEOUT_SECONDS = 15


class IdeationEmbedNotConfigured(Exception):
    """Raised when the ideation embed settings are blank (feature dormant)."""


class IdeationEmbedUpstreamError(Exception):
    """Raised when the shared-service ``/embed/session`` call cannot be completed
    (outage/timeout/HTTP error/malformed body/missing token)."""


def mint_embed_assertion(user: dict[str, Any]) -> str:
    """Sign a short-lived assertion identifying the logged-in user for the embed
    connection. Signed with ``ideation_embed_signing_secret`` (never the app JWT
    secret) so the shared-service verifies it against the embed connection only."""
    secret = settings.ideation_embed_signing_secret
    connection_id = settings.ideation_embed_connection_id
    if not secret or not connection_id:
        raise IdeationEmbedNotConfigured("ideation embed signing not configured")

    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "typ": "assertion",
        "aud": _ASSERTION_AUDIENCE,
        "iss": "sorento",
        "sub": str(user.get("id") or ""),
        "email": user.get("email"),
        "name": user.get("name"),
        "connection_id": connection_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=_ASSERTION_TTL_SECONDS)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def post_embed_session(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST the signed assertion to shared-service ``/embed/session`` (server-to-server).

    Raises ``IdeationEmbedUpstreamError`` on any transport/HTTP/parse failure so the
    caller returns a clean 502 instead of a 500 crash (AC-44)."""
    url = base_url.rstrip("/") + _EMBED_SESSION_PATH
    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise IdeationEmbedUpstreamError(f"embed session request failed: {exc}") from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise IdeationEmbedUpstreamError(f"embed session returned a malformed body: {exc}") from exc
    if not isinstance(data, dict):
        raise IdeationEmbedUpstreamError("embed session returned a non-object body")
    return data


def create_embed_session(user: dict[str, Any], *, idea_id: str | None = None) -> dict[str, Any]:
    """Mint an embed session for ``user``. Returns ``{ iframe_url, token, expires_at }``.

    Raises ``IdeationEmbedNotConfigured`` (dormant) or ``IdeationEmbedUpstreamError``
    (shared-service outage / bad response)."""
    base_url = settings.ideation_shared_service_url
    secret = settings.ideation_embed_signing_secret
    connection_id = settings.ideation_embed_connection_id
    if not base_url or not secret or not connection_id:
        raise IdeationEmbedNotConfigured("ideation embed not configured for this deployment")

    assertion = mint_embed_assertion(user)
    request_payload: dict[str, Any] = {
        "connection_id": connection_id,
        "assertion": assertion,
    }
    if idea_id:
        request_payload["idea_id"] = idea_id

    try:
        data = post_embed_session(base_url, request_payload)
    except IdeationEmbedUpstreamError:
        # Log WITHOUT the assertion/secret/token — just the failure fact.
        logger.warning("ideation embed session mint failed (shared-service upstream).", exc_info=True)
        raise

    token = data.get("token")
    if not token:
        raise IdeationEmbedUpstreamError("embed session response missing token")

    iframe_url = base_url.rstrip("/") + _EMBED_IDEAS_PATH + (f"/{idea_id}" if idea_id else "")
    return {
        "iframe_url": iframe_url,
        "token": token,
        "expires_at": data.get("expires_at"),
    }
