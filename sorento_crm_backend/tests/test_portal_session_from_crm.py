"""SIGNIN-2FA-NOT-ROLE: a CRM sign-in counts as verified for the user's OWN portal contact.

`POST /api/v1/public/portal/session-from-crm`, body `{"slug": "<portal slug>"}`, auth = the CRM
staff Bearer session (opaque `user_sessions` token). Answers `{token, expires_at}` for the
signed-in user's own linked contact (`users.respond_contact_id`) and refuses everything else.

Contract: documentation/plans/identity/signin-2fa-not-role-14nov-acceptance-criteria.md
(AC-2 to AC-6). Postgres only, own seed chain per test on `blank_session()` (CI's database is
empty); every write is discarded at teardown.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves circular-import in app.modules.runtime.guards.
from app.main import app  # noqa: E402

from app.models.access import RespondContact
from app.models.portal import PortalOtpCode, PortalToken
from app.models.respond_workspace import RespondWorkspace
from app.services.portal_service import (
    PORTAL_VERIFIED_TOKEN_TTL,
    PortalService,
    _hash_otp,
    _utcnow,
)
from tests._pg_fixture import blank_session, unique_code

ROUTE = "/api/v1/public/portal/session-from-crm"
ME = "/api/v1/public/portal/me"


# --------------------------------------------------------------------------------------
# fixtures + seeding
# --------------------------------------------------------------------------------------


@pytest.fixture()
def db():
    with blank_session() as s:
        yield s


@pytest.fixture()
def client(db, monkeypatch):
    from app.database import get_db
    from app.models.base import set_company_scope
    from app.services import rate_limit
    from app.services.company_scope_resolver import apply_company_scope

    def _override_db():
        yield db

    def _all_companies():
        set_company_scope(db, None)
        return None

    # Every TestClient request comes from one address; never let real Redis counters bleed.
    monkeypatch.setattr(
        rate_limit, "hit", lambda *a, **k: rate_limit.RateResult(allowed=True)
    )
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[apply_company_scope] = _all_companies
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(apply_company_scope, None)


def _workspace(db) -> RespondWorkspace:
    w = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=f"sp_{uuid.uuid4().hex[:8]}",
        name="ZZT WS",
        api_key_ciphertext="test-cipher",
    )
    db.add(w)
    db.flush()
    return w


def _contact(db, ws: RespondWorkspace, name: str = "ZZT Contact") -> RespondContact:
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6011{uuid.uuid4().int % 10_000_000:07d}",
        name=name,
        respond_io_id=f"rio_{uuid.uuid4().hex[:6]}",
        workspace_id=ws.id,
    )
    db.add(c)
    db.flush()
    return c


def _slug(db, contact: RespondContact) -> str:
    return PortalService(db).get_or_create_slug(contact)


def _user(
    db,
    *,
    contact: RespondContact | None,
    status: str = "ACTIVE",
    is_trashed: bool = False,
    role_slug: str | None = None,
    is_integration: bool = False,
    contact_number: str | None = "same",
):
    from app.models.user import User, UserRole, UserRoleAssignment

    # Fix round 1 S1: the user's own number must still match the linked contact's (the
    # `eligible_user_for_contact` rule), so by default the user carries the contact's number.
    if contact_number == "same":
        contact_number = contact.phone_number if contact else None
    user = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('s2f', alpha=True)}@example.com".lower(),
        name="ZZT Salesperson",
        status=status,
        is_trashed=is_trashed,
        respond_contact_id=contact.id if contact else None,
        is_integration=is_integration,
        contact_number=contact_number,
    )
    db.add(user)
    db.flush()
    role = UserRole(
        id=str(uuid.uuid4()),
        slug=role_slug or unique_code("sales", alpha=True).lower(),
        name=unique_code("Role"),
        is_protected=False,
        is_default=False,
    )
    db.add(role)
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    db.commit()
    return user


def _bearer(db, user, auth_method: str = "password") -> dict:
    from app.services.user_session_service import mint_session

    return {"Authorization": f"Bearer {mint_session(db, str(user.id), auth_method=auth_method).token}"}


def _tokens(db, contact_id: str) -> list[PortalToken]:
    db.expire_all()
    return db.query(PortalToken).filter(PortalToken.contact_id == contact_id).all()


def _otps(db, contact_id: str) -> list[PortalOtpCode]:
    db.expire_all()
    return db.query(PortalOtpCode).filter(PortalOtpCode.contact_id == contact_id).all()


def _near(dt: datetime, target: datetime, *, within: timedelta = timedelta(minutes=2)) -> bool:
    return abs(dt.replace(tzinfo=None) - target) <= within


def _assert_refused_without_token(res, contact_id, db, *, statuses, before=0):
    assert res.status_code in statuses, f"{res.status_code}: {res.text}"
    try:
        body = res.json()
    except ValueError:
        body = {}
    assert not (isinstance(body, dict) and body.get("token")), "a refusal must never carry a token"
    assert len(_tokens(db, contact_id)) == before, "a refusal must not write a portal_tokens row"


# --------------------------------------------------------------------------------------
# AC-2: own contact, signed in -> verified 30-day token, /me answers, no OTP row
# --------------------------------------------------------------------------------------


def test_ac2_own_slug_mints_verified_30_day_token_that_opens_me(client, db):
    ws = _workspace(db)
    contact = _contact(db, ws)
    slug = _slug(db, contact)
    user = _user(db, contact=contact)

    res = client.post(ROUTE, json={"slug": slug}, headers=_bearer(db, user))
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body.get("token"), str) and body["token"]
    assert isinstance(body.get("expires_at"), str) and body["expires_at"]
    # ISO string, about now + 30 days.
    returned_exp = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    assert _near(returned_exp, _utcnow() + PORTAL_VERIFIED_TOKEN_TTL)

    rows = [t for t in _tokens(db, contact.id) if t.token == body["token"]]
    assert len(rows) == 1, "the returned token must be a portal_tokens row for the user's contact"
    row = rows[0]
    assert row.verified_at is not None, "a CRM sign-in counts as verified"
    assert _near(row.verified_at, _utcnow())
    assert _near(row.expires_at, _utcnow() + PORTAL_VERIFIED_TOKEN_TTL)
    assert row.revoked_at is None
    assert not row.is_impersonation
    assert row.space_id == ws.space_id

    me = client.get(ME, headers={"X-Portal-Token": body["token"]})
    assert me.status_code == 200, me.text
    assert me.json()["contact_id"] == contact.id

    assert _otps(db, contact.id) == [], "the bridge never writes a portal_otp_codes row"


# --------------------------------------------------------------------------------------
# AC-3: somebody else's slug
# --------------------------------------------------------------------------------------


def test_ac3_other_contacts_slug_is_403_and_writes_no_token(client, db):
    ws = _workspace(db)
    own = _contact(db, ws, name="ZZT Own")
    other = _contact(db, ws, name="ZZT Other")
    other_slug = _slug(db, other)
    user = _user(db, contact=own)

    res = client.post(ROUTE, json={"slug": other_slug}, headers=_bearer(db, user))
    _assert_refused_without_token(res, other.id, db, statuses={403})
    assert _tokens(db, own.id) == []
    assert _otps(db, other.id) == []


def test_ac3_other_contact_linked_to_another_user_is_403(client, db):
    """The slug belongs to a contact that IS some user's linked contact, just not this one's."""
    ws = _workspace(db)
    own = _contact(db, ws, name="ZZT Own")
    other = _contact(db, ws, name="ZZT Other")
    _user(db, contact=other)
    other_slug = _slug(db, other)
    user = _user(db, contact=own)

    res = client.post(ROUTE, json={"slug": other_slug}, headers=_bearer(db, user))
    _assert_refused_without_token(res, other.id, db, statuses={403})


# --------------------------------------------------------------------------------------
# AC-4: no / invalid session, API key principal, no linked contact, unknown slug
# --------------------------------------------------------------------------------------


def test_ac4_no_bearer_is_401(client, db):
    ws = _workspace(db)
    contact = _contact(db, ws)
    slug = _slug(db, contact)
    _user(db, contact=contact)

    res = client.post(ROUTE, json={"slug": slug})
    _assert_refused_without_token(res, contact.id, db, statuses={401})


def test_ac4_invalid_bearer_is_401(client, db):
    ws = _workspace(db)
    contact = _contact(db, ws)
    slug = _slug(db, contact)
    _user(db, contact=contact)

    res = client.post(
        ROUTE, json={"slug": slug}, headers={"Authorization": f"Bearer not-a-session-{uuid.uuid4().hex}"}
    )
    _assert_refused_without_token(res, contact.id, db, statuses={401})


def test_ac4_api_key_principal_is_403_even_when_act_as_user_owns_the_contact(client, db):
    from app.models.integration import Integration
    from app.services.integration_key_service import IntegrationKeyService

    ws = _workspace(db)
    contact = _contact(db, ws)
    slug = _slug(db, contact)
    act_as = _user(db, contact=contact, is_integration=True)
    integration = Integration(
        id=str(uuid.uuid4()),
        name=f"zzt-n8n-{uuid.uuid4().hex[:6]}",
        type="automation",
        act_as_user_id=act_as.id,
        is_active=True,
    )
    db.add(integration)
    db.flush()
    key = IntegrationKeyService(db).issue_key(integration)
    db.commit()

    res = client.post(ROUTE, json={"slug": slug}, headers={"X-API-Key": key})
    _assert_refused_without_token(res, contact.id, db, statuses={403})


def test_ac4_user_with_no_linked_contact_is_403(client, db):
    ws = _workspace(db)
    contact = _contact(db, ws)
    slug = _slug(db, contact)
    user = _user(db, contact=None)

    res = client.post(ROUTE, json={"slug": slug}, headers=_bearer(db, user))
    _assert_refused_without_token(res, contact.id, db, statuses={403})


def test_ac4_unknown_slug_is_refused_with_no_token(client, db):
    ws = _workspace(db)
    contact = _contact(db, ws)
    own_slug = _slug(db, contact)
    user = _user(db, contact=contact)
    headers = _bearer(db, user)

    # Route must exist and serve this user: their own slug works (a missing route also 404s,
    # which would otherwise let the unknown-slug assertion below pass for the wrong reason).
    ok = client.post(ROUTE, json={"slug": own_slug}, headers=headers)
    assert ok.status_code == 200, ok.text
    before = len(_tokens(db, contact.id))

    unknown = "ZZZZZZZZZZ" if own_slug != "ZZZZZZZZZZ" else "YYYYYYYYYY"
    res = client.post(ROUTE, json={"slug": unknown}, headers=headers)
    _assert_refused_without_token(res, contact.id, db, statuses={403, 404}, before=before)


def test_ac4_missing_slug_is_422(client, db):
    ws = _workspace(db)
    contact = _contact(db, ws)
    user = _user(db, contact=contact)

    res = client.post(ROUTE, json={}, headers=_bearer(db, user))
    assert res.status_code == 422, res.text
    assert _tokens(db, contact.id) == []


@pytest.mark.parametrize(
    "status, is_trashed",
    [("INACTIVE", False), ("BLOCKED", False), ("ACTIVE", True)],
    ids=["inactive", "blocked", "trashed"],
)
def test_ac4_inactive_or_trashed_user_is_refused(client, db, status, is_trashed):
    ws = _workspace(db)
    contact = _contact(db, ws)
    slug = _slug(db, contact)
    # Session minted while active; the account is then switched off.
    user = _user(db, contact=contact)
    headers = _bearer(db, user)
    user.status = status
    user.is_trashed = is_trashed
    db.commit()

    res = client.post(ROUTE, json={"slug": slug}, headers=headers)
    _assert_refused_without_token(res, contact.id, db, statuses={401, 403})


# --------------------------------------------------------------------------------------
# AC-5: impersonation never mints
# --------------------------------------------------------------------------------------


def test_ac5_impersonated_session_is_403(client, db):
    from app.models.impersonation import ImpersonationSession

    ws = _workspace(db)
    target_contact = _contact(db, ws, name="ZZT Target")
    slug = _slug(db, target_contact)
    target = _user(db, contact=target_contact)
    admin = _user(db, contact=None, role_slug="admin")
    db.add(ImpersonationSession(id=str(uuid.uuid4()), admin_user_id=admin.id, target_user_id=target.id))
    db.commit()

    headers = {**_bearer(db, admin), "X-Impersonate-User-Id": str(target.id)}
    res = client.post(ROUTE, json={"slug": slug}, headers=headers)
    _assert_refused_without_token(res, target_contact.id, db, statuses={403})


def test_ac5_admin_with_own_contact_impersonating_is_403_for_either_slug(client, db):
    """Admin has their own linked contact too; while viewing as someone, neither slug mints."""
    from app.models.impersonation import ImpersonationSession

    ws = _workspace(db)
    admin_contact = _contact(db, ws, name="ZZT Admin")
    target_contact = _contact(db, ws, name="ZZT Target")
    admin_slug = _slug(db, admin_contact)
    target_slug = _slug(db, target_contact)
    target = _user(db, contact=target_contact)
    admin = _user(db, contact=admin_contact, role_slug="admin")
    db.add(ImpersonationSession(id=str(uuid.uuid4()), admin_user_id=admin.id, target_user_id=target.id))
    db.commit()

    headers = {**_bearer(db, admin), "X-Impersonate-User-Id": str(target.id)}
    for slug, cid in ((target_slug, target_contact.id), (admin_slug, admin_contact.id)):
        res = client.post(ROUTE, json={"slug": slug}, headers=headers)
        _assert_refused_without_token(res, cid, db, statuses={403})


# --------------------------------------------------------------------------------------
# Fix round 1 S1: a stale contact link (user's own number no longer matches) never mints
# --------------------------------------------------------------------------------------


def test_s1_user_whose_number_no_longer_matches_the_contact_is_403(client, db):
    ws = _workspace(db)
    contact = _contact(db, ws)
    slug = _slug(db, contact)
    user = _user(db, contact=contact, contact_number=f"+6019{uuid.uuid4().int % 10_000_000:07d}")

    res = client.post(ROUTE, json={"slug": slug}, headers=_bearer(db, user))
    _assert_refused_without_token(res, contact.id, db, statuses={403})


def test_s1_user_with_no_number_of_their_own_is_403(client, db):
    ws = _workspace(db)
    contact = _contact(db, ws)
    slug = _slug(db, contact)
    user = _user(db, contact=contact, contact_number=None)

    res = client.post(ROUTE, json={"slug": slug}, headers=_bearer(db, user))
    _assert_refused_without_token(res, contact.id, db, statuses={403})


def test_s1_same_number_in_another_format_still_mints(client, db):
    """The match is on the normalised number, not the raw string."""
    ws = _workspace(db)
    contact = _contact(db, ws)
    slug = _slug(db, contact)
    digits = contact.phone_number.lstrip("+")
    user = _user(db, contact=contact, contact_number=digits)

    res = client.post(ROUTE, json={"slug": slug}, headers=_bearer(db, user))
    assert res.status_code == 200, res.text


# --------------------------------------------------------------------------------------
# Fix round 1 S2: only a real sign-in session (password, passkey, phone code) may bridge
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("auth_method", ["portal_link", "dev_login"])
def test_s2_session_minted_by_portal_link_or_dev_login_is_403(client, db, auth_method):
    ws = _workspace(db)
    contact = _contact(db, ws)
    slug = _slug(db, contact)
    user = _user(db, contact=contact)

    res = client.post(ROUTE, json={"slug": slug}, headers=_bearer(db, user, auth_method))
    _assert_refused_without_token(res, contact.id, db, statuses={403})


@pytest.mark.parametrize("auth_method", ["password", "passkey", "phone_otp"])
def test_s2_password_passkey_or_phone_code_session_mints(client, db, auth_method):
    ws = _workspace(db)
    contact = _contact(db, ws)
    slug = _slug(db, contact)
    user = _user(db, contact=contact)

    res = client.post(ROUTE, json={"slug": slug}, headers=_bearer(db, user, auth_method))
    assert res.status_code == 200, res.text
    assert len(_tokens(db, contact.id)) == 1


# --------------------------------------------------------------------------------------
# Fix round 1 R5: the bridge is rate limited and mints nothing when over the limit
# --------------------------------------------------------------------------------------


def test_r5_over_the_rate_limit_is_429_and_mints_nothing(client, db, monkeypatch):
    from app.services import rate_limit

    ws = _workspace(db)
    contact = _contact(db, ws)
    slug = _slug(db, contact)
    user = _user(db, contact=contact)
    headers = _bearer(db, user)

    buckets: list[str] = []

    def _deny(bucket, ident, *, limit, window_seconds):
        buckets.append(bucket)
        return rate_limit.RateResult(allowed=False, retry_after_seconds=42)

    monkeypatch.setattr(rate_limit, "hit", _deny)
    res = client.post(ROUTE, json={"slug": slug}, headers=headers)
    assert res.status_code == 429, res.text
    assert buckets, "the bridge must consult the rate limiter"
    assert _tokens(db, contact.id) == []
    try:
        body = res.json()
    except ValueError:
        body = {}
    assert not (isinstance(body, dict) and body.get("token"))


# --------------------------------------------------------------------------------------
# AC-6: verify_otp keeps the same verified_at + 30-day rule (regression guard)
# --------------------------------------------------------------------------------------


def test_ac6_verify_otp_still_mints_verified_30_day_token(db):
    ws = _workspace(db)
    contact = _contact(db, ws)
    code = "246810"
    db.add(
        PortalOtpCode(
            contact_id=contact.id,
            space_id=ws.space_id,
            code_hash=_hash_otp(code),
            expires_at=_utcnow() + timedelta(minutes=10),
        )
    )
    db.commit()

    minted = PortalService(db).verify_otp(contact.id, ws.space_id, code)
    assert minted.verified_at is not None
    assert _near(minted.verified_at, _utcnow())
    assert _near(minted.expires_at, _utcnow() + PORTAL_VERIFIED_TOKEN_TTL)
    assert minted.contact_id == contact.id
    assert PortalService(db).resolve_token(minted.token).id == minted.id
