"""PORTAL-P1-SESSION-LINK: a WhatsApp portal link opens a CRM session.

Brief: `documentation/plans/portal/PLAN-portal-unify-scout-27oct.md`, "Lane briefs" -> P1
(AC-1 to AC-7); lane plan `documentation/plans/portal/PLAN-portal-p1-session-link-27oct.md`.

Security review round 1 (H1) changed the shape: `/public/portal/verify-otp` returns a one-time
`portal_link_secret` (only when the contact has an eligible user), and
`POST /api/v1/auth/portal-link {portal_link_secret}` exchanges THAT, never a portal token, for a
`user_sessions` row (`auth_method = portal_link`). Only the browser that entered the code holds
the secret, so a sibling token, a token staff re-send, or a token in a log cannot mint a session.
Every refusal answers the same 401 body.

Postgres only (`tests/_pg_fixture.py`, `blank_session`), one rolled-back transaction per test.
"""
from __future__ import annotations

import hashlib
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.access import RespondContact
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


def _verify(client, db, contact, ws) -> dict:
    """The real portal flow: an OTP goes out, the card posts the code to verify-otp."""
    from app.services.portal_service import PortalService

    captured: dict = {}

    def _fake_task(otp_id, identifier, message_text, otp_code, space_id):
        captured["code"] = otp_code
        return {"status": "success"}

    PortalService(db).create_and_dispatch_otp(
        contact, ws.space_id, "code {code}", _fake_task, dispatch_inline=True
    )
    r = client.post(
        "/api/v1/public/portal/verify-otp",
        json={"contact_id": contact.id, "space_id": ws.space_id, "code": captured["code"]},
    )
    assert r.status_code == 200, r.text
    return r.json()


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


