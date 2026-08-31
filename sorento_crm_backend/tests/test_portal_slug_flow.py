"""Tests for bookmarkable portal links + device trust.

Covers:
- slug lazy mint (idempotent, unique)
- GET /slug-info/{slug} (200 shape, 404 unknown, masked phone)
- POST /logout (revokes, idempotent, bad token tolerated)
- sliding 30-day TTL on verified tokens; impersonation tokens excluded
- OTP daily cap (10/contact/24h)
- build_portal_url emits the /portal/c/{slug}?token= shape
- /me returns portal_slug
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves circular-import in app.modules.runtime.guards.
from app.main import app  # noqa: E402

from app.database import SessionLocal
from app.models.access import RespondContact
from app.models.portal import PortalOtpCode, PortalToken
from app.models.respond_workspace import RespondWorkspace
from app.services.portal_service import (
    OTP_DAILY_CAP,
    PORTAL_VERIFIED_TOKEN_TTL,
    PortalService,
    _utcnow,
)


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


def _workspace(db, cleanup, *, whatsapp: str | None = None) -> RespondWorkspace:
    w = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=f"sp_{uuid.uuid4().hex[:8]}",
        name="Test WS",
        api_key_ciphertext="test-cipher",
        whatsapp_number=whatsapp,
    )
    db.add(w)
    db.flush()
    cleanup["workspaces"].append(w.id)
    return w


def _contact(db, cleanup, *, workspace_id=None) -> RespondContact:
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6011{int(uuid.uuid4().int % 10**8):08d}",
        name="Tester",
        respond_io_id=f"rio_{uuid.uuid4().hex[:6]}",
        workspace_id=workspace_id,
    )
    db.add(c)
    db.flush()
    cleanup["contacts"].append(c.id)
    return c


def _track_tokens(db, cleanup, contact_id):
    for tok in (
        db.query(PortalToken).filter(PortalToken.contact_id == contact_id).all()
    ):
        if tok.id not in cleanup["tokens"]:
            cleanup["tokens"].append(tok.id)


def _track_otps(db, cleanup, contact_id):
    for o in (
        db.query(PortalOtpCode).filter(PortalOtpCode.contact_id == contact_id).all()
    ):
        if o.id not in cleanup["otps"]:
            cleanup["otps"].append(o.id)


@pytest.fixture
def client(db):
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


# ---------- slug mint ----------


def test_slug_lazy_mint_idempotent(db, cleanup):
    contact = _contact(db, cleanup)
    svc = PortalService(db)
    slug1 = svc.get_or_create_slug(contact)
    slug2 = svc.get_or_create_slug(contact)
    assert slug1 == slug2
    assert len(slug1) == 10
    # Crockford alphabet only (no I, L, O, U)
    assert all(ch in "0123456789ABCDEFGHJKMNPQRSTVWXYZ" for ch in slug1)


def test_mint_token_mints_slug(db, cleanup):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    svc = PortalService(db)
    svc.mint_token(contact.id, ws.space_id)
    _track_tokens(db, cleanup, contact.id)
    db.refresh(contact)
    assert contact.portal_slug


# ---------- slug-info endpoint ----------


def test_slug_info_known(client, db, cleanup):
    ws = _workspace(db, cleanup, whatsapp="60123456789")
    contact = _contact(db, cleanup, workspace_id=ws.id)
    slug = PortalService(db).get_or_create_slug(contact)
    res = client.get(f"/api/v1/public/portal/slug-info/{slug}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["contact_id"] == contact.id
    assert body["whatsapp_number"] == "60123456789"
    # Masked: last 4 digits visible, middle hidden
    digits = "".join(ch for ch in contact.phone_number if ch.isdigit())
    assert body["masked_phone"].endswith(digits[-4:])
    assert digits[2:-4] not in body["masked_phone"]


def test_slug_info_unknown_404(client):
    res = client.get("/api/v1/public/portal/slug-info/ZZZZZZZZZZ")
    assert res.status_code == 404


# ---------- logout ----------


def test_logout_revokes_token(client, db, cleanup):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    svc = PortalService(db)
    token = svc.mint_token(contact.id, ws.space_id)
    _track_tokens(db, cleanup, contact.id)
    res = client.post(
        "/api/v1/public/portal/logout", headers={"X-Portal-Token": token.token}
    )
    assert res.status_code == 204
    db.refresh(token)
    assert token.revoked_at is not None
    # Idempotent + bad token tolerated
    res2 = client.post(
        "/api/v1/public/portal/logout", headers={"X-Portal-Token": token.token}
    )
    assert res2.status_code == 204
    res3 = client.post(
        "/api/v1/public/portal/logout", headers={"X-Portal-Token": "nonsense"}
    )
    assert res3.status_code == 204


# ---------- sliding TTL ----------


def test_verified_token_slides_on_use(db, cleanup):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    svc = PortalService(db)
    token = svc.mint_token(contact.id, ws.space_id)
    _track_tokens(db, cleanup, contact.id)
    token.verified_at = _utcnow()
    token.expires_at = _utcnow() + timedelta(days=3)  # well under threshold
    db.commit()

    resolved = svc.resolve_token(token.token)
    remaining = resolved.expires_at - _utcnow()
    assert remaining > PORTAL_VERIFIED_TOKEN_TTL - timedelta(minutes=5)


def test_fresh_verified_token_not_rebumped(db, cleanup):
    """Within the 29d threshold no write happens (daily throttle)."""
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    svc = PortalService(db)
    token = svc.mint_token(contact.id, ws.space_id)
    _track_tokens(db, cleanup, contact.id)
    token.verified_at = _utcnow()
    fresh_expiry = _utcnow() + PORTAL_VERIFIED_TOKEN_TTL
    token.expires_at = fresh_expiry
    db.commit()

    resolved = svc.resolve_token(token.token)
    assert resolved.expires_at == fresh_expiry


def test_impersonation_token_never_slides(db, cleanup):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    svc = PortalService(db)
    token = svc.mint_token(contact.id, ws.space_id, is_impersonation=True)
    _track_tokens(db, cleanup, contact.id)
    token.verified_at = _utcnow()
    short_expiry = _utcnow() + timedelta(days=3)
    token.expires_at = short_expiry
    db.commit()

    resolved = svc.resolve_token(token.token)
    assert resolved.expires_at == short_expiry


def test_unverified_token_rejected(db, cleanup):
    from app.services.portal_service import PortalAuthError

    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    svc = PortalService(db)
    token = svc.mint_token(contact.id, ws.space_id)
    _track_tokens(db, cleanup, contact.id)
    with pytest.raises(PortalAuthError):
        svc.resolve_token(token.token)


# ---------- OTP daily cap ----------


def test_otp_daily_cap(db, cleanup, monkeypatch):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    svc = PortalService(db)

    # Seed OTP_DAILY_CAP rows inside the window, spaced outside the cooldown.
    now = _utcnow()
    for i in range(OTP_DAILY_CAP):
        db.add(
            PortalOtpCode(
                contact_id=contact.id,
                space_id=ws.space_id,
                code_hash="x" * 64,
                expires_at=now + timedelta(minutes=10),
                created_at=now - timedelta(hours=1, minutes=i * 2),
            )
        )
    db.commit()
    _track_otps(db, cleanup, contact.id)

    from app.services.error_handler import AppException

    with pytest.raises(AppException) as exc:
        svc.request_otp(contact.id, ws.space_id)
    assert "limit" in str(exc.value.detail).lower()


def test_otp_cooldown_precedes_cap(db, cleanup):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    svc = PortalService(db)
    db.add(
        PortalOtpCode(
            contact_id=contact.id,
            space_id=ws.space_id,
            code_hash="x" * 64,
            expires_at=_utcnow() + timedelta(minutes=10),
        )
    )
    db.commit()
    _track_otps(db, cleanup, contact.id)

    from app.services.error_handler import AppException

    with pytest.raises(AppException) as exc:
        svc.request_otp(contact.id, ws.space_id)
    assert "wait" in str(exc.value.detail).lower()


# ---------- portal URL shape ----------


def test_build_portal_url_uses_slug(db, cleanup):
    ws = _workspace(db, cleanup)
    contact = _contact(db, cleanup, workspace_id=ws.id)
    svc = PortalService(db)
    token = svc.mint_token(contact.id, ws.space_id)
    _track_tokens(db, cleanup, contact.id)
    db.refresh(contact)
    url = svc.build_portal_url(token.token, "https://crm.example.com", "stock_inquiry")
    assert url == (
        f"https://crm.example.com/portal/c/{contact.portal_slug}"
        f"?token={token.token}&type=stock_inquiry"
    )


def test_build_portal_url_falls_back_without_row(db):
    svc = PortalService(db)
    url = svc.build_portal_url("NOTAREALTOKEN", "https://crm.example.com")
    assert url == "https://crm.example.com/portal?token=NOTAREALTOKEN"


# ---------- /me + /token-info enrichment ----------


def test_me_returns_portal_slug(client, db, cleanup):
    ws = _workspace(db, cleanup, whatsapp="60123456789")
    contact = _contact(db, cleanup, workspace_id=ws.id)
    svc = PortalService(db)
    token = svc.mint_token(contact.id, ws.space_id)
    _track_tokens(db, cleanup, contact.id)
    token.verified_at = _utcnow()
    db.commit()

    res = client.get(
        "/api/v1/public/portal/me", headers={"X-Portal-Token": token.token}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    db.refresh(contact)
    assert body["portal_slug"] == contact.portal_slug
    assert body["whatsapp_number"] == "60123456789"
    # The landing gates its entry points on this list; response_model would
    # silently drop an undeclared field, so its presence is asserted here.
    # A contact with no access types resolves to nothing (fail-closed).
    assert body["visible_form_types"] == []


def test_token_info_returns_slug_and_mask(client, db, cleanup):
    ws = _workspace(db, cleanup, whatsapp="60123456789")
    contact = _contact(db, cleanup, workspace_id=ws.id)
    svc = PortalService(db)
    token = svc.mint_token(contact.id, ws.space_id)
    _track_tokens(db, cleanup, contact.id)

    res = client.get(f"/api/v1/public/portal/token-info?token={token.token}")
    assert res.status_code == 200, res.text
    body = res.json()
    db.refresh(contact)
    assert body["portal_slug"] == contact.portal_slug
    assert body["masked_phone"]
    assert body["whatsapp_number"] == "60123456789"
