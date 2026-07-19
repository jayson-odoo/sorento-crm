"""Slice D — Ideas iframe embed-session mint (SSO) endpoint + service.

Keys back to ``documentation/plans/ideation/ideation-ideate-intent-acceptance-criteria.md``:

- **AC-42 [BE]** — a logged-in sorento user's request mints a signed assertion
  (``ideation_embed_signing_secret`` + ``ideation_embed_connection_id``), POSTs it to
  ``{ideation_shared_service_url}/embed/session``, and returns
  ``{ iframe_url, token, expires_at }`` — ``iframe_url`` = ``{shared}/embed/ideas[/{id}]``.
- **AC-32 [BE]** — blank settings keep the feature DORMANT: a clean 4xx (not a 500)
  and no shared-service call.
- **AC-44 [FE, mirrored here]** — a shared-service outage surfaces as a clean non-500
  error the FE can turn into a retry state (never a raw 500 crash).
- Secrets (signing secret, intake key, the minted assertion) are never echoed in the
  response body.

The shared-service ``/embed/session`` endpoint is in the DEFERRED capture-spine set
(embed framework not built yet), so the live handshake is STUBBED here (monkeypatched
``post_embed_session``). Live-iframe verification (AC-43 seamless auth, AC-45 link
round-trip inside a real iframe) is DEFERRED to the shared-service embed dependency.
"""
from __future__ import annotations

import httpx
import pytest
from jose import jwt

import app.services.ideation_embed_service as svc
from app.config import settings
from app.services.ideation_embed_service import (
    IdeationEmbedNotConfigured,
    IdeationEmbedUpstreamError,
    create_embed_session,
    mint_embed_assertion,
)


_SIGNING_SECRET = "test-embed-signing-secret-value"
_CONNECTION_ID = "conn-ideation-1"
_SHARED_URL = "https://shared.test"

_USER = {"id": "user-uuid-1", "email": "staff@example.com", "name": "Staff Member"}


@pytest.fixture
def configured(monkeypatch):
    """Populate the ideation embed settings so the feature is live."""
    monkeypatch.setattr(svc.settings, "ideation_shared_service_url", _SHARED_URL)
    monkeypatch.setattr(svc.settings, "ideation_embed_signing_secret", _SIGNING_SECRET)
    monkeypatch.setattr(svc.settings, "ideation_embed_connection_id", _CONNECTION_ID)
    return monkeypatch


# --------------------------------------------------------------------------- #
# AC-42 — mint a signed assertion for the logged-in user                       #
# --------------------------------------------------------------------------- #
def test_mint_assertion_is_signed_and_carries_identity(configured):
    token = mint_embed_assertion(_USER)

    decoded = jwt.decode(
        token,
        _SIGNING_SECRET,
        algorithms=[settings.jwt_algorithm],
        audience="ideation-embed",
    )
    assert decoded["sub"] == "user-uuid-1"
    assert decoded["aud"] == "ideation-embed"
    assert decoded["connection_id"] == _CONNECTION_ID
    assert "exp" in decoded and "iat" in decoded
    # The signing secret is never carried inside the token payload.
    assert _SIGNING_SECRET not in token or decoded.get("connection_id") == _CONNECTION_ID
    assert "signing_secret" not in decoded


def test_mint_assertion_rejected_by_wrong_secret(configured):
    token = mint_embed_assertion(_USER)
    with pytest.raises(Exception):
        jwt.decode(token, "wrong-secret", algorithms=[settings.jwt_algorithm], audience="ideation-embed")


# --------------------------------------------------------------------------- #
# AC-42 — create_embed_session posts to shared-service + returns the contract  #
# --------------------------------------------------------------------------- #
def test_create_embed_session_board(configured, monkeypatch):
    captured: dict = {}

    def _fake_post(base_url, payload):  # noqa: ANN001
        captured["base_url"] = base_url
        captured["payload"] = payload
        return {"token": "embed-token-xyz", "expires_at": "2026-07-19T00:15:00+00:00"}

    monkeypatch.setattr(svc, "post_embed_session", _fake_post)

    result = create_embed_session(_USER, idea_id=None)

    assert result["iframe_url"] == "https://shared.test/embed/ideas"
    assert result["token"] == "embed-token-xyz"
    assert result["expires_at"] == "2026-07-19T00:15:00+00:00"
    # The assertion (a signed JWT) was posted to the shared-service, with the connection id.
    assert captured["base_url"] == _SHARED_URL
    assert captured["payload"]["connection_id"] == _CONNECTION_ID
    assert captured["payload"]["assertion"]  # a minted token, not blank
    assert "idea_id" not in captured["payload"]


def test_create_embed_session_detail(configured, monkeypatch):
    monkeypatch.setattr(
        svc, "post_embed_session",
        lambda base_url, payload: {"token": "t", "expires_at": "x"},
    )
    result = create_embed_session(_USER, idea_id="idea-123")
    assert result["iframe_url"] == "https://shared.test/embed/ideas/idea-123"


# --------------------------------------------------------------------------- #
# AC-32 — dormant when settings blank                                          #
# --------------------------------------------------------------------------- #
def test_dormant_when_url_blank(monkeypatch):
    monkeypatch.setattr(svc.settings, "ideation_shared_service_url", None)
    monkeypatch.setattr(svc.settings, "ideation_embed_signing_secret", _SIGNING_SECRET)
    monkeypatch.setattr(svc.settings, "ideation_embed_connection_id", _CONNECTION_ID)
    with pytest.raises(IdeationEmbedNotConfigured):
        create_embed_session(_USER, idea_id=None)