def _secret_key(secret: str) -> str:
    return "portal_link:secret:" + hashlib.sha256(secret.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# AC-1: set-up contact gets a CRM session, portal unchanged                    #
# --------------------------------------------------------------------------- #
def test_ac1_verify_then_exchange_mints_portal_link_session():
    with blank_session() as db:
        ws, contact, user = _chain(db)
        with _client_ctx(db) as client:
            v = _verify(client, db, contact, ws)
            assert set(v.keys()) == {"token", "expires_at", "portal_link_secret"}

            r = client.post(ROUTE, json={"portal_link_secret": v["portal_link_secret"]})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["id"] == user.id

            # The CRM session works on a staff route and is the user's own.
            auth = {"Authorization": f"Bearer {body['token']}"}
            sessions = client.get("/api/v1/auth/sessions", headers=auth)
            assert sessions.status_code == 200, sessions.text
            assert len(sessions.json()) == 1 and sessions.json()[0]["current"] is True

            # The portal token is untouched and still grants portal access.
            pm = client.get("/api/v1/public/portal/me", headers={"X-Portal-Token": v["token"]})
            assert pm.status_code == 200, pm.text

        rows = _sessions(db, user.id)
        assert len(rows) == 1
        assert rows[0].auth_method == "portal_link"
        assert rows[0].token == body["token"]
        db.refresh(user)
        assert user.last_sign_in_at is not None


def test_ac1_secret_lives_120s_and_only_its_hash_is_stored():
    from app.services.queue_service import redis_conn

    with blank_session() as db:
        ws, contact, user = _chain(db)
        with _client_ctx(db) as client:
            secret = _verify(client, db, contact, ws)["portal_link_secret"]
        ttl = redis_conn.ttl(_secret_key(secret))
        assert 0 < ttl <= 120
        assert not redis_conn.keys(f"*{secret}*")
        redis_conn.delete(_secret_key(secret))


# --------------------------------------------------------------------------- #
# Security review H1: only the verifying browser's secret mints                #
# --------------------------------------------------------------------------- #
def test_h1_no_portal_token_is_accepted_even_before_the_card_exchanges():
    """The fresh token, a sibling token stamped by the same OTP, and the token staff
    'copy link' hands back (`get_or_mint_token`) all fail; the card's secret still works."""
    from app.services.portal_service import PortalService

    with blank_session() as db:
        ws, contact, user = _chain(db)
        sibling = PortalService(db).mint_token(contact.id, ws.space_id)  # admin-sent, unverified
        with _client_ctx(db) as client:
            v = _verify(client, db, contact, ws)
            db.refresh(sibling)
            assert sibling.verified_at is not None  # verify_otp stamped it too
            reused, was_reused = PortalService(db).get_or_mint_token(contact.id, ws.space_id)
            assert was_reused
            for candidate in (v["token"], sibling.token, reused.token):
                r = client.post(ROUTE, json={"portal_link_secret": candidate})
                assert r.status_code == 401, r.text
                assert r.json() == REFUSED
            assert _sessions(db, user.id) == []
            ok = client.post(ROUTE, json={"portal_link_secret": v["portal_link_secret"]})
        assert ok.status_code == 200, ok.text
        assert len(_sessions(db, user.id)) == 1


def test_h1_old_field_name_is_not_accepted():
    """The brief's original `{portal_token}` body is gone: a portal token never mints."""
    with blank_session() as db:
        ws, contact, user = _chain(db)
        with _client_ctx(db) as client:
            v = _verify(client, db, contact, ws)
            r = client.post(ROUTE, json={"portal_token": v["token"]})
        assert r.status_code == 422
        assert _sessions(db, user.id) == []


def test_replay_of_the_secret_is_refused():
    with blank_session() as db:
        ws, contact, user = _chain(db)
        with _client_ctx(db) as client:
            secret = _verify(client, db, contact, ws)["portal_link_secret"]
            assert client.post(ROUTE, json={"portal_link_secret": secret}).status_code == 200
            r2 = client.post(ROUTE, json={"portal_link_secret": secret})
        assert r2.status_code == 401
        assert r2.json() == REFUSED
        assert len(_sessions(db, user.id)) == 1


def test_expired_secret_is_refused():
    from app.services.queue_service import redis_conn

    with blank_session() as db:
        ws, contact, user = _chain(db)
        with _client_ctx(db) as client:
            secret = _verify(client, db, contact, ws)["portal_link_secret"]
            redis_conn.delete(_secret_key(secret))  # what the 120 s TTL does
            r = client.post(ROUTE, json={"portal_link_secret": secret})
        assert r.status_code == 401
        assert r.json() == REFUSED
        assert _sessions(db, user.id) == []


def test_user_turned_ineligible_after_verify_is_refused():
    with blank_session() as db:
        ws, contact, user = _chain(db)
        with _client_ctx(db) as client:
            secret = _verify(client, db, contact, ws)["portal_link_secret"]
            user.status = "BLOCKED"
            db.commit()
            r = client.post(ROUTE, json={"portal_link_secret": secret})
        assert r.status_code == 401
        assert r.json() == REFUSED
        assert _sessions(db, user.id) == []


def test_redis_down_at_verify_issues_no_secret_and_portal_still_works():
    with blank_session() as db:
        ws, contact, user = _chain(db)
        with _client_ctx(db) as client, patch(
            "app.services.phone_signin_service._redis", return_value=None
        ):
            v = _verify(client, db, contact, ws)
        assert set(v.keys()) == {"token", "expires_at"}


def test_redis_down_at_exchange_fails_closed():
    with blank_session() as db:
        ws, contact, user = _chain(db)
        with _client_ctx(db) as client:
            secret = _verify(client, db, contact, ws)["portal_link_secret"]
            with patch("app.services.phone_signin_service._redis", return_value=None):
                r = client.post(ROUTE, json={"portal_link_secret": secret})
        assert r.status_code == 401
        assert r.json() == REFUSED
        assert _sessions(db, user.id) == []


# --------------------------------------------------------------------------- #
# AC-2: contact without a user: verify-otp byte-identical, nothing minted      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "case",
    ["no_user", "inactive", "blocked", "trashed", "integration", "phone_mismatch"],
)
def test_ac2_ac4_no_secret_for_a_contact_without_an_eligible_user(case):
    with blank_session() as db:
        kw = {
            "inactive": {"status": "INACTIVE"},
            "blocked": {"status": "BLOCKED"},
            "trashed": {"is_trashed": True},
            "integration": {"is_integration": True},
        }.get(case, {})
        ws, contact, user = _chain(db, with_user=(case != "no_user"), **kw)
        if case == "phone_mismatch":
            # Lost-phone rule shared with phone sign-in: the user's own number no longer
            # matches the linked contact's (a stale link).
            user.contact_number = _digits()
            db.commit()
        before = db.query(UserSession).count()
        with _client_ctx(db) as client:
            v = _verify(client, db, contact, ws)
        # Exactly today's shape: no extra key, not even a null one.
        assert set(v.keys()) == {"token", "expires_at"}, v
        assert db.query(UserSession).count() == before


