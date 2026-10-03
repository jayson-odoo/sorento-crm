"""DEV-LOGIN-BYPASS: the dev auto-login endpoints and every guard in front of them.

Plan: documentation/plans/identity/PLAN-dev-login-bypass-03oct.md (UAC alongside).

The happy path runs only when EVERY guard holds. Each kill test below turns exactly one
guard off and proves the route then answers the same plain 404 an absent route gives, so a
single dropped check fails a test instead of silently opening a passwordless sign-in.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.main import app
from app.models.user import User
from app.services import dev_login
from tests._pg_fixture import blank_session

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

LOCAL_BASE = "http://localhost:8123"
LOOPBACK_PEER = ("127.0.0.1", 50123)


@pytest.fixture()
def db_bind():
    with blank_session() as db:
        bind = db.get_bind()

        def _override():
            yield db

        app.dependency_overrides[get_db] = _override
        try:
            yield db, bind
        finally:
            app.dependency_overrides.pop(get_db, None)


def _client(*, base_url: str = LOCAL_BASE, peer=LOOPBACK_PEER) -> TestClient:
    return TestClient(app, base_url=base_url, client=peer)


def _make_user(bind, *, email: str, status: str = "ACTIVE", trashed: bool = False) -> str:
    db = Session(bind=bind, join_transaction_mode="create_savepoint")
    try:
        user = User(id=str(uuid.uuid4()), email=email, name=f"Dev {email.split('@')[0]}", status=status)
        if trashed:
            user.is_trashed = True
        db.add(user)
        db.commit()
        return str(user.id)
    finally:
        db.close()


@pytest.fixture()
def enabled(monkeypatch, db_bind):
    """Every guard on, two allowlisted ACTIVE users. Kill tests flip one thing off."""
    _db, bind = db_bind
    admin = f"devadmin-{uuid.uuid4().hex[:8]}@example.com"
    viewer = f"devview-{uuid.uuid4().hex[:8]}@example.com"
    _make_user(bind, email=admin)
    _make_user(bind, email=viewer)
    monkeypatch.setattr(settings, "dev_auto_login", True)
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "dev_auto_login_users", f"{admin}, {viewer.upper()}")
    return {"admin": admin, "viewer": viewer, "bind": bind}


def _dev_login(client: TestClient, email: str):
    return client.post("/api/v1/auth/dev-login", json={"email": email})


# --------------------------------------------------------------------------- happy path


def test_dev_login_mints_a_real_session_that_authenticates(enabled):
    with _client() as c:
        res = _dev_login(c, enabled["admin"])
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["email"] == enabled["admin"]
        token = body["token"]
        assert token

        # The same opaque session the password login issues: get_current_user resolves it.
        me = c.get("/api/v1/test-auth", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text

    from app.models.user_session import UserSession

    db = Session(bind=enabled["bind"], join_transaction_mode="create_savepoint")
    try:
        row = db.query(UserSession).filter(UserSession.token == token).one()
        assert row.auth_method == "dev_login"
        assert row.rolling is True
    finally:
        db.close()


def test_dev_login_users_lists_only_the_allowlist_default_first(enabled):
    with _client() as c:
        res = c.get("/api/v1/auth/dev-login/users")
    assert res.status_code == 200, res.text
    emails = [u["email"] for u in res.json()["users"]]
    assert emails == [enabled["admin"], enabled["viewer"]]
    assert set(res.json()["users"][0]) == {"email", "name", "role_name"}


def test_email_match_is_case_insensitive(enabled):
    with _client() as c:
        assert _dev_login(c, enabled["viewer"].upper()).status_code == 200


@pytest.mark.parametrize("host", ["http://localhost:3101", "http://lane-a.localhost:8101", "http://127.0.0.1:8000"])
def test_each_local_host_form_is_accepted(enabled, host):
    with _client(base_url=host) as c:
        assert _dev_login(c, enabled["admin"]).status_code == 200


# --------------------------------------------------------------------------- kill tests


def _assert_404_both(c: TestClient, email: str):
    assert _dev_login(c, email).status_code == 404
    assert c.get("/api/v1/auth/dev-login/users").status_code == 404


def test_kill_flag_off(enabled, monkeypatch):
    monkeypatch.setattr(settings, "dev_auto_login", False)
    with _client() as c:
        _assert_404_both(c, enabled["admin"])


def test_flag_defaults_off():
    from app.config import Settings

    fresh = Settings(database_url="postgresql://x:x@localhost/x", jwt_secret="x", _env_file=None)
    assert fresh.dev_auto_login is False


@pytest.mark.parametrize("env", ["production", "PRODUCTION", "prod", "staging", "", "qa", "productionish"])
def test_kill_environment_not_allowlisted(enabled, monkeypatch, env):
    monkeypatch.setattr(settings, "environment", env)
    with _client() as c:
        _assert_404_both(c, enabled["admin"])


@pytest.mark.parametrize(
    "host",
    [
        "http://sorento.example.com",
        "http://localhost.evil.com",
        "http://evillocalhost",
        "http://127.0.0.2",
        "http://10.0.0.5:8000",
        "http://backend:8000",
    ],
)
def test_kill_host_not_local(enabled, host):
    with _client(base_url=host) as c:
        _assert_404_both(c, enabled["admin"])


@pytest.mark.parametrize("peer", [("10.0.0.7", 5000), ("172.18.0.3", 5000), ("testclient", 5000)])
def test_kill_peer_not_loopback(enabled, peer):
    with _client(peer=peer) as c:
        _assert_404_both(c, enabled["admin"])


def test_kill_forwarded_for_does_not_fake_loopback(enabled):
    with _client(peer=("10.0.0.7", 5000)) as c:
        res = c.post(
            "/api/v1/auth/dev-login",
            json={"email": enabled["admin"]},
            headers={"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"},
        )
    assert res.status_code == 404


def test_kill_email_not_allowlisted(enabled):
    other = f"notlisted-{uuid.uuid4().hex[:8]}@example.com"
    _make_user(enabled["bind"], email=other)
    with _client() as c:
        assert _dev_login(c, other).status_code == 404


def test_kill_empty_allowlist(enabled, monkeypatch):
    monkeypatch.setattr(settings, "dev_auto_login_users", "")
    with _client() as c:
        _assert_404_both(c, enabled["admin"])


@pytest.mark.parametrize("kind", ["inactive", "trashed"])
def test_kill_allowlisted_but_not_signable(enabled, monkeypatch, kind):
    email = f"{kind}-{uuid.uuid4().hex[:8]}@example.com"
    _make_user(enabled["bind"], email=email, status="INACTIVE" if kind == "inactive" else "ACTIVE",
               trashed=kind == "trashed")
    monkeypatch.setattr(settings, "dev_auto_login_users", f"{enabled['admin']},{email}")
    with _client() as c:
        assert _dev_login(c, email).status_code == 404
        listed = [u["email"] for u in c.get("/api/v1/auth/dev-login/users").json()["users"]]
    assert email not in listed


# --------------------------------------------------------------------------- guard unit truth table


@pytest.mark.parametrize(
    "host,ok",
    [
        ("localhost", True),
        ("localhost:3101", True),
        ("LocalHost:3101", True),
        ("lane-a.localhost:3101", True),
        ("127.0.0.1:8000", True),
        ("", False),
        (None, False),
        ("localhost.", False),
        ("localhost.evil.com", False),
        ("evil.com:localhost", False),
        ("a.b.localhost.com", False),
        ("[::1]:8000", False),
        ("0.0.0.0", False),
    ],
)
def test_is_local_host(host, ok):
    assert dev_login.is_local_host(host) is ok


@pytest.mark.parametrize(
    "ip,ok",
    [("127.0.0.1", True), ("::1", True), ("10.0.0.1", False), ("testclient", False), ("", False), (None, False)],
)
def test_is_loopback_peer(ip, ok):
    assert dev_login.is_loopback_peer(ip) is ok


# --------------------------------------------------------------------------- startup assertion


@pytest.mark.parametrize("env", ["production", "prod", "staging", "", "qa"])
def test_startup_assertion_refuses_non_dev_environment(env):
    with pytest.raises(RuntimeError, match="DEV_AUTO_LOGIN"):
        dev_login.assert_safe_startup(enabled=True, environment=env)


def test_startup_assertion_passes_when_off_in_production():
    dev_login.assert_safe_startup(enabled=False, environment="production")


def test_startup_assertion_warns_loudly_when_active(caplog):
    with caplog.at_level("WARNING"):
        dev_login.assert_safe_startup(enabled=True, environment="development")
    assert any("DEV_AUTO_LOGIN" in r.getMessage() and r.levelname == "WARNING" for r in caplog.records)


def test_kill_app_import_crashes_with_flag_in_production():
    """The real process, not the helper: importing app.main must die."""
    env = {**os.environ, "DEV_AUTO_LOGIN": "true", "ENVIRONMENT": "production"}
    proc = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode != 0
    assert "DEV_AUTO_LOGIN" in (proc.stderr + proc.stdout)


# --------------------------------------------------------------------------- deploy guard


def _deploy_files() -> list[Path]:
    files: list[Path] = []
    files += sorted((REPO_ROOT / ".github" / "workflows").glob("*.y*ml"))
    files += sorted(REPO_ROOT.glob("**/docker-compose*.y*ml"))
    files += sorted(REPO_ROOT.glob("**/Dockerfile*"))
    for pattern in ("**/.env.production*", "**/.env.prod*", "**/.env.staging*"):
        files += sorted(REPO_ROOT.glob(pattern))
    files += [REPO_ROOT / "sorento_crm" / "deploy.sh"]
    skip = ("node_modules", "/venv/", "/.next/")
    return [f for f in dict.fromkeys(files) if f.is_file() and not any(s in str(f) for s in skip)]


def test_deploy_files_never_mention_the_flag():
    files = _deploy_files()
    assert any(f.name == "docker-compose.yml" for f in files)
    assert any(f.parent.name == "workflows" for f in files)
    offenders = [str(f.relative_to(REPO_ROOT)) for f in files if re.search(r"DEV_AUTO_LOGIN", f.read_text(errors="ignore"))]
    assert offenders == [], f"DEV_AUTO_LOGIN must never be set by a deploy/CI file: {offenders}"
