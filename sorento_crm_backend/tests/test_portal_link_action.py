"""Tests for PortalService reuse logic + send-link-via-respond-io flow."""
from __future__ import annotations

import re

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import — resolves circular-import in app.modules.runtime.guards
# (app.models.__init__ → app.modules.runtime.guards → app.dependencies during partial init).
from app.main import app  # noqa: E402

from app.database import SessionLocal
from app.models.access import RespondContact
from app.models.portal import PortalToken
from app.models.respond_workspace import RespondWorkspace
from app.services.portal_service import PortalService, _utcnow


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def cleanup(db):
    state = {"tokens": [], "contacts": [], "workspaces": []}
    yield state
    if state["tokens"]:
        db.query(PortalToken).filter(PortalToken.id.in_(state["tokens"])).delete(
            synchronize_session=False
        )
    if state["contacts"]:
        db.query(RespondContact).filter(
            RespondContact.id.in_(state["contacts"])
        ).delete(synchronize_session=False)
    if state["workspaces"]:
        db.query(RespondWorkspace).filter(
            RespondWorkspace.id.in_(state["workspaces"])
        ).delete(synchronize_session=False)
    db.commit()


def _workspace(db, cleanup) -> RespondWorkspace:
    w = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=f"sp_{uuid.uuid4().hex[:8]}",
        name="Test WS",
        api_key_ciphertext="test-cipher",
    )
    db.add(w)
    db.flush()
    cleanup["workspaces"].append(w.id)
    return w


def _contact(db, cleanup, *, workspace_id=None, respond_io_id=None) -> RespondContact:
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6011{uuid.uuid4().hex[:8]}",
        name="Tester",
        respond_io_id=respond_io_id or f"rio_{uuid.uuid4().hex[:6]}",
        workspace_id=workspace_id,
    )
    db.add(c)
    db.flush()
    cleanup["contacts"].append(c.id)
    return c


def _track_minted(cleanup, token: PortalToken) -> PortalToken:
    cleanup["tokens"].append(token.id)
    return token


def test_get_or_mint_token_mints_when_no_token(db, cleanup):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    svc = PortalService(db)
    token, reused = svc.get_or_mint_token(contact.id, ws.space_id)
    _track_minted(cleanup, token)

    assert reused is False
    assert token.contact_id == contact.id
    assert token.space_id == ws.space_id


def test_get_or_mint_token_reuses_live_token(db, cleanup):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    svc = PortalService(db)
    first, first_reused = svc.get_or_mint_token(contact.id, ws.space_id)
    _track_minted(cleanup, first)
    second, reused = svc.get_or_mint_token(contact.id, ws.space_id)

    assert first_reused is False
    assert reused is True
    assert second.token == first.token
    assert second.id == first.id


def test_get_or_mint_token_mints_new_when_only_expired(db, cleanup):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    expired = PortalToken(
        id=str(uuid.uuid4()),
        token=f"expired-tok-{uuid.uuid4().hex[:8]}",
        contact_id=contact.id,
        space_id=ws.space_id,
        expires_at=_utcnow() - timedelta(hours=1),
    )
    db.add(expired)
    db.commit()
    cleanup["tokens"].append(expired.id)

    svc = PortalService(db)
    new_token, reused = svc.get_or_mint_token(contact.id, ws.space_id)
    _track_minted(cleanup, new_token)

    assert reused is False
    assert new_token.token != expired.token
    assert new_token.id != expired.id


def test_get_or_mint_token_mints_new_when_revoked(db, cleanup):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    revoked = PortalToken(
        id=str(uuid.uuid4()),
        token=f"revoked-tok-{uuid.uuid4().hex[:8]}",
        contact_id=contact.id,
        space_id=ws.space_id,
        expires_at=_utcnow() + timedelta(days=5),
        revoked_at=_utcnow(),
    )
    db.add(revoked)
    db.commit()
    cleanup["tokens"].append(revoked.id)

    svc = PortalService(db)
    new_token, reused = svc.get_or_mint_token(contact.id, ws.space_id)
    _track_minted(cleanup, new_token)

    assert reused is False
    assert new_token.token != revoked.token
    assert new_token.id != revoked.id