# --------------------------------------------------------------------------- #
# AC-3: an admin "view as contact" token never mints                           #
# --------------------------------------------------------------------------- #
def test_ac3_impersonation_token_never_mints():
    from app.services.portal_service import PortalService, _utcnow

    with blank_session() as db:
        ws, contact, user = _chain(db)
        tok = PortalService(db).mint_token(contact.id, ws.space_id, is_impersonation=True)
        tok.verified_at = _utcnow()
        db.commit()
        with _client_ctx(db) as client:
            r = client.post(ROUTE, json={"portal_link_secret": tok.token})
        assert r.status_code == 401
        assert r.json() == REFUSED
        assert _sessions(db, user.id) == []


# --------------------------------------------------------------------------- #
# AC-4: one 401 body for every refusal at the exchange                         #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("secret", ["", "x", "NOPE" + uuid.uuid4().hex, "a" * 200])
def test_ac4_unknown_secret_is_the_same_401(secret):
    with blank_session() as db:
        with _client_ctx(db) as client:
            r = client.post(ROUTE, json={"portal_link_secret": secret})
        assert r.status_code == 401, r.text
        assert r.json() == REFUSED


def test_rate_limited_per_ip_with_its_own_setting():
    from app.config import settings

    assert settings.rate_limit_portal_link_max <= 10
    with blank_session() as db:
        with _client_ctx(db) as client, patch.object(settings, "rate_limit_portal_link_max", 2):
            codes = [
                client.post(ROUTE, json={"portal_link_secret": "NOPE" + uuid.uuid4().hex}).status_code
                for _ in range(3)
            ]
    assert codes == [401, 401, 429]


# --------------------------------------------------------------------------- #
# AC-5: logout revokes the portal_link session                                 #
# --------------------------------------------------------------------------- #
def test_ac5_logout_revokes_the_session_row():
    with blank_session() as db:
        ws, contact, user = _chain(db)
        with _client_ctx(db) as client:
            v = _verify(client, db, contact, ws)
            api_token = client.post(ROUTE, json={"portal_link_secret": v["portal_link_secret"]}).json()["token"]
            auth = {"Authorization": f"Bearer {api_token}"}
            assert client.post("/api/v1/auth/logout", headers=auth).status_code == 200
            assert client.get("/api/v1/auth/sessions", headers=auth).status_code == 401
            assert (
                client.post("/api/v1/public/portal/logout", headers={"X-Portal-Token": v["token"]}).status_code
                == 204
            )
        assert _sessions(db, user.id)[0].revoked_at is not None


# --------------------------------------------------------------------------- #
# AC-6: nothing about the user leaks through the public portal routes          #
# --------------------------------------------------------------------------- #
def test_ac6_public_routes_name_no_user():
    """Security review: the card no longer needs `has_user` (the secret's presence is the
    signal), so slug-info / token-info keep today's shape and do not mark staff contacts."""
    from app.services.portal_service import PortalService

    with blank_session() as db:
        ws, contact, user = _chain(db)
        slug = PortalService(db).get_or_create_slug(contact)
        with _client_ctx(db) as client:
            v = _verify(client, db, contact, ws)
            s = client.get(f"/api/v1/public/portal/slug-info/{slug}")
            t = client.get("/api/v1/public/portal/token-info", params={"token": v["token"]})
        for resp in (s, t):
            assert resp.status_code == 200, resp.text
            assert "has_user" not in resp.json()
            assert user.id not in resp.text
            assert user.email not in resp.text
            assert user.name not in resp.text
        assert user.id not in str(v) and user.email not in str(v)
