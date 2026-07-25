"""Form handling-lock — settings + get_me round-trip (§12 P2-14).

Guards the two "manual dict builder drops fields" gotchas (CLAUDE.md):

1. SETTINGS: ``handling_lock_enabled_types`` must round-trip list-in -> CSV-stored
   -> list-out through the singleton ``system_settings`` GET dict AND
   ``SystemSettingUpdate`` (POST /general). Unknown / non-form types are dropped,
   dupes de-duped. Empty list clears the flag.
2. USER: ``notify_email_on_handling`` / ``notify_whatsapp_on_handling`` must appear
   in the ``get_me`` payload (they are set by the manual dict builder in
   users.get_current_user_profile, not merely inherited on UserResponse — the
   builder silently drops any field it doesn't list).

Runs against an in-memory sqlite bind. Auth deps are overridden; the settings
route hits the real GET dict + PUT/POST impl; get_me hits the real UserService +
manual dict builder + UserResponse.

Run: venv/bin/pytest tests/test_form_handling_lock_settings_me.py -q
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.user import SystemSetting, User
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


_ACTOR: dict = {"id": None}


@pytest.fixture
def client(db):
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# =========================================================================== #
# Settings round-trip                                                          #
# =========================================================================== #
SETTINGS_GET = "/api/v1/user-management/settings/"
SETTINGS_POST = "/api/v1/user-management/settings/general"


def _seed_settings(db):
    db.add(SystemSetting(id=str(uuid.uuid4()), name="Co", handling_lock_enabled_types=""))
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email="admin@t.com", name="Admin", status="ACTIVE"))
    db.commit()
    _ACTOR["id"] = uid
    return uid


def test_settings_list_in_csv_stored_list_out(client, db):
    _seed_settings(db)

    # list in -> POST /general
    r = client.post(
        SETTINGS_POST,
        json={"handling_lock_enabled_types": ["complaint", "purchase_request"]},
    )
    assert r.status_code == 200, r.text

    # CSV stored on the singleton column.
    row = db.query(SystemSetting).first()
    assert row.handling_lock_enabled_types == "complaint,purchase_request"

    # list out -> GET
    r = client.get(SETTINGS_GET)
    assert r.status_code == 200, r.text
    out = r.json()["settings"]["handling_lock_enabled_types"]
    assert out == ["complaint", "purchase_request"]


def test_settings_drops_unknown_and_dedupes(client, db):
    _seed_settings(db)
    r = client.post(
        SETTINGS_POST,
        json={
            "handling_lock_enabled_types": [
                "complaint",
                "complaint",  # dupe
                "not_a_form",  # not in FORM_SLA_TYPES
                "stock_inquiry",
            ]
        },
    )
    assert r.status_code == 200, r.text
    row = db.query(SystemSetting).first()
    assert row.handling_lock_enabled_types == "complaint,stock_inquiry"


def test_settings_empty_list_clears_flag(client, db):
    _seed_settings(db)
    db.query(SystemSetting).first().handling_lock_enabled_types = "complaint"
    db.commit()

    r = client.post(SETTINGS_POST, json={"handling_lock_enabled_types": []})
    assert r.status_code == 200, r.text
    assert db.query(SystemSetting).first().handling_lock_enabled_types == ""

    r = client.get(SETTINGS_GET)
    assert r.json()["settings"]["handling_lock_enabled_types"] == []


# =========================================================================== #
# get_me user toggles                                                          #
# =========================================================================== #
ME = "/api/v1/user-management/users/me"


def test_get_me_includes_handling_toggles_non_default(client, db):
    """Set NON-default values so a pass proves the values round-trip, not that the
    UserResponse defaults happen to match."""
    uid = str(uuid.uuid4())
    db.add(
        User(
            id=uid,
            email="member@t.com",
            name="Member",
            status="ACTIVE",
            notify_email_on_handling=False,   # default is True
            notify_whatsapp_on_handling=True,  # default is False
        )
    )
    db.commit()
    _ACTOR["id"] = uid

    r = client.get(ME)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "notify_email_on_handling" in body
    assert "notify_whatsapp_on_handling" in body
    assert body["notify_email_on_handling"] is False
    assert body["notify_whatsapp_on_handling"] is True