# ---------- send_link_via_respond_io ----------


def test_send_link_via_respond_io_success(db, cleanup, monkeypatch):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    captured = {}

    def fake_send(self, identifier, text):
        captured["identifier"] = identifier
        captured["text"] = text
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.portal_service.RespondClient.send_message",
        fake_send,
    )

    svc = PortalService(db)
    result = svc.send_link_via_respond_io(contact.id, ws.space_id)

    # Track all live tokens for this contact for teardown
    for tok in (
        db.query(PortalToken).filter(PortalToken.contact_id == contact.id).all()
    ):
        if tok.id not in cleanup["tokens"]:
            cleanup["tokens"].append(tok.id)

    assert result["sent"] is True
    assert result["reused"] is False
    assert result["portal_url"]
    assert captured["identifier"] == contact.respond_io_id
    assert "portal" in captured["text"].lower()
    assert result["portal_url"] in captured["text"]


def test_send_link_via_respond_io_reuses_token(db, cleanup, monkeypatch):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    monkeypatch.setattr(
        "app.services.portal_service.RespondClient.send_message",
        lambda self, identifier, text: {"ok": True},
    )

    svc = PortalService(db)
    first = svc.send_link_via_respond_io(contact.id, ws.space_id)
    second = svc.send_link_via_respond_io(contact.id, ws.space_id)

    for tok in (
        db.query(PortalToken).filter(PortalToken.contact_id == contact.id).all()
    ):
        if tok.id not in cleanup["tokens"]:
            cleanup["tokens"].append(tok.id)

    assert first["portal_url"] == second["portal_url"]
    assert first["reused"] is False
    assert second["reused"] is True


def test_send_link_propagates_respond_io_failure(db, cleanup, monkeypatch):
    import httpx

    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    def boom(self, identifier, text):
        request = httpx.Request("POST", "https://api.respond.io/v2/contact/x/message")
        response = httpx.Response(500, request=request, text="upstream blew up")
        raise httpx.HTTPStatusError("500", request=request, response=response)

    monkeypatch.setattr(
        "app.services.portal_service.RespondClient.send_message", boom
    )

    svc = PortalService(db)
    with pytest.raises(httpx.HTTPStatusError):
        svc.send_link_via_respond_io(contact.id, ws.space_id)

    # Track minted tokens for teardown (the mint happened before send failed)
    for tok in (
        db.query(PortalToken).filter(PortalToken.contact_id == contact.id).all()
    ):
        if tok.id not in cleanup["tokens"]:
            cleanup["tokens"].append(tok.id)

    # token still minted (so /portal-link itself remains usable)
    assert (
        db.query(PortalToken)
        .filter(
            PortalToken.contact_id == contact.id,
            PortalToken.revoked_at.is_(None),
        )
        .count()
        == 1
    )


# ---------- HTTP endpoint tests ----------
# We don't have a project-wide TestClient with auth helpers, so we build one
# inline: dependency_overrides for get_current_user + get_db, plus a monkeypatch
# on UserPermissionService.check_user_has_permission for the per-test allow/deny.


@pytest.fixture
def client(db, monkeypatch):
    """TestClient that:
    - injects a stub current user
    - reuses the live Postgres session (so test setup writes are visible to routes)
    - defaults UserPermissionService.check_user_has_permission to True
      (each test can monkeypatch.setattr again to flip it).
    """
    from app.dependencies import get_current_user, get_db

    stub_user = {"id": str(uuid.uuid4()), "email": "portal-test@test"}

    def _override_user():
        return stub_user

    def _override_db():
        # Reuse the same session as the test fixture so flushes/commits are
        # visible to the route handler. We do NOT close it here; the `db`
        # fixture owns that.
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db

    # Default to allowing the permission. Individual tests can override.
    monkeypatch.setattr(
        "app.services.user_service.UserPermissionService.check_user_has_permission",
        lambda self, user_id, slug: True,
    )

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


