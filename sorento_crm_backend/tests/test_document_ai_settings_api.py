"""The document reader's provider and model round-trip through System Settings.

Both manual builders (CLAUDE.md lesson): the GET dict must carry `document_ai_*`, and
`SystemSettingUpdate` must accept them, or the picker saves and never reads back. A
provider change that does not also name a model clears the model, so a Gemini id is
never posted to OpenAI after a direct PUT.

Runs against a Postgres `blank_session()`; auth is overridden, the gate is not the
subject here (tests/test_settings_app_config_gate.py owns it).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.user import SystemSetting, User
from tests._pg_fixture import blank_session

SETTINGS_GET = "/api/v1/user-management/settings/"
SETTINGS_POST = "/api/v1/user-management/settings/general"
_ACTOR: dict = {"id": None}


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def client(db, monkeypatch):
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.user_service import UserPermissionService

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug
        in {"user_management.settings.view", "user_management.settings.edit"},
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed(db, **columns):
    db.add(SystemSetting(id=str(uuid.uuid4()), name="Co", **columns))
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{uid}@example.com", name="Admin", status="ACTIVE"))
    db.commit()
    _ACTOR["id"] = uid


def _get(client) -> dict:
    r = client.get(SETTINGS_GET)
    assert r.status_code == 200, r.text
    return r.json()["settings"]


def test_the_saved_pair_is_read_back(client, db):
    _seed(db)

    r = client.post(
        SETTINGS_POST,
        json={"document_ai_provider": "gemini", "document_ai_model": "gemini-3.5-flash"},
    )
    assert r.status_code == 200, r.text

    out = _get(client)
    assert out["document_ai_provider"] == "gemini"
    assert out["document_ai_model"] == "gemini-3.5-flash"


def test_a_provider_change_without_a_model_clears_the_model(client, db):
    _seed(db, document_ai_provider="gemini", document_ai_model="gemini-3.5-flash")

    r = client.post(SETTINGS_POST, json={"document_ai_provider": "openai"})
    assert r.status_code == 200, r.text

    out = _get(client)
    assert out["document_ai_provider"] == "openai"
    assert out["document_ai_model"] is None


def test_a_provider_change_that_names_its_model_keeps_it(client, db):
    _seed(db, document_ai_provider="gemini", document_ai_model="gemini-3.5-flash")

    r = client.post(
        SETTINGS_POST, json={"document_ai_provider": "openai", "document_ai_model": "gpt-4o"}
    )
    assert r.status_code == 200, r.text

    out = _get(client)
    assert (out["document_ai_provider"], out["document_ai_model"]) == ("openai", "gpt-4o")
