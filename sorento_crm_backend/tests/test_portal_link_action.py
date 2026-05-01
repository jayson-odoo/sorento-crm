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