def test_portal_link_endpoint_requires_permission(client, db, cleanup, monkeypatch):
    monkeypatch.setattr(
        "app.services.user_service.UserPermissionService.check_user_has_permission",
        lambda self, user_id, slug: False,
    )
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    res = client.post(f"/api/v1/user-management/contacts/{contact.id}/portal-link")
    assert res.status_code == 403


def test_portal_link_endpoint_returns_url(client, db, cleanup):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    res = client.post(f"/api/v1/user-management/contacts/{contact.id}/portal-link")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["token"]
    # Durable slug URL: /portal/c/{slug}?token={token} — slug half stays a
    # bookmarkable re-entry point after the token half expires.
    assert re.search(
        rf"/portal/c/[0-9A-Z]{{10}}\?token={body['token']}$", body["portal_url"]
    ), body["portal_url"]
    assert body["reused"] is False

    # Track minted token for teardown.
    for tok in db.query(PortalToken).filter(PortalToken.contact_id == contact.id).all():
        if tok.id not in cleanup["tokens"]:
            cleanup["tokens"].append(tok.id)


def test_portal_link_endpoint_reuses_on_second_call(client, db, cleanup):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    first = client.post(
        f"/api/v1/user-management/contacts/{contact.id}/portal-link"
    ).json()
    second = client.post(
        f"/api/v1/user-management/contacts/{contact.id}/portal-link"
    ).json()

    for tok in db.query(PortalToken).filter(PortalToken.contact_id == contact.id).all():
        if tok.id not in cleanup["tokens"]:
            cleanup["tokens"].append(tok.id)

    assert first["token"] == second["token"]
    assert first["reused"] is False
    assert second["reused"] is True


def test_portal_link_endpoint_404_unknown_contact(client):
    res = client.post(
        "/api/v1/user-management/contacts/does-not-exist/portal-link"
    )
    assert res.status_code == 404


def test_portal_link_endpoint_422_when_no_workspace(client, db, cleanup):
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6019{uuid.uuid4().hex[:8]}",
        name="Orphan",
        respond_io_id=f"rio_{uuid.uuid4().hex[:6]}",
        workspace_id=None,
    )
    db.add(c)
    db.commit()
    cleanup["contacts"].append(c.id)

    res = client.post(f"/api/v1/user-management/contacts/{c.id}/portal-link")
    assert res.status_code == 422, res.text
    body = res.json()
    detail = body.get("detail")
    # detail may be a string or structured; coerce to string and lowercase.
    assert "workspace" in str(detail).lower()


# ---------- POST /portal-link/send endpoint ----------


def test_portal_link_send_endpoint_success(client, db, cleanup, monkeypatch):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    monkeypatch.setattr(
        "app.services.portal_service.RespondClient.send_message",
        lambda self, identifier, text: {"ok": True},
    )

    res = client.post(
        f"/api/v1/user-management/contacts/{contact.id}/portal-link/send"
    )

    # Track minted token(s) for teardown.
    for tok in db.query(PortalToken).filter(PortalToken.contact_id == contact.id).all():
        if tok.id not in cleanup["tokens"]:
            cleanup["tokens"].append(tok.id)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["sent"] is True
    assert body["portal_url"]
    assert body["reused"] is False


def test_portal_link_send_endpoint_422_no_respond_io_id(client, db, cleanup):
    ws = _workspace(db, cleanup)
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6012{uuid.uuid4().hex[:8]}",
        name="No RIO",
        respond_io_id=None,
        workspace_id=ws.id,
    )
    db.add(c)
    db.commit()
    cleanup["contacts"].append(c.id)

    res = client.post(
        f"/api/v1/user-management/contacts/{c.id}/portal-link/send"
    )
    assert res.status_code == 422, res.text
    body = res.json()
    detail = body.get("detail")
    assert "respond.io" in str(detail).lower()


