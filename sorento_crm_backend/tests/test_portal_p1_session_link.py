"""PORTAL-P1-SESSION-LINK red tests: a WhatsApp portal link opens a CRM session.

Brief: `documentation/plans/portal/PLAN-portal-unify-scout-27oct.md`, "Lane briefs" -> P1
(AC-1 to AC-7), lane plan `documentation/plans/portal/PLAN-portal-p1-session-link-27oct.md`.

`POST /api/v1/auth/portal-link {portal_token}` exchanges a portal token verified in the last
120 s for a `user_sessions` row (`auth_method = portal_link`) of the ONE eligible user linked
to the token's contact. Every refusal answers the same 401 body. One OTP verification mints
at most one session (security review decision, see the lane plan).

Postgres only (`tests/_pg_fixture.py`, `blank_session`), one rolled-back transaction per test.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.access import RespondContact
from app.models.portal import PortalToken
from app.models.respond_workspace import RespondWorkspace
from app.models.user import User
from app.models.user_session import UserSession
from tests._pg_fixture import blank_session, unique_code

ROUTE = "/api/v1/auth/portal-link"
REFUSED = {"detail": "Portal link sign-in refused."}


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _digits() -> str:
    return "601" + f"{uuid.uuid4().int % 10**8:08d}"


def _workspace(db) -> RespondWorkspace:
    ws = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=f"sp_{uuid.uuid4().hex[:8]}",
        name="ZZT WS",
        api_key_ciphertext="test-cipher",
    )
    db.add(ws)
    db.flush()
    return ws


def _contact(db, ws, phone: str) -> RespondContact:
    c = RespondContact(
        id=str(uuid.uuid4()), phone_number=phone, name="ZZT Contact", workspace_id=ws.id
    )
    db.add(c)
    db.flush()
    return c


def _user(db, *, phone, contact_id, status="ACTIVE", is_trashed=False, is_integration=False):
    u = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('plink')}@x.com".lower(),
        name="ZZT Portal Link User",
        status=status,
        is_trashed=is_trashed,
        is_integration=is_integration,
        contact_number=phone,
        respond_contact_id=contact_id,
    )
    db.add(u)
    db.commit()
    return u


def _chain(db, *, with_user=True, **user_kw):
    ws = _workspace(db)
    digits = _digits()
    contact = _contact(db, ws, digits)
    user = _user(db, phone=digits, contact_id=contact.id, **user_kw) if with_user else None
    return ws, contact, user


def _verified_token(db, contact, ws, *, age_seconds: float = 0, is_impersonation=False) -> PortalToken:
    """A portal token as `verify_otp` leaves it: verified `age_seconds` ago, 30-day expiry."""
    from app.services.portal_service import PORTAL_VERIFIED_TOKEN_TTL, PortalService, _utcnow

    tok = PortalService(db).mint_token(contact.id, ws.space_id, is_impersonation=is_impersonation)
    now = _utcnow()
    tok.verified_at = now - timedelta(seconds=age_seconds)
    tok.expires_at = now + PORTAL_VERIFIED_TOKEN_TTL
    db.commit()
    return tok


class _client_ctx:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        def _override_db():
            yield self.db

        app.dependency_overrides[get_db] = _override_db
        self._tc = TestClient(app)
        return self._tc.__enter__()

    def __exit__(self, *exc):
        self._tc.__exit__(*exc)
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def _clean_rate_limit():
    from app.services.queue_service import redis_conn

    yield
    redis_conn.delete("rate_limit:v1:portal_link:testclient")


def _sessions(db, user_id):
    return db.query(UserSession).filter(UserSession.user_id == user_id).all()


# --------------------------------------------------------------------------- #
# AC-1: set-up contact gets a CRM session, portal unchanged                    #
# --------------------------------------------------------------------------- #
def test_ac1_verify_otp_then_exchange_mints_portal_link_session():
    """End to end through the real verify-otp route: the portal token it returns still
    works on the portal, and exchanging it yields a CRM session for the linked user."""
    from app.services.portal_service import PortalService

    with blank_session() as db:
        ws, contact, user = _chain(db)
        captured: dict = {}

        def _fake_task(otp_id, identifier, message_text, otp_code, space_id):
            captured["code"] = otp_code
            return {"status": "success"}

        PortalService(db).create_and_dispatch_otp(
            contact, ws.space_id, "code {code}", _fake_task, dispatch_inline=True
        )
        with _client_ctx(db) as client:
            v = client.post(
                "/api/v1/public/portal/verify-otp",
                json={"contact_id": contact.id, "space_id": ws.space_id, "code": captured["code"]},
            )
            assert v.status_code == 200, v.text
            portal_token = v.json()["token"]

            r = client.post(ROUTE, json={"portal_token": portal_token})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["id"] == user.id
            assert body["token"]

            # The CRM session works on a staff route and resolves to the user.
            me = client.get("/api/v1/auth/sessions", headers={"Authorization": f"Bearer {body['token']}"})
            assert me.status_code == 200, me.text

            # The portal token is untouched and still grants portal access.
            pm = client.get("/api/v1/public/portal/me", headers={"X-Portal-Token": portal_token})
            assert pm.status_code == 200, pm.text

        rows = _sessions(db, user.id)
        assert len(rows) == 1
        assert rows[0].auth_method == "portal_link"
        assert rows[0].token == body["token"]
        assert rows[0].revoked_at is None


def test_ac1_audit_actor_is_the_user():

    with blank_session() as db:
        ws, contact, user = _chain(db)
        tok = _verified_token(db, contact, ws)
        with _client_ctx(db) as client:
            r = client.post(ROUTE, json={"portal_token": tok.token})
            assert r.status_code == 200, r.text
            sessions = client.get(
                "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {r.json()['token']}"}
            ).json()
        # The sessions list is the CURRENT USER's own list: the session belongs to the user.
        assert len(sessions) == 1
        assert sessions[0]["current"] is True
        assert _sessions(db, user.id)[0].user_id == user.id


def test_ac1_stamps_last_sign_in():
    with blank_session() as db:
        ws, contact, user = _chain(db)
        tok = _verified_token(db, contact, ws)
        with _client_ctx(db) as client:
            assert client.post(ROUTE, json={"portal_token": tok.token}).status_code == 200
        db.refresh(user)
        assert user.last_sign_in_at is not None


# --------------------------------------------------------------------------- #
# One-time: one OTP verification mints at most one session                     #
# --------------------------------------------------------------------------- #
def test_replay_of_same_token_is_refused():
    with blank_session() as db:
        ws, contact, user = _chain(db)
        tok = _verified_token(db, contact, ws)
        with _client_ctx(db) as client:
            assert client.post(ROUTE, json={"portal_token": tok.token}).status_code == 200
            r2 = client.post(ROUTE, json={"portal_token": tok.token})
        assert r2.status_code == 401
        assert r2.json() == REFUSED
        assert len(_sessions(db, user.id)) == 1


def test_sibling_token_verified_by_the_same_otp_is_refused():
    """verify_otp stamps every unverified token of the contact with the same `verified_at`
    (the admin-sent link included); one verification must still mint only one session."""
    from app.services.portal_service import PortalService, _utcnow

    with blank_session() as db:
        ws, contact, user = _chain(db)
        a = PortalService(db).mint_token(contact.id, ws.space_id)
        b = PortalService(db).mint_token(contact.id, ws.space_id)
        now = _utcnow()
        a.verified_at = now
        b.verified_at = now
        db.commit()
        with _client_ctx(db) as client:
            assert client.post(ROUTE, json={"portal_token": a.token}).status_code == 200
            r2 = client.post(ROUTE, json={"portal_token": b.token})
        assert r2.status_code == 401
        assert r2.json() == REFUSED
        assert len(_sessions(db, user.id)) == 1


def test_redis_unavailable_fails_closed():
    """The one-time claim lives in Redis; without it nothing is minted (the portal itself
    is unaffected, the person just gets no CRM session)."""
    with blank_session() as db:
        ws, contact, user = _chain(db)
        tok = _verified_token(db, contact, ws)
        with _client_ctx(db) as client, patch(
            "app.services.phone_signin_service._redis", return_value=None
        ):
            r = client.post(ROUTE, json={"portal_token": tok.token})
        assert r.status_code == 401
        assert r.json() == REFUSED
        assert _sessions(db, user.id) == []


def test_refused_attempt_does_not_burn_the_claim():
    """A refusal before the claim (e.g. the user is briefly INACTIVE) must not stop a later
    valid exchange inside the window."""
    with blank_session() as db:
        ws, contact, user = _chain(db, status="INACTIVE")
        tok = _verified_token(db, contact, ws)
        with _client_ctx(db) as client:
            assert client.post(ROUTE, json={"portal_token": tok.token}).status_code == 401
            user.status = "ACTIVE"
            db.commit()
            assert client.post(ROUTE, json={"portal_token": tok.token}).status_code == 200


# --------------------------------------------------------------------------- #
# AC-2: contact without a user                                                 #
# --------------------------------------------------------------------------- #
def test_ac2_contact_without_user_is_refused_and_mints_nothing():
    with blank_session() as db:
        ws, contact, _ = _chain(db, with_user=False)
        tok = _verified_token(db, contact, ws)
        before = db.query(UserSession).count()
        with _client_ctx(db) as client:
            r = client.post(ROUTE, json={"portal_token": tok.token})
        assert r.status_code == 401
        assert r.json() == REFUSED
        assert db.query(UserSession).count() == before


# --------------------------------------------------------------------------- #
# AC-3: impersonation token never mints                                        #
# --------------------------------------------------------------------------- #
def test_ac3_impersonation_token_never_mints():
    with blank_session() as db:
        ws, contact, user = _chain(db)
        tok = _verified_token(db, contact, ws, is_impersonation=True)
        with _client_ctx(db) as client:
            r = client.post(ROUTE, json={"portal_token": tok.token})
        assert r.status_code == 401
        assert r.json() == REFUSED
        assert _sessions(db, user.id) == []


# --------------------------------------------------------------------------- #
# AC-4: every refusal is the same 401 body                                     #
# --------------------------------------------------------------------------- #
def _refusal_case(db, case: str) -> tuple[str, User | None]:
    from app.services.portal_service import PortalService, _utcnow

    if case == "not_found":
        ws, contact, user = _chain(db)
        return "NOPE" + uuid.uuid4().hex, user
    if case == "empty":
        ws, contact, user = _chain(db)
        return "", user
    if case == "no_user":
        ws, contact, _ = _chain(db, with_user=False)
        return _verified_token(db, contact, ws).token, None
    kw = {
        "inactive": {"status": "INACTIVE"},
        "blocked": {"status": "BLOCKED"},
        "trashed": {"is_trashed": True},
        "integration": {"is_integration": True},
    }.get(case, {})
    ws, contact, user = _chain(db, **kw)
    if case == "revoked":
        tok = _verified_token(db, contact, ws)
        tok.revoked_at = _utcnow()
        db.commit()
        return tok.token, user
    if case == "expired":
        tok = _verified_token(db, contact, ws)
        tok.expires_at = _utcnow() - timedelta(seconds=1)
        db.commit()
        return tok.token, user
    if case == "unverified":
        tok = PortalService(db).mint_token(contact.id, ws.space_id)
        return tok.token, user
    if case == "stale_verify":
        return _verified_token(db, contact, ws, age_seconds=121).token, user
    if case == "phone_mismatch":
        # Lost-phone rule shared with phone sign-in: the user's own number no longer
        # matches the linked contact's (the link is stale).
        user.contact_number = _digits()
        db.commit()
        return _verified_token(db, contact, ws).token, user
    if case == "two_users":
        _user(db, phone=contact.phone_number, contact_id=contact.id)
        return _verified_token(db, contact, ws).token, user
    return _verified_token(db, contact, ws).token, user


@pytest.mark.parametrize(
    "case",
    [
        "not_found",
        "empty",
        "revoked",
        "expired",
        "unverified",
        "stale_verify",
        "no_user",
        "inactive",
        "blocked",
        "trashed",
        "integration",
        "phone_mismatch",
        "two_users",
    ],
)
def test_ac4_refusals_share_one_401_body(case):
    with blank_session() as db:
        token, user = _refusal_case(db, case)
        before = db.query(UserSession).count()
        with _client_ctx(db) as client:
            r = client.post(ROUTE, json={"portal_token": token})
        assert r.status_code == 401, (case, r.text)
        assert r.json() == REFUSED, (case, r.text)
        assert db.query(UserSession).count() == before


def test_ac4_verified_119s_ago_still_mints():
    """Boundary: inside the 120 s window."""
    with blank_session() as db:
        ws, contact, user = _chain(db)
        tok = _verified_token(db, contact, ws, age_seconds=110)
        with _client_ctx(db) as client:
            r = client.post(ROUTE, json={"portal_token": tok.token})
        assert r.status_code == 200, r.text


def test_ac4_window_uses_verified_at_not_created_at():
    """A token created long ago but verified just now (the admin-sent link that verify_otp
    stamps) is inside the window; created_at is never the clock."""
    from app.services.portal_service import _utcnow

    with blank_session() as db:
        ws, contact, user = _chain(db)
        tok = _verified_token(db, contact, ws)
        tok.created_at = _utcnow() - timedelta(days=3)
        db.commit()
        with _client_ctx(db) as client:
            r = client.post(ROUTE, json={"portal_token": tok.token})
        assert r.status_code == 200, r.text


def test_rate_limited_per_ip():
    from app.config import settings

    with blank_session() as db:
        with _client_ctx(db) as client, patch.object(settings, "rate_limit_portal_otp_max", 2):
            codes = [
                client.post(ROUTE, json={"portal_token": "NOPE" + uuid.uuid4().hex}).status_code
                for _ in range(3)
            ]
    assert codes == [401, 401, 429]


# --------------------------------------------------------------------------- #
# AC-5: logout revokes the portal_link session                                 #
# --------------------------------------------------------------------------- #
def test_ac5_logout_revokes_the_session_row():
    with blank_session() as db:
        ws, contact, user = _chain(db)
        tok = _verified_token(db, contact, ws)
        with _client_ctx(db) as client:
            api_token = client.post(ROUTE, json={"portal_token": tok.token}).json()["token"]
            auth = {"Authorization": f"Bearer {api_token}"}
            assert client.post("/api/v1/auth/logout", headers=auth).status_code == 200
            assert client.get("/api/v1/auth/sessions", headers=auth).status_code == 401
            # The portal logout route still revokes the portal token as before.
            assert (
                client.post("/api/v1/public/portal/logout", headers={"X-Portal-Token": tok.token}).status_code
                == 204
            )
        row = _sessions(db, user.id)[0]
        assert row.revoked_at is not None
        db.refresh(tok)
        assert tok.revoked_at is not None


# --------------------------------------------------------------------------- #
# AC-6: has_user is a boolean only                                             #
# --------------------------------------------------------------------------- #
SLUG_KEYS = {"contact_id", "space_id", "name", "masked_phone", "whatsapp_number", "has_user"}
TOKEN_KEYS = {
    "contact_id", "space_id", "expires_at", "expired", "revoked", "portal_slug",
    "name", "masked_phone", "whatsapp_number", "has_user",
}


@pytest.mark.parametrize("with_user", [True, False])
def test_ac6_slug_info_and_token_info_carry_has_user_only(with_user):
    from app.services.portal_service import PortalService

    with blank_session() as db:
        ws, contact, user = _chain(db, with_user=with_user)
        slug = PortalService(db).get_or_create_slug(contact)
        tok = PortalService(db).mint_token(contact.id, ws.space_id)  # unverified is fine for token-info
        with _client_ctx(db) as client:
            s = client.get(f"/api/v1/public/portal/slug-info/{slug}")
            t = client.get("/api/v1/public/portal/token-info", params={"token": tok.token})
        assert s.status_code == 200, s.text
        assert t.status_code == 200, t.text
        for resp, keys in ((s, SLUG_KEYS), (t, TOKEN_KEYS)):
            body = resp.json()
            assert set(body.keys()) == keys, body
            assert body["has_user"] is with_user
            if user is not None:
                assert user.id not in resp.text
                assert user.email not in resp.text
                assert user.name not in resp.text


def test_ac6_has_user_false_for_ineligible_user():
    """has_user mirrors the exchange's eligibility, so the card never calls NextAuth for a
    link that would be refused."""
    from app.services.portal_service import PortalService

    with blank_session() as db:
        ws, contact, user = _chain(db, status="INACTIVE")
        slug = PortalService(db).get_or_create_slug(contact)
        with _client_ctx(db) as client:
            s = client.get(f"/api/v1/public/portal/slug-info/{slug}")
        assert s.json()["has_user"] is False
