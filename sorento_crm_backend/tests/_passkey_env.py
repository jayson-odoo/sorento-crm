"""Shared seeding + call helpers for the PASSKEY-LOGIN tests (test_passkey_signin.py,
test_passkey_manage.py).

Postgres only: every test runs on `blank_session()` (a blank copy of the full schema, rolled
back at teardown) and seeds its own users, roles, permissions and passkeys - CI's database is
empty. The route reads through a `get_db` override onto that same session.

`rate_limit.hit` is replaced for every test with an always-allow recorder: every request from
TestClient comes from the one address "testclient", so the real Redis counters would bleed
across tests. A rate-limit test flips `env.deny_rate` to see the 429.

Contract: documentation/plans/identity/passkey-login-12nov-acceptance-criteria.md
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi.testclient import TestClient

from tests._pg_fixture import blank_session, unique_code
from tests._soft_authenticator import SoftAuthenticator, user_handle_for

RP_ID = "crm.example.test"
ORIGIN = "https://crm.example.test"
# Same listed hostname, different origin (port): a stored-origin mismatch, not an RP mismatch.
ALT_ORIGIN = "https://crm.example.test:8443"
OTHER_RP_ID = "other.example.test"
RP_IDS = f"{RP_ID},{OTHER_RP_ID},localhost"

PASSWORD = "correct-horse-battery-staple"

PASSKEY_FAILED = {"code": "PASSKEY_FAILED", "message": "That passkey didn't work. Sign in another way."}

IPHONE_SAFARI_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
)

ITEM_KEYS = {"id", "name", "created_at", "last_used_at"}


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


class _BrokenRedis:
    """Every call raises the error a dead Redis raises."""

    def __getattr__(self, name):
        import redis

        def _fail(*_a, **_k):
            raise redis.exceptions.ConnectionError("redis is down (test)")

        return _fail


class PasskeyEnv:
    def __init__(self, db, client: TestClient, monkeypatch):
        self.db = db
        self.client = client
        self.monkeypatch = monkeypatch
        self.deny_rate = False
        self.rate_buckets: list[str] = []

    # ---- seeding ----------------------------------------------------------------------

    def make_user(
        self,
        *,
        status: str = "ACTIVE",
        is_trashed: bool = False,
        passkey_enabled: bool = True,
        password: Optional[str] = PASSWORD,
        email: Optional[str] = None,
        **extra,
    ):
        from app.models.user import User

        user = User(
            id=str(uuid.uuid4()),
            email=email or f"{unique_code('pk', alpha=True)}@example.com".lower(),
            name="ZZT Passkey User",
            password=hash_pw(password) if password else None,
            status=status,
            is_trashed=is_trashed,
            passkey_enabled=passkey_enabled,
            **extra,
        )
        self.db.add(user)
        self.db.commit()
        return user

    def grant(self, user, *slugs: str, role_slug: Optional[str] = None):
        """Give ``user`` a fresh role holding exactly ``slugs`` (each permission seeded)."""
        from app.models.user import UserPermission, UserRole, UserRoleAssignment, UserRolePermission

        role = UserRole(
            id=str(uuid.uuid4()),
            slug=role_slug or unique_code("role", alpha=True).lower(),
            name=unique_code("Role"),
            is_protected=False,
            is_default=False,
        )
        self.db.add(role)
        self.db.flush()
        for slug in slugs:
            perm = self.db.query(UserPermission).filter(UserPermission.slug == slug).first()
            if perm is None:
                perm = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
                self.db.add(perm)
                self.db.flush()
            self.db.add(UserRolePermission(role_id=role.id, permission_id=perm.id))
        self.db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
        self.db.commit()
        return role

    def make_admin(self, **kw):
        user = self.make_user(**kw)
        self.grant(user, role_slug="admin")
        return user

    def impersonate(self, admin, target) -> dict:
        """A live impersonation row; returns headers for the admin's session viewing as target."""
        from app.models.impersonation import ImpersonationSession

        self.db.add(
            ImpersonationSession(id=str(uuid.uuid4()), admin_user_id=admin.id, target_user_id=target.id)
        )
        self.db.commit()
        return {**self.auth(admin), "X-Impersonate-User-Id": str(target.id)}

    def auth(self, user, *, origin: Optional[str] = ORIGIN) -> dict:
        """Bearer headers for a real password session of ``user`` (one minted per user)."""
        from app.services.user_session_service import mint_session

        cache = self.__dict__.setdefault("_tokens", {})
        if user.id not in cache:
            cache[user.id] = mint_session(self.db, str(user.id), auth_method="password").token
        headers = {"Authorization": f"Bearer {cache[user.id]}"}
        if origin:
            headers["Origin"] = origin
        return headers

    def seed_passkey(
        self,
        user,
        authenticator: Optional[SoftAuthenticator] = None,
        *,
        sign_count: int = 0,
        name: str = "ZZT key",
        created_at: Optional[datetime] = None,
    ):
        """Store a passkey row directly. ``public_key`` holds the COSE_Key bytes (what
        py_webauthn returns as ``credential_public_key`` and what an assertion is verified
        against)."""
        from app.models.user_passkey import UserPasskey

        auth = authenticator or SoftAuthenticator()
        row = UserPasskey(
            id=str(uuid.uuid4()),
            user_id=user.id,
            credential_id=auth.credential_id_b64,
            public_key=auth.cose_public_key(),
            sign_count=sign_count,
            transports=["internal"],
            aaguid=str(uuid.UUID(bytes=auth.aaguid)),
            backed_up=True,
            name=name,
        )
        if created_at is not None:
            row.created_at = created_at
        self.db.add(row)
        self.db.commit()
        return row, auth

    # ---- reads ------------------------------------------------------------------------

    def sessions(self, user_id: str):
        from app.models.user_session import UserSession

        self.db.expire_all()
        return self.db.query(UserSession).filter(UserSession.user_id == str(user_id)).all()

    def passkey(self, passkey_id: str):
        from app.models.user_passkey import UserPasskey

        self.db.expire_all()
        return self.db.query(UserPasskey).filter(UserPasskey.id == str(passkey_id)).first()

    def passkeys_of(self, user_id: str):
        from app.models.user_passkey import UserPasskey

        self.db.expire_all()
        return self.db.query(UserPasskey).filter(UserPasskey.user_id == str(user_id)).all()

    def audit_rows(self, *, entity_type: str, entity_id: Optional[str] = None, **filters):
        from app.models.audit import AuditLog

        self.db.expire_all()
        q = self.db.query(AuditLog).filter(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            q = q.filter(AuditLog.entity_id == str(entity_id))
        for col, value in filters.items():
            q = q.filter(getattr(AuditLog, col) == value)
        return q.all()

    # ---- sign-in calls ----------------------------------------------------------------

    def sign_in_options(self, origin: str = ORIGIN):
        return self.client.post("/api/v1/auth/passkey/options", headers={"Origin": origin})

    def sign_in_challenge(self, origin: str = ORIGIN) -> tuple[str, str]:
        res = self.sign_in_options(origin)
        assert res.status_code == 200, res.text
        body = res.json()
        return body["challenge_id"], body["options"]["challenge"]

    def verify(self, challenge_id: str, credential: dict, *, origin: str = ORIGIN):
        return self.client.post(
            "/api/v1/auth/passkey/verify",
            json={"challenge_id": challenge_id, "credential": credential},
            headers={"Origin": origin, "User-Agent": IPHONE_SAFARI_UA},
        )

    def assertion(self, auth: SoftAuthenticator, user, challenge: str, **kw) -> dict:
        kw.setdefault("origin", ORIGIN)
        kw.setdefault("rp_id", RP_ID)
        kw.setdefault("user_handle", user_handle_for(user.id))
        return auth.authentication_response(challenge=challenge, **kw)

    # ---- registration calls -----------------------------------------------------------

    def register_options(self, headers: dict, body: Optional[dict] = None):
        return self.client.post(
            "/api/v1/auth/passkeys/register/options",
            json={"password": PASSWORD} if body is None else body,
            headers=headers,
        )

    def register_challenge(self, user, *, origin: str = ORIGIN, headers: Optional[dict] = None):
        res = self.register_options(headers or self.auth(user, origin=origin))
        assert res.status_code == 200, res.text
        body = res.json()
        return body["challenge_id"], body["options"]

    def register(self, headers: dict, challenge_id: str, credential: dict, *, name: Optional[str] = None):
        payload = {"challenge_id": challenge_id, "credential": credential}
        if name is not None:
            payload["name"] = name
        return self.client.post(
            "/api/v1/auth/passkeys",
            json=payload,
            headers={**headers, "User-Agent": IPHONE_SAFARI_UA},
        )

    def registration(self, auth: SoftAuthenticator, challenge: str, **kw) -> dict:
        kw.setdefault("origin", ORIGIN)
        kw.setdefault("rp_id", RP_ID)
        return auth.registration_response(challenge=challenge, **kw)

    # ---- infra ------------------------------------------------------------------------

    def break_redis(self):
        """Make the challenge store unreachable, wherever the service reaches Redis from."""
        broken = _BrokenRedis()
        self.monkeypatch.setattr("app.services.queue_service.redis_conn", broken)
        from app.services import passkey_service

        # A module-level connection object is swapped for the broken one; a getter
        # function (`_redis()` / `_redis_conn()`, the shape login_throttle uses) is
        # swapped for one that returns it.
        if hasattr(passkey_service, "redis_conn"):
            self.monkeypatch.setattr(passkey_service, "redis_conn", broken)
        for getter in ("_redis_conn", "_redis"):
            if callable(getattr(passkey_service, getter, None)):
                self.monkeypatch.setattr(passkey_service, getter, lambda: broken)


def make_env(monkeypatch):
    """Generator body for the `env` fixture in each passkey test file."""
    from app.config import settings
    from app.database import get_db
    from app.main import app
    from app.models.base import set_company_scope
    from app.services import rate_limit
    from app.services.company_scope_resolver import apply_company_scope

    monkeypatch.setattr(settings, "webauthn_rp_ids", RP_IDS)

    with blank_session() as db:

        def _override():
            yield db

        def _all_companies():
            # Seeded users hold no company grants; without this `/pending-actions/current`
            # hides their own `last_outcome` (same override tests/test_saved_views_routes.py uses).
            set_company_scope(db, None)
            return None

        app.dependency_overrides[get_db] = _override
        app.dependency_overrides[apply_company_scope] = _all_companies
        try:
            with TestClient(app) as client:
                env = PasskeyEnv(db, client, monkeypatch)
                # The real limiter, for the test that proves no per-IP gate runs at all.
                env.real_hit = rate_limit.hit

                def _fake_hit(bucket, ident, *, limit, window_seconds):
                    env.rate_buckets.append(bucket)
                    if env.deny_rate:
                        return rate_limit.RateResult(allowed=False, retry_after_seconds=42)
                    return rate_limit.RateResult(allowed=True)

                monkeypatch.setattr(rate_limit, "hit", _fake_hit)
                yield env
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(apply_company_scope, None)


def recent(dt: Optional[datetime], *, within: timedelta = timedelta(minutes=5)) -> bool:
    if dt is None:
        return False
    now = datetime.utcnow()
    return now - within <= dt.replace(tzinfo=None) <= now + timedelta(minutes=1)
