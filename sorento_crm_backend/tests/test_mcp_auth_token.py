"""MCP-TOKEN-UI: the MCP bearer token is set on Settings > Integrations, stored encrypted.

Plan: documentation/plans/security/PLAN-mcp-token-ui-30oct.md.

Postgres `blank_session()` only. The MCP server's side (digests, cache, Enforce) is pinned in
sorento_crm_mcp/tests/test_token_from_backend.py; this file pins what the backend stores, what
it tells the MCP server, who may change it, and that no token ever lands in a response it
should not, a log, or the audit trail.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests._pg_fixture import TEST_PREFIX, blank_session

SETTINGS = "/api/v1/user-management/settings/mcp-token"
MCP_AUTH = "/api/v1/system/mcp-auth"
SECRETS_SLUG = "user_management.settings.secrets"


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture(autouse=True)
def fresh_cache():
    from app.services import mcp_auth_token

    mcp_auth_token.clear_cache()
    yield
    mcp_auth_token.clear_cache()


@pytest.fixture
def actor(db):
    from app.models.user import User

    user = User(
        id=str(uuid.uuid4()),
        email=f"{TEST_PREFIX}-mcp-actor-{uuid.uuid4().hex[:6]}@zzt.test".lower(),
        name=f"{TEST_PREFIX} MCP Actor",
        avatar_storage_provider="s3",
    )
    db.add(user)
    db.commit()
    return user


def _row(db):
    from app.models.user import SystemSetting

    db.expire_all()
    return db.query(SystemSetting).first()


def _audit_rows(db):
    from app.models.audit import AuditLog

    db.expire_all()
    return db.query(AuditLog).filter(AuditLog.event == "MCP_AUTH_TOKEN").all()


# --------------------------------------------------------------------------- service


def test_nothing_set_means_no_token_and_a_permit_answer(db):
    from app.services import mcp_auth_token as m

    assert m.current_token(db) is None
    assert m.mcp_answer(db) == {"enforce": False, "token_sha256": []}
    state = m.describe(db)
    assert state["configured"] is False
    assert state["masked"] is None
    assert state["enforce"] is False


def test_generate_stores_ciphertext_only_and_returns_a_long_random_token(db, actor):
    from app.services import mcp_auth_token as m

    token = m.rotate(db, actor.id)
    assert len(token) >= 32
    row = _row(db)
    assert row.mcp_auth_token_ciphertext and token not in row.mcp_auth_token_ciphertext
    assert m.current_token(db) == token
    assert m.mcp_answer(db) == {"enforce": False, "token_sha256": [_sha(token)]}
    assert m.describe(db)["masked"] == f"****{token[-4:]}"
    assert row.mcp_auth_previous_token_ciphertext is None, "a first token has no previous one"
    assert m.rotate(db, actor.id) != token, "each generate is fresh"


def test_rotate_keeps_the_previous_token_valid_for_the_grace_window(db, actor):
    from app.services import mcp_auth_token as m

    old = m.rotate(db, actor.id)
    new = m.rotate(db, actor.id)
    assert m.current_token(db) == new
    assert m.mcp_answer(db)["token_sha256"] == [_sha(new), _sha(old)]
    until = datetime.fromisoformat(m.describe(db)["previous_valid_until"])
    expected = datetime.now(timezone.utc) + timedelta(hours=m.GRACE_HOURS)
    assert abs((until - expected).total_seconds()) < 60


def test_an_expired_grace_window_drops_the_previous_token(db, actor):
    from app.services import mcp_auth_token as m

    m.rotate(db, actor.id)
    new = m.rotate(db, actor.id)
    row = _row(db)
    row.mcp_auth_previous_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert m.mcp_answer(db)["token_sha256"] == [_sha(new)]
    assert m.describe(db)["previous_valid_until"] is None


def test_revoke_previous_ends_the_grace_window_now(db, actor):
    from app.services import mcp_auth_token as m

    m.rotate(db, actor.id)
    new = m.rotate(db, actor.id)
    m.revoke_previous(db, actor.id)
    assert m.mcp_answer(db)["token_sha256"] == [_sha(new)]


def test_enforce_needs_a_token_first(db, actor):
    from app.services import mcp_auth_token as m

    with pytest.raises(m.EnforceWithoutToken):
        m.set_enforce(db, True, actor.id)
    assert m.mcp_answer(db)["enforce"] is False


def test_enforce_on_and_off(db, actor):
    from app.services import mcp_auth_token as m

    m.rotate(db, actor.id)
    m.set_enforce(db, True, actor.id)
    assert m.mcp_answer(db)["enforce"] is True
    m.set_enforce(db, False, actor.id)
    assert m.mcp_answer(db)["enforce"] is False


def test_a_token_that_no_longer_decrypts_is_unset_and_reported(db, actor):
    from app.services import mcp_auth_token as m

    m.rotate(db, actor.id)
    row = _row(db)
    row.mcp_auth_token_ciphertext = "not-a-fernet-token"
    db.commit()
    assert m.current_token(db) is None
    assert m.mcp_answer(db)["token_sha256"] == []
    assert m.describe(db)["unreadable"] is True


def test_every_action_is_audited_without_a_value(db, actor):
    from app.services import mcp_auth_token as m

    old = m.rotate(db, actor.id)
    new = m.rotate(db, actor.id)
    m.set_enforce(db, True, actor.id)
    m.revoke_previous(db, actor.id)
    rows = _audit_rows(db)
    actions = [r.new_values["action"] for r in sorted(rows, key=lambda r: r.changed_at)]
    assert actions == ["generated", "rotated", "enforce_on", "previous_revoked"]
    dumped = json.dumps([[r.old_values, r.new_values] for r in rows], default=str)
    for secret in (old, new, _sha(old), _sha(new)):
        assert secret not in dumped
    assert all(str(r.user_id) == str(actor.id) for r in rows)


def test_an_enforce_no_op_writes_no_audit_row(db, actor):
    from app.services import mcp_auth_token as m

    m.rotate(db, actor.id)
    m.set_enforce(db, False, actor.id)
    assert len(_audit_rows(db)) == 1


def test_current_token_without_a_session_is_cached(db, actor, monkeypatch):
    """The MCP client reads it per call with no session; one read per TTL, not per call."""
    from app.services import mcp_auth_token as m

    token = m.rotate(db, actor.id)
    reads = []

    class FakeSession:
        def query(self, _model):
            reads.append(1)
            return self

        def first(self):
            return _row(db)

        def close(self):
            pass

    monkeypatch.setattr(m, "SessionLocal", FakeSession)
    assert m.current_token() == token
    assert m.current_token() == token
    assert len(reads) == 1
    m.clear_cache()
    assert m.current_token() == token
    assert len(reads) == 2


# --------------------------------------------------------------------------- settings API


@pytest.fixture
def api(db, actor, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {"id": actor.id, "email": actor.email}
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client, allow
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


_CALLS = [
    ("get", SETTINGS, None),
    ("post", SETTINGS + "/rotate", None),
    ("put", SETTINGS, {"enforce": False}),
    ("post", SETTINGS + "/revoke-previous", None),
]


@pytest.mark.parametrize("method, path, body", _CALLS)
def test_settings_routes_need_the_secrets_slug(api, method, path, body):
    client, allow = api
    allow.update({"user_management.settings.view", "user_management.settings.edit"})
    kwargs = {"json": body} if body is not None else {}
    resp = getattr(client, method)(path, **kwargs)
    assert resp.status_code == 403
    assert SECRETS_SLUG in str(resp.json())


def test_rotate_returns_the_token_once_and_get_never_does(api):
    client, allow = api
    allow.add(SECRETS_SLUG)
    resp = client.post(SETTINGS + "/rotate")
    assert resp.status_code == 200
    token = resp.json()["token"]
    assert len(token) >= 32
    assert resp.json()["configured"] is True
    got = client.get(SETTINGS)
    assert got.status_code == 200
    assert token not in got.text
    assert "token" not in got.json()
    assert got.json()["masked"] == f"****{token[-4:]}"


def test_enforce_before_a_token_is_a_409(api):
    client, allow = api
    allow.add(SECRETS_SLUG)
    resp = client.put(SETTINGS, json={"enforce": True})
    assert resp.status_code == 409


@pytest.mark.parametrize("body", [{}, {"enforce": "yes"}, {"enforce": True, "token": "x" * 40}, ["enforce"]])
def test_put_accepts_only_the_enforce_switch(api, body):
    client, allow = api
    allow.add(SECRETS_SLUG)
    client.post(SETTINGS + "/rotate")
    resp = client.put(SETTINGS, json=body)
    assert resp.status_code == 422
    assert "x" * 40 not in resp.text


def test_enforce_then_revoke_through_the_api(api):
    client, allow = api
    allow.add(SECRETS_SLUG)
    client.post(SETTINGS + "/rotate")
    client.post(SETTINGS + "/rotate")
    assert client.get(SETTINGS).json()["previous_valid_until"] is not None
    on = client.put(SETTINGS, json={"enforce": True})
    assert on.status_code == 200 and on.json()["enforce"] is True
    revoked = client.post(SETTINGS + "/revoke-previous")
    assert revoked.status_code == 200 and revoked.json()["previous_valid_until"] is None


def test_the_general_settings_echo_never_carries_the_ciphertext(api, db, actor):
    from app.services import mcp_auth_token as m

    client, allow = api
    allow.update({SECRETS_SLUG, "user_management.settings.edit"})
    m.rotate(db, actor.id)
    resp = client.put("/api/v1/user-management/settings/general", json={"name": f"{TEST_PREFIX} Co"})
    assert "mcp_auth_token_ciphertext" not in resp.text
    assert "mcp_auth_previous_token_ciphertext" not in resp.text


# --------------------------------------------------------------------------- what the MCP server reads


@pytest.fixture
def mcp_api(db):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_mcp_auth_refuses_a_request_without_an_integration_key(mcp_api):
    resp = mcp_api.get(MCP_AUTH)
    assert resp.status_code in (401, 403)
    assert "token_sha256" not in resp.text


def test_mcp_auth_answers_digests_only_for_an_integration_key(mcp_api, db, actor):
    from app.dependencies import get_current_user_or_api_key, get_external_api_user
    from app.main import app
    from app.services import mcp_auth_token as m

    token = m.rotate(db, actor.id)
    principal = {"id": actor.id}
    # The system router's module guard resolves the caller too.
    app.dependency_overrides[get_external_api_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    try:
        resp = mcp_api.get(MCP_AUTH)
    finally:
        app.dependency_overrides.pop(get_external_api_user, None)
        app.dependency_overrides.pop(get_current_user_or_api_key, None)
    assert resp.status_code == 200
    assert resp.json() == {"enforce": False, "token_sha256": [_sha(token)]}
    assert token not in resp.text
    assert resp.headers.get("cache-control") == "no-store"


def test_mcp_auth_route_carries_the_integration_key_dependency():
    """Structural, like test_external_permission_coverage: the route cannot lose its gate."""
    from fastapi import FastAPI

    from app.api.v1.system import router as system_router
    from app.dependencies import get_external_api_user

    probe = FastAPI()
    probe.include_router(system_router, prefix="/api/v1/system")
    route = next(r for r in probe.routes if getattr(r, "path", "") == MCP_AUTH)
    deps = [d.call for d in route.dependant.dependencies]
    assert get_external_api_user in deps
