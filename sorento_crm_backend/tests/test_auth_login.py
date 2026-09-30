"""Regression tests for POST /api/v1/auth/login.

`auth.py` had NO tests. That gap let a model change break every login in the
product while 3,776 other tests stayed green: making `users.status` a SQLAlchemy
`Enum` meant the ORM returned a `UserStatus` MEMBER instead of a string, and the
route's guard is

    if str(getattr(user, "status", "") or "") != "ACTIVE":

On Python 3.12+ `str(UserStatus.ACTIVE)` is "UserStatus.ACTIVE", so the check
rejected everyone with 403 "Account not activated". It is a nasty shape because
`user.status == "ACTIVE"` and `user.status.value` both still work - only `str()`
breaks, and it breaks silently by producing a plausible-looking string.

`test_active_user_status_survives_str_conversion` pins that specific mechanism.
The rest cover the login contract: the happy path, both 401s, the 404, and the
403 for a genuinely inactive account.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import app
from app.models.user import User
from tests._pg_fixture import blank_session

PASSWORD = "correct-horse-battery-staple"


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


@pytest.fixture()
def client():
    # A blank copy of the full Postgres schema, rolled back at teardown. Login
    # resolves the user's roles too, so more than `users` has to exist -- the
    # blank schema has every table, so nothing needs listing by hand.
    with blank_session() as db:
        bind = db.get_bind()

        # Helper writes go through their own Session on the SAME connection, so
        # they share the outer transaction (and its search_path) and the route --
        # which reads via the get_db override below -- sees them. create_savepoint
        # keeps their commits scoped to the discarded outer transaction.
        def _session_factory() -> Session:
            return Session(bind=bind, join_transaction_mode="create_savepoint")

        def _override():
            yield db

        app.dependency_overrides[get_db] = _override
        with TestClient(app) as c:
            c._session_factory = _session_factory  # type: ignore[attr-defined]
            yield c
        app.dependency_overrides.pop(get_db, None)


def _make_user(client, *, email: str, password: str = PASSWORD, status: str = "ACTIVE"):
    db = client._session_factory()  # type: ignore[attr-defined]
    try:
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            name="Login Test",
            password=_hash(password),
            status=status,
        )
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def _login(client, email: str, password: str, **extra):
    # Unique IP per call so the shared login throttle cannot bleed across tests.
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, **extra},
        headers={"X-Forwarded-For": f"10.0.0.{uuid.uuid4().int % 250 + 1}"},
    )


def test_active_user_can_log_in(client):
    """The happy path. This alone would have caught the enum regression."""
    email = f"active-{uuid.uuid4().hex[:8]}@example.com"
    _make_user(client, email=email)

    res = _login(client, email, PASSWORD)

    assert res.status_code == 200, res.text
    # The route returns the user record; NextAuth (frontend) mints the JWT.
    assert res.json()["email"] == email


def _session_for(client, token: str):
    from app.models.user_session import UserSession

    db = client._session_factory()  # type: ignore[attr-defined]
    try:
        return db.query(UserSession).filter(UserSession.token == token).one()
    finally:
        db.close()


@pytest.mark.parametrize("extra", [{}, {"remember_me": False}, {"remember_me": True}])
def test_email_login_always_mints_30d_sliding_session(client, extra):
    """SIGNIN-ALWAYS-SLIDE: no remember-me choice. A legacy `remember_me` (even
    False) is accepted and ignored; every email sign-in is the 30-day slide."""
    from app.services.user_session_service import _utcnow

    email = f"slide-{uuid.uuid4().hex[:8]}@example.com"
    _make_user(client, email=email)

    res = _login(client, email, PASSWORD, **extra)

    assert res.status_code == 200, res.text
    row = _session_for(client, res.json()["token"])
    assert row.rolling is True
    assert row.auth_method == "password"
    remaining = row.expires_at - _utcnow()
    assert timedelta(days=29, hours=23) < remaining <= timedelta(days=30, minutes=1)


def test_email_session_slides_on_activity_and_revoke_still_ends_it(client):
    """A day later the session is used, its expiry moves forward; logout revokes it."""
    from app.services.user_session_service import _utcnow

    email = f"slide2-{uuid.uuid4().hex[:8]}@example.com"
    _make_user(client, email=email)
    token = _login(client, email, PASSWORD).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    # Simulate a day passing: pull the expiry back so under 29 days remain.
    db = client._session_factory()  # type: ignore[attr-defined]
    try:
        from app.models.user_session import UserSession

        row = db.query(UserSession).filter(UserSession.token == token).one()
        row.expires_at = row.expires_at - timedelta(days=1, hours=1)
        db.commit()
        pulled_back = row.expires_at
    finally:
        db.close()

    assert client.get("/api/v1/auth/sessions", headers=auth).status_code == 200
    slid = _session_for(client, token).expires_at
    assert slid > pulled_back
    assert slid - _utcnow() > timedelta(days=29, hours=23)

    assert client.post("/api/v1/auth/logout", headers=auth).status_code in (200, 204)
    res = client.get("/api/v1/auth/sessions", headers=auth)
    assert res.status_code == 401
    assert _session_for(client, token).revoked_at is not None


def test_active_user_status_survives_str_conversion(client):
    """Pins the exact mechanism that broke login.

    The route compares ``str(user.status) != "ACTIVE"``. If `User.status` is ever
    redeclared as a SQLAlchemy ``Enum``, the ORM hands back a ``UserStatus``
    member whose ``str()`` is "UserStatus.ACTIVE" - and every login 403s. Assert
    on the round-tripped value, not on the literal we wrote.
    """
    email = f"strcheck-{uuid.uuid4().hex[:8]}@example.com"
    _make_user(client, email=email)

    db = client._session_factory()  # type: ignore[attr-defined]
    try:
        stored = db.query(User).filter(User.email == email).first()
        rendered = str(getattr(stored, "status", "") or "")
    finally:
        db.close()

    assert rendered == "ACTIVE", (
        f"str(user.status) renders as {rendered!r}, so auth.py's guard "
        '`str(user.status) != "ACTIVE"` will reject every login with 403. '
        "User.status must stay a plain String column, or every `.status` read "
        "has to be audited first."
    )


def test_inactive_user_is_rejected(client):
    email = f"inactive-{uuid.uuid4().hex[:8]}@example.com"
    _make_user(client, email=email, status="INACTIVE")

    res = _login(client, email, PASSWORD)

    assert res.status_code == 403
    assert "not activated" in res.text.lower()


def test_wrong_password_is_rejected(client):
    email = f"wrongpw-{uuid.uuid4().hex[:8]}@example.com"
    _make_user(client, email=email)

    res = _login(client, email, "not-the-password")

    assert res.status_code == 401
    assert "invalid credentials" in res.text.lower()


def test_unknown_email_is_rejected(client):
    """identity S1, AC-26: an unknown email must no longer answer 404 (that
    enumerates which emails exist) - it answers the same 401 a wrong password
    gets. This assertion is the defect AC-26 fixes; it used to read
    `assert res.status_code == 404`."""
    res = _login(client, f"nobody-{uuid.uuid4().hex[:8]}@example.com", PASSWORD)

    assert res.status_code == 401
    assert res.json().get("detail") == "Invalid credentials."


def test_ac26_unknown_email_and_wrong_password_get_identical_401_body(client):
    email = f"knownuser-{uuid.uuid4().hex[:8]}@example.com"
    _make_user(client, email=email)

    unknown_resp = _login(client, f"nobody-{uuid.uuid4().hex[:8]}@example.com", PASSWORD)
    wrong_pw_resp = _login(client, email, "not-the-password")

    assert unknown_resp.status_code == wrong_pw_resp.status_code == 401
    assert unknown_resp.json() == wrong_pw_resp.json() == {"detail": "Invalid credentials."}


def test_ac26_trashed_user_with_right_password_is_401():
    """A trashed user must not be able to log in even with the correct
    password - login() today has no is_trashed check at all, so this fails
    with a 200 until AC-26 adds one."""
    from app.database import get_db as _get_db

    with blank_session() as db:
        email = f"trashed-{uuid.uuid4().hex[:8]}@example.com"
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            name="Trashed User",
            password=_hash(PASSWORD),
            status="ACTIVE",
            is_trashed=True,
        )
        db.add(user)
        db.commit()

        def _override():
            yield db

        app.dependency_overrides[_get_db] = _override
        try:
            with TestClient(app) as c:
                res = c.post(
                    "/api/v1/auth/login",
                    json={"email": email, "password": PASSWORD},
                    headers={"X-Forwarded-For": f"10.0.9.{uuid.uuid4().int % 250 + 1}"},
                )
        finally:
            app.dependency_overrides.pop(_get_db, None)

    assert res.status_code == 401, res.text
    assert res.json().get("detail") == "Invalid credentials."


def test_user_without_a_password_cannot_log_in(client):
    """OAuth-only accounts have no password hash and must not authenticate."""
    email = f"nopw-{uuid.uuid4().hex[:8]}@example.com"
    db = client._session_factory()  # type: ignore[attr-defined]
    try:
        db.add(
            User(
                id=str(uuid.uuid4()),
                email=email,
                name="No Password",
                password="",
                status="ACTIVE",
            )
        )
        db.commit()
    finally:
        db.close()

    res = _login(client, email, PASSWORD)

    assert res.status_code == 401
