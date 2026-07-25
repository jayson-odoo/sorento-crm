"""Unit tests for staff session lifecycle (mint / resolve-slide / revoke).

Self-contained: a blank copy of the real Postgres schema, rolled back at teardown,
so it never leaves anything behind in a real database. Covers the sliding-window
throttle, the 8h vs 30d remember-me split, expiry/revoke/invalid reason codes, and
revoke-all.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

# app.models must finish importing before the service module: the service imports
# app.models.user_session, which pulls in app.dependencies, which imports back
# into the service. Importing the package first breaks that cycle.
import app.models  # noqa: F401  isort:skip

import app.services.user_session_service as svc
from app.models.user import User
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _uid(db) -> str:
    """A real user id.

    user_sessions.user_id is a foreign key, so the row has to exist -- returning a
    bare uuid4 only worked while the fixture had no constraint enforcement.
    """
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{uid[:8]}@sessions.test", name="Session User", status="active"))
    db.commit()
    return uid


def test_mint_remember_gives_30d_rolling(db):
    uid = _uid(db)
    row = svc.mint_session(db, uid, remember=True, user_agent="UA", ip_address="1.2.3.4")
    assert row.rolling is True
    delta = row.expires_at - svc._utcnow()
    assert timedelta(days=29) < delta <= timedelta(days=30, minutes=1)


def test_mint_unchecked_gives_8h_no_roll(db):
    row = svc.mint_session(db, _uid(db), remember=False)
    assert row.rolling is False
    delta = row.expires_at - svc._utcnow()
    assert timedelta(hours=7) < delta <= timedelta(hours=8, minutes=1)


def test_resolve_slides_rolling_session_past_threshold(db):
    row = svc.mint_session(db, _uid(db), remember=True)
    # Pretend it's near expiry (<29d remaining) so the slide fires.
    row.expires_at = svc._utcnow() + timedelta(days=5)
    db.commit()
    resolved = svc.resolve_session(db, row.token)
    assert resolved.expires_at - svc._utcnow() > timedelta(days=29)


def test_resolve_does_not_slide_within_throttle(db):
    row = svc.mint_session(db, _uid(db), remember=True)  # ~30d remaining
    before = row.expires_at
    svc.resolve_session(db, row.token)
    db.refresh(row)
    assert row.expires_at == before  # still >29d away, no rewrite


def test_resolve_never_slides_non_rolling(db):
    row = svc.mint_session(db, _uid(db), remember=False)
    before = row.expires_at
    svc.resolve_session(db, row.token)
    db.refresh(row)
    assert row.expires_at == before


def test_resolve_revoked_raises(db):
    row = svc.mint_session(db, _uid(db), remember=True)
    svc.revoke_session(db, session_id=row.id)
    with pytest.raises(svc.SessionAuthError) as ei:
        svc.resolve_session(db, row.token)
    assert ei.value.reason == svc.REASON_REVOKED


def test_resolve_expired_raises(db):
    row = svc.mint_session(db, _uid(db), remember=False)
    row.expires_at = svc._utcnow() - timedelta(minutes=1)
    db.commit()
    with pytest.raises(svc.SessionAuthError) as ei:
        svc.resolve_session(db, row.token)
    assert ei.value.reason == svc.REASON_EXPIRED


def test_resolve_unknown_token_raises_invalid(db):
    with pytest.raises(svc.SessionAuthError) as ei:
        svc.resolve_session(db, "nope")
    assert ei.value.reason == svc.REASON_INVALID


def test_revoke_all_keeps_current(db):
    uid = _uid(db)
    keep = svc.mint_session(db, uid, remember=True)
    other1 = svc.mint_session(db, uid, remember=True)
    other2 = svc.mint_session(db, uid, remember=False)
    count = svc.revoke_all_for_user(db, uid, except_session_id=keep.id)
    assert count == 2
    db.refresh(keep); db.refresh(other1); db.refresh(other2)
    assert keep.revoked_at is None
    assert other1.revoked_at is not None and other2.revoked_at is not None


def test_last_seen_updates_on_resolve(db):
    row = svc.mint_session(db, _uid(db), remember=True)
    row.last_seen_at = svc._utcnow() - timedelta(hours=1)  # older than the 10m throttle
    db.commit()
    svc.resolve_session(db, row.token, ip_address="9.9.9.9")
    db.refresh(row)
    assert svc._utcnow() - row.last_seen_at < timedelta(minutes=1)
    assert row.ip_address == "9.9.9.9"


@pytest.mark.parametrize("ua,expected", [
    ("Mozilla/5.0 (Macintosh) Chrome/120 Safari/537", "Chrome on macOS"),
    ("Mozilla/5.0 (iPhone) Safari/604", "Safari on iPhone"),
    ("Mozilla/5.0 (Windows NT 10) Firefox/119", "Firefox on Windows"),
    ("", "Unknown device"),
])
def test_device_label(ua, expected):
    assert svc.device_label_from_ua(ua) == expected
