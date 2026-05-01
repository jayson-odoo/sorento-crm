"""End-to-end tests for the portal OTP -> /me flow.

Goal: prove the post-verify redirect bug is NOT a backend issue. Specifically,
that a token returned by ``POST /verify-otp`` immediately authorizes
``GET /me`` (no race / no encoding mismatch).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import — resolves circular-import in app.modules.runtime.guards.
from app.main import app  # noqa: E402

from app.database import SessionLocal
from app.models.access import RespondContact
from app.models.portal import PortalOtpCode, PortalToken
from app.models.respond_workspace import RespondWorkspace
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
    state = {"tokens": [], "otps": [], "contacts": [], "workspaces": []}
    yield state
    if state["tokens"]:
        db.query(PortalToken).filter(PortalToken.id.in_(state["tokens"])).delete(
            synchronize_session=False
        )
    if state["otps"]:
        db.query(PortalOtpCode).filter(PortalOtpCode.id.in_(state["otps"])).delete(
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


def _contact(db, cleanup, *, workspace_id=None) -> RespondContact:
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6011{uuid.uuid4().hex[:8]}",
        name="Tester",
        respond_io_id=f"rio_{uuid.uuid4().hex[:6]}",
        workspace_id=workspace_id,
    )
    db.add(c)
    db.flush()
    cleanup["contacts"].append(c.id)
    return c


@pytest.fixture
def client(db):
    """Public portal endpoints don't need auth — just override get_db so the
    route handler sees the same session as the test fixture (so flushes/commits
    are visible).
    """
    from app.dependencies import get_db

    def _override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def test_verify_otp_then_me_succeeds(client, db, cleanup):
    """Mint OTP, exchange via /verify-otp, then immediately call /me with the
    returned token. Must succeed — confirms BE has no race / encoding issue
    between mint_token and resolve_token.
    """
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)

    # Seed a fresh, unconsumed OTP directly so we don't depend on Respond.io.
    code = "123456"
    otp = PortalOtpCode(
        contact_id=contact.id,
        space_id=ws.space_id,
        code_hash=_hash_otp(code),
        expires_at=_utcnow() + __import__("datetime").timedelta(minutes=10),
    )
    db.add(otp)
    db.commit()
    cleanup["otps"].append(otp.id)

    # Exchange OTP -> token
    res = client.post(
        "/api/v1/public/portal/verify-otp",
        json={
            "contact_id": contact.id,
            "space_id": ws.space_id,
            "code": code,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    token = body["token"]
    assert token

    for tok in db.query(PortalToken).filter(PortalToken.contact_id == contact.id).all():
        if tok.id not in cleanup["tokens"]:
            cleanup["tokens"].append(tok.id)

    # Immediately call /me with the freshly minted token via X-Portal-Token.
    me = client.get(
        "/api/v1/public/portal/me",
        headers={"X-Portal-Token": token},
    )
    assert me.status_code == 200, me.text
    me_body = me.json()
    assert me_body["contact_id"] == contact.id
    assert me_body["space_id"] == ws.space_id


def test_verify_otp_token_is_resolvable_by_service(db, cleanup):
    """Direct service-level proof: verify_otp returns a row that resolve_token
    accepts when looked up by its ``token`` value. Guards against any
    serialization mismatch between what's stored and what's returned.
    """
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)

    code = "654321"
    otp = PortalOtpCode(
        contact_id=contact.id,
        space_id=ws.space_id,
        code_hash=_hash_otp(code),
        expires_at=_utcnow() + __import__("datetime").timedelta(minutes=10),
    )
    db.add(otp)
    db.commit()
    cleanup["otps"].append(otp.id)

    svc = PortalService(db)
    minted = svc.verify_otp(contact.id, ws.space_id, code)
    cleanup["tokens"].append(minted.id)

    # Round-trip through the same exact string the route handler returns.
    resolved = svc.resolve_token(minted.token)
    assert resolved.id == minted.id
    assert resolved.contact_id == contact.id
    assert resolved.space_id == ws.space_id