def test_portal_link_send_endpoint_502_on_upstream_failure(
    client, db, cleanup, monkeypatch
):
    import httpx

    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    def boom(self, identifier, text):
        request = httpx.Request("POST", "https://api.respond.io/x")
        response = httpx.Response(500, request=request, text="upstream blew up")
        raise httpx.HTTPStatusError("500", request=request, response=response)

    monkeypatch.setattr(
        "app.services.portal_service.RespondClient.send_message", boom
    )

    res = client.post(
        f"/api/v1/user-management/contacts/{contact.id}/portal-link/send"
    )

    # Track minted token(s) for teardown (mint happens before send fails).
    for tok in db.query(PortalToken).filter(PortalToken.contact_id == contact.id).all():
        if tok.id not in cleanup["tokens"]:
            cleanup["tokens"].append(tok.id)

    assert res.status_code == 502, res.text


def test_portal_link_send_endpoint_504_on_upstream_timeout(client, db, cleanup, monkeypatch):
    import httpx as _httpx

    def _timeout(self, identifier, text):
        raise _httpx.ReadTimeout("upstream slow")

    monkeypatch.setattr(
        "app.services.portal_service.RespondClient.send_message", _timeout
    )
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    res = client.post(
        f"/api/v1/user-management/contacts/{contact.id}/portal-link/send"
    )
    for tok in db.query(PortalToken).filter_by(contact_id=contact.id).all():
        cleanup["tokens"].append(tok.id)
    assert res.status_code == 504
    assert "timed out" in res.json()["detail"].lower()


def test_portal_link_send_endpoint_502_on_network_error(client, db, cleanup, monkeypatch):
    import httpx as _httpx

    def _connect_err(self, identifier, text):
        raise _httpx.ConnectError("dns fail")

    monkeypatch.setattr(
        "app.services.portal_service.RespondClient.send_message", _connect_err
    )
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    res = client.post(
        f"/api/v1/user-management/contacts/{contact.id}/portal-link/send"
    )
    for tok in db.query(PortalToken).filter_by(contact_id=contact.id).all():
        cleanup["tokens"].append(tok.id)
    assert res.status_code == 502
    assert "unreachable" in res.json()["detail"].lower()


def test_portal_link_send_endpoint_503_when_api_key_missing(client, db, cleanup, monkeypatch):
    def _no_key(self, identifier, text):
        raise ValueError("Respond API key is not configured.")

    monkeypatch.setattr(
        "app.services.portal_service.RespondClient.send_message", _no_key
    )
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    res = client.post(
        f"/api/v1/user-management/contacts/{contact.id}/portal-link/send"
    )
    for tok in db.query(PortalToken).filter_by(contact_id=contact.id).all():
        cleanup["tokens"].append(tok.id)
    assert res.status_code == 503
    assert "respond api key" in res.json()["detail"].lower()


def test_portal_link_endpoint_falls_back_to_request_base_url(client, db, cleanup, monkeypatch):
    """When frontend_base_url is unset, response uses scheme://host from the request."""
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "frontend_base_url", None, raising=False)
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    db.commit()

    res = client.post(f"/api/v1/user-management/contacts/{contact.id}/portal-link")
    body = res.json()
    for tok in db.query(PortalToken).filter_by(contact_id=contact.id).all():
        cleanup["tokens"].append(tok.id)
    assert res.status_code == 200
    # TestClient base URL is http://testserver/
    assert body["portal_url"].startswith("http"), f"expected absolute URL, got {body['portal_url']}"
    # Durable slug URL: /portal/c/{slug}?token={token} — slug half stays a
    # bookmarkable re-entry point after the token half expires.
    assert re.search(
        rf"/portal/c/[0-9A-Z]{{10}}\?token={body['token']}$", body["portal_url"]
    ), body["portal_url"]
