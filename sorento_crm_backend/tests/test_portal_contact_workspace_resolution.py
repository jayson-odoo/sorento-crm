"""Portal contact resolution is scoped to the workspace the caller names.

A Respond.io contact id is unique per workspace, not globally: two workspaces can
each hold a contact with the same `respond_io_id`. Every portal entry point that
takes (contact_id, space_id) must resolve the contact INSIDE that workspace, and
an id it cannot pin to exactly one row must be refused rather than resolved to
whichever row the database happens to return first.
"""
from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy.orm import Session

# MUST be first app import - resolves circular-import in app.modules.runtime.guards.
from app.main import app  # noqa: E402,F401

from app.database import SessionLocal
from app.models.access import RespondContact
from app.models.portal import PortalOtpCode, PortalToken
from app.models.respond_workspace import RespondWorkspace
from app.services.error_handler import AppException
from app.services.portal_service import PortalService, _hash_otp, _utcnow


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


def _contact(db, cleanup, *, respond_io_id: str, workspace_id=None) -> RespondContact:
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6011{uuid.uuid4().hex[:8]}",
        name="Tester",
        respond_io_id=respond_io_id,
        workspace_id=workspace_id,
    )
    db.add(c)
    db.flush()
    cleanup["contacts"].append(c.id)
    return c


@pytest.fixture
def twins(db, cleanup):
    """Two workspaces, each holding a contact with the SAME Respond.io id."""
    rid = f"rio_{uuid.uuid4().hex[:8]}"
    ws_a = _workspace(db, cleanup)
    ws_b = _workspace(db, cleanup)
    a = _contact(db, cleanup, respond_io_id=rid, workspace_id=ws_a.id)
    b = _contact(db, cleanup, respond_io_id=rid, workspace_id=ws_b.id)
    db.commit()
    return rid, ws_a, ws_b, a, b


def test_mint_token_resolves_contact_in_named_workspace(db, twins):
    rid, ws_a, ws_b, a, b = twins
    svc = PortalService(db)

    tok_b = svc.mint_token(rid, ws_b.space_id)
    tok_a = svc.mint_token(rid, ws_a.space_id)

    assert tok_b.contact_id == b.id
    assert tok_a.contact_id == a.id


def test_get_or_mint_token_resolves_contact_in_named_workspace(db, twins):
    rid, ws_a, ws_b, a, b = twins
    svc = PortalService(db)

    tok_b, _ = svc.get_or_mint_token(rid, ws_b.space_id)
    tok_a, _ = svc.get_or_mint_token(rid, ws_a.space_id)

    assert tok_b.contact_id == b.id
    assert tok_a.contact_id == a.id


def test_unknown_workspace_is_refused(db, twins, cleanup):
    rid, *_ = twins
    other = _workspace(db, cleanup)
    db.commit()
    with pytest.raises(AppException) as exc:
        PortalService(db).mint_token(rid, other.space_id)
    assert exc.value.status_code == 404


def test_request_otp_goes_to_contact_in_named_workspace(db, twins, monkeypatch):
    rid, ws_a, ws_b, a, b = twins
    svc = PortalService(db)
    seen = {}

    def _fake_dispatch(contact, space_id, template, task):
        seen["contact_id"] = contact.id
        return PortalOtpCode(
            contact_id=contact.id,
            space_id=space_id,
            code_hash=_hash_otp("000000"),
            expires_at=_utcnow() + datetime.timedelta(minutes=10),
        )

    monkeypatch.setattr(svc, "create_and_dispatch_otp", _fake_dispatch)
    svc.request_otp(rid, ws_b.space_id)
    assert seen["contact_id"] == b.id


def test_verify_otp_checks_code_of_contact_in_named_workspace(db, twins):
    """A code issued to B (workspace B) is verified against B only: the same
    Respond.io id under workspace A has no outstanding code."""
    rid, ws_a, ws_b, a, b = twins
    db.add(
        PortalOtpCode(
            contact_id=b.id,
            space_id=ws_b.space_id,
            code_hash=_hash_otp("424242"),
            expires_at=_utcnow() + datetime.timedelta(minutes=10),
        )
    )
    db.commit()
    svc = PortalService(db)

    with pytest.raises(AppException):
        svc.verify_otp(rid, ws_a.space_id, "424242")

    token = svc.verify_otp(rid, ws_b.space_id, "424242")
    assert token.contact_id == b.id


def test_ambiguous_id_without_workspace_is_refused(db, twins):
    """submission_link carries no workspace: an id two workspaces share links nowhere."""
    rid, *_ = twins
    assert PortalService(db).submission_link(rid, "complaint", str(uuid.uuid4())) is None


def test_internal_id_still_resolves(db, twins):
    rid, ws_a, ws_b, a, b = twins
    tok = PortalService(db).mint_token(b.id, ws_b.space_id)
    assert tok.contact_id == b.id


def test_unique_id_with_null_workspace_still_resolves(db, cleanup):
    """A contact not yet assigned to a workspace keeps working for its only id."""
    rid = f"rio_{uuid.uuid4().hex[:8]}"
    ws = _workspace(db, cleanup)
    c = _contact(db, cleanup, respond_io_id=rid, workspace_id=None)
    db.commit()
    tok = PortalService(db).mint_token(rid, ws.space_id)
    assert tok.contact_id == c.id


def test_respond_inbox_url_refuses_id_outside_named_workspace(db, twins, cleanup, monkeypatch):
    rid, ws_a, ws_b, a, b = twins
    from app.config import settings

    monkeypatch.setattr(settings, "respond_app_base_url", "https://app.respond.io")
    url = PortalService(db)._build_respond_inbox_url(rid, ws_b.space_id)
    assert url == f"https://app.respond.io/space/{ws_b.space_id}/inbox/{rid}"
    other = _workspace(db, cleanup)
    db.commit()
    assert PortalService(db)._build_respond_inbox_url(rid, other.space_id) is None
