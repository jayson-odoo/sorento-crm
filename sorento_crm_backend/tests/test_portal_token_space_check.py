"""A portal token or contact id is refused when its space_id is not the contact's workspace.

Follow-up to #2028. An internal contact id used to resolve whatever space_id the
caller passed, so a token could be minted (or used) under a workspace the contact
does not belong to. Owner decision on the evidence (prod backup 28 Oct: every live
token matches its contact's workspace; the one mismatch is revoked and expired):
refuse through the existing error paths. A contact with no workspace yet keeps
resolving, as #2028 left it.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

# MUST be first app import - resolves circular-import in app.modules.runtime.guards.
from app.main import app  # noqa: E402,F401

from app.database import SessionLocal
from app.models.access import RespondContact
from app.models.portal import PortalOtpCode, PortalToken
from app.models.respond_workspace import RespondWorkspace
from app.services.error_handler import AppException
from app.services.portal_service import PortalAuthError, PortalService, _utcnow


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
    state = {"contacts": [], "workspaces": []}
    yield state
    db.rollback()
    if state["contacts"]:
        db.query(PortalToken).filter(PortalToken.contact_id.in_(state["contacts"])).delete(
            synchronize_session=False
        )
        db.query(PortalOtpCode).filter(PortalOtpCode.contact_id.in_(state["contacts"])).delete(
            synchronize_session=False
        )
        db.query(RespondContact).filter(RespondContact.id.in_(state["contacts"])).delete(
            synchronize_session=False
        )
    if state["workspaces"]:
        db.query(RespondWorkspace).filter(RespondWorkspace.id.in_(state["workspaces"])).delete(
            synchronize_session=False
        )
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


def _contact(db, cleanup, workspace_id=None) -> RespondContact:
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6011{uuid.uuid4().hex[:8]}",
        name="Tester",
        respond_io_id=f"rio_{uuid.uuid4().hex[:8]}",
        workspace_id=workspace_id,
    )
    db.add(c)
    db.flush()
    cleanup["contacts"].append(c.id)
    return c


@pytest.fixture
def setup(db, cleanup):
    home = _workspace(db, cleanup)
    other = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=home.id)
    db.commit()
    return home, other, contact


def _token_row(db, contact, space_id) -> PortalToken:
    """A live, OTP-verified token, written directly (as an old row would sit)."""
    row = PortalToken(
        token=uuid.uuid4().hex + uuid.uuid4().hex,
        contact_id=contact.id,
        space_id=space_id,
        expires_at=_utcnow() + timedelta(days=5),
        verified_at=_utcnow(),
    )
    db.add(row)
    db.commit()
    return row


def test_internal_id_in_its_own_workspace_mints(db, setup):
    home, other, contact = setup
    tok = PortalService(db).mint_token(contact.id, home.space_id)
    assert tok.contact_id == contact.id


def test_internal_id_with_another_workspace_is_refused(db, setup):
    home, other, contact = setup
    with pytest.raises(AppException):
        PortalService(db).mint_token(contact.id, other.space_id)


def test_internal_id_with_unknown_space_is_refused(db, setup):
    home, other, contact = setup
    with pytest.raises(AppException):
        PortalService(db).get_or_mint_token(contact.id, "sp_does_not_exist")


def test_request_otp_with_another_workspace_is_refused(db, setup, monkeypatch):
    home, other, contact = setup
    svc = PortalService(db)
    monkeypatch.setattr(svc, "create_and_dispatch_otp", lambda *a, **k: pytest.fail("dispatched"))
    with pytest.raises(AppException):
        svc.request_otp(contact.id, other.space_id)


def test_contact_without_workspace_still_resolves_by_internal_id(db, cleanup):
    contact = _contact(db, cleanup, workspace_id=None)
    db.commit()
    tok = PortalService(db).mint_token(contact.id, "sp_anything")
    assert tok.contact_id == contact.id


def test_token_in_contacts_workspace_resolves(db, setup):
    home, other, contact = setup
    row = _token_row(db, contact, home.space_id)
    assert PortalService(db).resolve_token(row.token).id == row.id


def test_token_with_another_workspace_is_refused(db, setup):
    home, other, contact = setup
    row = _token_row(db, contact, other.space_id)
    with pytest.raises(PortalAuthError):
        PortalService(db).resolve_token(row.token)


def test_token_of_contact_without_workspace_still_resolves(db, cleanup):
    contact = _contact(db, cleanup, workspace_id=None)
    db.commit()
    row = _token_row(db, contact, "sp_anything")
    assert PortalService(db).resolve_token(row.token).id == row.id


def test_slug_info_names_the_contacts_workspace_over_a_stale_token(db, setup):
    """The verify page OTPs with the space slug_info returns: a stale latest token
    must not hand it a space the stricter check now refuses."""
    home, other, contact = setup
    _token_row(db, contact, other.space_id)
    slug = PortalService(db).get_or_create_slug(contact)
    assert PortalService(db).slug_info(slug)["space_id"] == home.space_id


def test_token_info_names_the_contacts_workspace(db, setup):
    """The verify page recovers (contact_id, space_id) from token-info and OTPs with
    it: a stale token space must not be echoed back, or the OTP request 404s."""
    from fastapi.testclient import TestClient

    home, other, contact = setup
    row = _token_row(db, contact, other.space_id)
    res = TestClient(app).get("/api/v1/public/portal/token-info", params={"token": row.token})
    assert res.status_code == 200, res.text
    assert res.json()["space_id"] == home.space_id
