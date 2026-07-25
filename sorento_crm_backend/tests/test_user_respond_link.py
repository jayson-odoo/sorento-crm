"""TCK-2026-000031 — user<->RespondContact link + phone uniqueness.

Covers AC-31-F1 (resolve), F2 (auto-link + cache + order), F3 (normalised match),
F4 (duplicate phone rejected), F5 (backfill idempotent).

Run: pytest tests/test_user_respond_link.py -v
"""
from __future__ import annotations

import uuid

import pytest

from app.models.access import RespondContact
from app.models.user import User
from app.services.respond_link_service import (
    resolve_user_respond_io_id,
    resolve_user_respond_contact,
)
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _contact(db, phone, io_id="io-1", name="Field Tech"):
    cid = str(uuid.uuid4())
    db.add(RespondContact(id=cid, phone_number=phone, name=name, respond_io_id=io_id, session_vars={}))
    db.commit()
    return cid


def _user(db, *, contact_number=None, respond_contact_id=None, email=None):
    uid = str(uuid.uuid4())
    db.add(User(
        id=uid,
        email=email or f"u{uid[:8]}@test.com",
        name="U",
        contact_number=contact_number,
        respond_contact_id=respond_contact_id,
    ))
    db.commit()
    return uid


def test_explicit_link_resolves(db):
    cid = _contact(db, "60123456789", io_id="io-explicit")
    uid = _user(db, respond_contact_id=cid)
    user = db.query(User).get(uid)
    assert resolve_user_respond_io_id(db, user) == "io-explicit"


def test_phone_match_auto_links_and_caches(db):
    """No explicit link, but contact_number uniquely matches -> resolve + cache."""
    _contact(db, "60123456789", io_id="io-match")
    uid = _user(db, contact_number="60123456789")
    user = db.query(User).get(uid)
    assert user.respond_contact_id is None
    assert resolve_user_respond_io_id(db, user) == "io-match"
    # cached onto the user row
    db.refresh(user)
    assert user.respond_contact_id is not None


def test_resolution_order_explicit_wins(db):
    explicit = _contact(db, "60111111111", io_id="io-explicit")
    _contact(db, "60123456789", io_id="io-phone")
    uid = _user(db, contact_number="60123456789", respond_contact_id=explicit)
    user = db.query(User).get(uid)
    assert resolve_user_respond_io_id(db, user) == "io-explicit"  # not io-phone


def test_no_match_returns_none(db):
    uid = _user(db, contact_number="60999999999")
    user = db.query(User).get(uid)
    assert resolve_user_respond_contact(db, user) is None
    assert resolve_user_respond_io_id(db, user) is None


def test_no_contact_number_returns_none(db):
    uid = _user(db, contact_number=None)
    user = db.query(User).get(uid)
    assert resolve_user_respond_io_id(db, user) is None


def test_duplicate_phone_rejected(db):
    """AC-31-F4: a second user with the same normalised phone is rejected by the service."""
    from app.services.user_service import UserService
    from app.schemas.user import UserUpdate

    _user(db, contact_number="60123456789", email="first@test.com")
    second = _user(db, contact_number=None, email="second@test.com")
    svc = UserService(db)
    with pytest.raises(Exception) as exc:
        svc.update_user(second, UserUpdate(contact_number="0123456789"))  # normalises to 60123456789
    assert "already used" in str(exc.value).lower() or "conflict" in str(type(exc.value)).lower()


def test_backfill_idempotent(db):
    """AC-31-F5: backfill links unique matches; second run changes nothing."""
    import scripts.backfill_user_respond_contact as bf
    # point the script's SessionLocal at our in-memory session
    bf.SessionLocal = lambda: db
    # neutralise close() so the shared fixture session survives the run
    orig_close = db.close
    db.close = lambda: None
    try:
        _contact(db, "60123456789", io_id="io-bf")
        uid = _user(db, contact_number="60123456789")
        first = bf.run()
        assert first["linked"] == 1
        db.refresh(db.query(User).get(uid))
        second = bf.run()
        assert second["linked"] == 0
        assert second["already_linked"] >= 1
    finally:
        db.close = orig_close