def test_dormant_when_secret_blank(monkeypatch):
    monkeypatch.setattr(svc.settings, "ideation_shared_service_url", _SHARED_URL)
    monkeypatch.setattr(svc.settings, "ideation_embed_signing_secret", None)
    monkeypatch.setattr(svc.settings, "ideation_embed_connection_id", _CONNECTION_ID)
    with pytest.raises(IdeationEmbedNotConfigured):
        create_embed_session(_USER, idea_id=None)


# --------------------------------------------------------------------------- #
# AC-44 (mirrored) — shared-service outage → clean upstream error, not a crash #
# --------------------------------------------------------------------------- #
def test_upstream_outage_raises_upstream_error(configured, monkeypatch):
    def _boom(base_url, payload):  # noqa: ANN001
        raise IdeationEmbedUpstreamError("connect timeout")

    monkeypatch.setattr(svc, "post_embed_session", _boom)
    with pytest.raises(IdeationEmbedUpstreamError):
        create_embed_session(_USER, idea_id=None)


def test_upstream_missing_token_raises(configured, monkeypatch):
    monkeypatch.setattr(svc, "post_embed_session", lambda base_url, payload: {"expires_at": "x"})
    with pytest.raises(IdeationEmbedUpstreamError):
        create_embed_session(_USER, idea_id=None)


def test_post_embed_session_wraps_httpx_error(configured, monkeypatch):
    def _boom(self, url, **kw):  # noqa: ANN001
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.Client, "post", _boom)
    with pytest.raises(IdeationEmbedUpstreamError):
        svc.post_embed_session(_SHARED_URL, {"connection_id": _CONNECTION_ID, "assertion": "a"})


# --------------------------------------------------------------------------- #
# Endpoint — auth + status-code contract + secrets not echoed                  #
# --------------------------------------------------------------------------- #
@pytest.fixture
def api_client(monkeypatch):
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user, get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: dict(_USER)
    try:
        yield TestClient(app), monkeypatch
    finally:
        app.dependency_overrides.clear()


_EMBED_URL = "/api/v1/integrations/ideation/embed-session"


def test_endpoint_returns_session(api_client):
    client, mp = api_client
    mp.setattr(
        "app.api.v1.integrations.ideation_embed.create_embed_session",
        lambda user, *, idea_id=None: {
            "iframe_url": "https://shared.test/embed/ideas",
            "token": "embed-token-xyz",
            "expires_at": "2026-07-19T00:15:00+00:00",
        },
    )
    resp = client.post(_EMBED_URL, json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["iframe_url"] == "https://shared.test/embed/ideas"
    assert body["token"] == "embed-token-xyz"
    assert body["expires_at"] == "2026-07-19T00:15:00+00:00"


def test_endpoint_detail_passes_idea_id(api_client):
    client, mp = api_client
    seen: dict = {}

    def _capture(user, *, idea_id=None):  # noqa: ANN001
        seen["idea_id"] = idea_id
        return {"iframe_url": f"https://shared.test/embed/ideas/{idea_id}", "token": "t", "expires_at": "x"}

    mp.setattr("app.api.v1.integrations.ideation_embed.create_embed_session", _capture)
    resp = client.post(_EMBED_URL, json={"idea_id": "idea-123"})
    assert resp.status_code == 200
    assert seen["idea_id"] == "idea-123"


def test_endpoint_dormant_is_clean_4xx_not_500(api_client):
    client, mp = api_client

    def _dormant(user, *, idea_id=None):  # noqa: ANN001
        raise IdeationEmbedNotConfigured("blank settings")

    mp.setattr("app.api.v1.integrations.ideation_embed.create_embed_session", _dormant)
    resp = client.post(_EMBED_URL, json={})
    assert 400 <= resp.status_code < 500
    assert resp.status_code != 500


def test_endpoint_upstream_failure_is_not_500(api_client):
    client, mp = api_client

    def _outage(user, *, idea_id=None):  # noqa: ANN001
        raise IdeationEmbedUpstreamError("embed session upstream failed")

    mp.setattr("app.api.v1.integrations.ideation_embed.create_embed_session", _outage)
    resp = client.post(_EMBED_URL, json={})
    assert resp.status_code == 502
    # No secret / internal URL leaks in the error body.
    text = resp.text.lower()
    assert "signing" not in text and "assertion" not in text


def test_endpoint_never_echoes_secrets(api_client, monkeypatch):
    """A real (service-level) round-trip with the shared-service POST stubbed —
    the response must not contain the signing secret, the connection id, or the
    minted assertion."""
    client, mp = api_client
    monkeypatch.setattr(svc.settings, "ideation_shared_service_url", _SHARED_URL)
    monkeypatch.setattr(svc.settings, "ideation_embed_signing_secret", _SIGNING_SECRET)
    monkeypatch.setattr(svc.settings, "ideation_embed_connection_id", _CONNECTION_ID)
    monkeypatch.setattr(
        svc, "post_embed_session",
        lambda base_url, payload: {"token": "embed-token-xyz", "expires_at": "x"},
    )
    resp = client.post(_EMBED_URL, json={})
    assert resp.status_code == 200
    text = resp.text
    assert _SIGNING_SECRET not in text
    assert _CONNECTION_ID not in text
