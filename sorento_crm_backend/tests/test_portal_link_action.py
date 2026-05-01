"""Tests for PortalService reuse logic + send-link-via-respond-io flow."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

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
