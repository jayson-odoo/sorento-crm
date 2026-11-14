"""UI-V2 phase 0, slice S1: theme storage (UAC C-5, C-6, and the B-5 read side).

Mode is per user (``users.theme_mode``); the brand is per company
(``system_settings.theme``, written through ``PUT /settings/general``, read by any signed-in user
through ``GET /settings/app-config``). The backend stores the input only, never colours.

Run:
    SORENTO_ENV_FILE=.env.ci-tests venv/bin/python -m pytest tests/test_ui_v2_theme_settings.py -q
"""
from __future__ import annotations

import uuid

import pytest

from app.models.user import SystemSetting, User
from tests._ai_usage_client import api_client
from tests._pg_fixture import TEST_PREFIX, blank_session

SETTINGS_EDIT = "user_management.settings.edit"

ME = "/api/v1/user-management/users/me"
THEME_MODE = f"{ME}/theme-mode"
SETTINGS = "/api/v1/user-management/settings"
GENERAL = f"{SETTINGS}/general"
APP_CONFIG = f"{SETTINGS}/app-config"

DEFAULT_THEME = {"preset": "sorento-blue", "custom_hex": None}


@pytest.fixture
def db():
    with blank_session() as session:
        yield session
        session.rollback()


def _seed_company(db) -> None:
    db.add(SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} Theme Co"))
    db.commit()


def _seed_user(db, client) -> str:
    uid = client.actor["id"]
    db.add(
        User(
            id=uid,
            email=client.actor["email"],
            name=f"{TEST_PREFIX} Theme User",
            status="ACTIVE",
        )
    )
    db.commit()
    return uid


# --------------------------------------------------------------------------- #
# C-5 - PUT /me/theme-mode                                                      #
# --------------------------------------------------------------------------- #


def test_put_theme_mode(db):
    with api_client(db, []) as client:  # any signed-in user may set their own
        _seed_company(db)
        _seed_user(db, client)
        assert client.get(ME).json()["theme_mode"] == "system"
        for mode in ("light", "dark", "system"):
            r = client.put(THEME_MODE, json={"theme_mode": mode})
            assert r.status_code == 200, mode
            assert client.get(ME).json()["theme_mode"] == mode
        client.put(THEME_MODE, json={"theme_mode": "dark"})
        bad = client.put(THEME_MODE, json={"theme_mode": "blue"})
        assert bad.status_code == 422
        assert client.get(ME).json()["theme_mode"] == "dark"


# --------------------------------------------------------------------------- #
# C-6 - the company brand                                                       #
# --------------------------------------------------------------------------- #


def test_settings_theme_write_and_app_config_read(db):
    _seed_company(db)

    with api_client(db, [SETTINGS_EDIT]) as editor:
        preset = editor.put(GENERAL, json={"theme": {"preset": "teal", "custom_hex": None}})
        assert preset.status_code == 200
        after_preset = editor.get(APP_CONFIG).json()

        custom = editor.put(
            GENERAL, json={"theme": {"preset": "sorento-blue", "custom_hex": "#12ab3f"}}
        )
        assert custom.status_code == 200
        after_custom = editor.get(APP_CONFIG).json()

        for bad in (
            {"preset": "sorento-blue", "custom_hex": "#12345"},
            {"preset": "sorento-blue", "custom_hex": "red"},
            {"preset": "neon", "custom_hex": None},
        ):
            r = editor.put(GENERAL, json={"theme": bad})
            assert r.status_code == 422, bad

    assert after_preset["theme"] == {"preset": "teal", "custom_hex": None}
    assert after_custom["theme"]["preset"] == "sorento-blue"
    assert after_custom["theme"]["custom_hex"].lower() == "#12ab3f"

    # a non-editor is refused, but still reads the stored brand
    with api_client(db, []) as viewer:
        denied = viewer.put(GENERAL, json={"theme": {"preset": "indigo", "custom_hex": None}})
        assert denied.status_code == 403
        seen = viewer.get(APP_CONFIG)
    assert seen.status_code == 200
    assert seen.json()["theme"]["custom_hex"].lower() == "#12ab3f"
    assert seen.json()["theme"]["preset"] == "sorento-blue"


def test_app_config_has_ui_v2_enabled(db):
    _seed_company(db)

    with api_client(db, []) as anyone:
        before = anyone.get(APP_CONFIG)
    assert before.status_code == 200
    assert before.json()["ui_v2_enabled"] is True
    assert before.json()["theme"] == DEFAULT_THEME

    with api_client(db, [SETTINGS_EDIT]) as editor:
        assert editor.put(GENERAL, json={"ui_v2_enabled": False}).status_code == 200

    with api_client(db, []) as anyone:
        after = anyone.get(APP_CONFIG)
    assert after.status_code == 200
    assert after.json()["ui_v2_enabled"] is False
