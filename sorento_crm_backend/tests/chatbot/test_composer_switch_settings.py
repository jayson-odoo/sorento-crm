"""CHAT-RELEASE-1021 (owner, 21 Oct 2026): the release is inert until the owner flips it.

The reply composer was an env flag (`CHAT_COMPOSER_ENABLED`); it is now also a settings
column, `system_settings.chatbot_composer_enabled` (default off), read at run time so the
owner flips it from Settings > Chatbot with no restart. The env var, when SET, still wins
(the rollback lever). The closed lists mode (`block` | `index`) rides the same screen.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.config import settings
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.main import app
from app.models.user import SystemSetting
from app.services.chatbot import composers
from app.services.user_service import UserPermissionService
from tests._pg_fixture import TEST_PREFIX, blank_session

SETTINGS = "/api/v1/user-management/settings/"
GENERAL = "/api/v1/user-management/settings/general"
APP_DIR = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _client(db, monkeypatch, allow):
    def _override_db():
        yield db

    actor = {"id": str(uuid.uuid4()), "email": "composer-switch@zzt.test", "name": "ZZT"}
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in allow
    )
    monkeypatch.setattr(UserPermissionService, "get_user_permission_slugs", lambda self, uid: set(allow))
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def api(db, monkeypatch):
    try:
        yield _client(db, monkeypatch, {"user_management.settings.view", "user_management.settings.edit"})
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def viewer(db, monkeypatch):
    try:
        yield _client(db, monkeypatch, {"user_management.settings.view"})
    finally:
        app.dependency_overrides.clear()


def _row(db, **values) -> SystemSetting:
    row = SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} Co", **values)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --------------------------------------------------------------------------- #
# The column and the settings API
# --------------------------------------------------------------------------- #


def test_the_composer_column_defaults_off(db):
    assert _row(db).chatbot_composer_enabled is False


def test_get_settings_reports_both_switches_at_their_defaults(api, db):
    _row(db)
    body = api.get(SETTINGS).json()["settings"]
    assert body["chatbot_composer_enabled"] is False
    assert body["chatbot_closed_lists_mode"] == "block"


def test_both_switches_round_trip_through_put_general(api, db):
    _row(db)
    resp = api.put(GENERAL, json={"chatbot_composer_enabled": True, "chatbot_closed_lists_mode": "index"})
    assert resp.status_code == 200, resp.text
    body = api.get(SETTINGS).json()["settings"]
    assert body["chatbot_composer_enabled"] is True
    assert body["chatbot_closed_lists_mode"] == "index"

    resp = api.put(GENERAL, json={"chatbot_composer_enabled": False, "chatbot_closed_lists_mode": "block"})
    assert resp.status_code == 200, resp.text
    body = api.get(SETTINGS).json()["settings"]
    assert body["chatbot_composer_enabled"] is False
    assert body["chatbot_closed_lists_mode"] == "block"


def test_the_screen_save_path_post_general_writes_the_composer_too(api, db):
    _row(db)
    resp = api.post(GENERAL, json={"chatbot_composer_enabled": True})
    assert resp.status_code == 200, resp.text
    assert api.get(SETTINGS).json()["settings"]["chatbot_composer_enabled"] is True


@pytest.mark.parametrize("bad", ["Index", "full", ""])
def test_a_closed_lists_mode_outside_the_two_is_refused(api, db, bad):
    _row(db)
    assert api.put(GENERAL, json={"chatbot_closed_lists_mode": bad}).status_code == 422


def test_an_explicit_null_composer_leaves_the_stored_value(api, db):
    _row(db, chatbot_composer_enabled=True)
    resp = api.put(GENERAL, json={"chatbot_composer_enabled": None})
    assert resp.status_code == 200, resp.text
    assert api.get(SETTINGS).json()["settings"]["chatbot_composer_enabled"] is True


def test_flipping_needs_the_settings_edit_permission(viewer, db):
    _row(db)
    assert viewer.put(GENERAL, json={"chatbot_composer_enabled": True}).status_code == 403
    assert viewer.post(GENERAL, json={"chatbot_closed_lists_mode": "index"}).status_code == 403


def test_a_save_drops_this_process_cached_composer_value(api, db, monkeypatch):
    _row(db)
    cleared: list[bool] = []
    monkeypatch.setattr(composers, "clear_cache", lambda: cleared.append(True))
    assert api.put(GENERAL, json={"chatbot_composer_enabled": True}).status_code == 200
    assert cleared, "PUT /settings/general must drop the cached composer switch"


# --------------------------------------------------------------------------- #
# The gate: env override when set, else the stored switch, read at run time
# --------------------------------------------------------------------------- #


def test_the_env_var_is_unset_by_default(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("CHAT_COMPOSER_ENABLED", raising=False)
    assert Settings().chat_composer_enabled is None
    monkeypatch.setenv("CHAT_COMPOSER_ENABLED", "false")
    assert Settings().chat_composer_enabled is False


@pytest.mark.parametrize("stored", [False, True])
def test_unset_env_reads_the_stored_switch(db, monkeypatch, stored):
    _row(db, chatbot_composer_enabled=stored)
    monkeypatch.setattr(settings, "chat_composer_enabled", None, raising=False)
    composers.clear_cache()
    assert composers.enabled(db) is stored


@pytest.mark.parametrize("override,stored", [(False, True), (True, False)])
def test_a_set_env_var_wins_over_the_stored_switch(db, monkeypatch, override, stored):
    _row(db, chatbot_composer_enabled=stored)
    monkeypatch.setattr(settings, "chat_composer_enabled", override, raising=False)
    composers.clear_cache()
    assert composers.enabled(db) is override


def test_a_flip_reaches_the_next_read_with_no_restart(db, monkeypatch):
    row = _row(db, chatbot_composer_enabled=False)
    monkeypatch.setattr(settings, "chat_composer_enabled", None, raising=False)
    composers.clear_cache()
    assert composers.enabled(db) is False
    row.chatbot_composer_enabled = True
    db.commit()
    assert composers.enabled(db) is True


def test_no_settings_row_reads_off(db, monkeypatch):
    monkeypatch.setattr(settings, "chat_composer_enabled", None, raising=False)
    composers.clear_cache()
    assert composers.enabled(db) is False


def test_the_stored_switch_is_read_through_the_cache_without_a_session(monkeypatch):
    """No caller passes a session: the cache answers inside its window, one read per window."""
    monkeypatch.setattr(settings, "chat_composer_enabled", None, raising=False)
    reads: list[int] = []
    monkeypatch.setattr(composers, "_read_stored", lambda db=None: reads.append(1) or True)
    composers.clear_cache()
    assert composers.enabled() is True
    assert composers.enabled() is True
    assert len(reads) == 1
    composers.clear_cache()
    assert composers.enabled() is True
    assert len(reads) == 2


def test_only_the_gate_reads_the_composer_setting():
    """Every caller asks `composers.enabled()`; a direct `settings.chat_composer_enabled`
    read elsewhere would skip the stored switch and stay off whatever the screen says."""
    allowed = {APP_DIR / "config.py", APP_DIR / "services" / "chatbot" / "composers" / "__init__.py"}
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in APP_DIR.rglob("*.py")
        if path not in allowed and "chat_composer_enabled" in path.read_text()
    ]
    assert not offenders, offenders
