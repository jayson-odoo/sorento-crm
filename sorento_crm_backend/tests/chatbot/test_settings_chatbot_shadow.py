"""AC-1028: `system_settings.chatbot_parser_shadow_version` reaches both settings surfaces.

A new settings column that lands on only one of the two manual dict builders never
reaches the screen (LESSONS-LEARNT: "a new DB column must be added to BOTH manual dict
builders"). Same harness as `tests/test_default_uom_setting.py`: TestClient with `get_db`
and `get_current_user` overridden onto a blank schema, permission checks monkeypatched.

RED: `chatbot_parser_shadow_version` is on neither the GET dict
(`app/api/v1/user_management/settings.py`'s `get_settings`) nor `SystemSettingUpdate`, the
column does not exist on `SystemSetting`, and `INGRESS_KINDS` has no `"shadow"` member.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.user import SystemSetting
from app.services.chatbot.contracts import INGRESS_KINDS
from tests._pg_fixture import blank_session

SETTINGS_ENDPOINT = "/api/v1/user-management/settings/"
SETTINGS_GENERAL_ENDPOINT = "/api/v1/user-management/settings/general"
_SETTINGS_PERMISSIONS = {
    "user_management.settings.view",
    "user_management.settings.edit",
}
MARKER = "ZZTSHADOW"


@pytest.fixture()
def db():
    with blank_session() as s:
        yield s


@pytest.fixture()
def settings_api(db, monkeypatch):
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    user = {"id": str(uuid.uuid4()), "email": "shadow-settings-caller@zzt.test"}

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: user

    async def _scope():
        from app.models.base import set_company_scope

        set_company_scope(db, None)
        return None

    app.dependency_overrides[apply_company_scope] = _scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in _SETTINGS_PERMISSIONS,
    )
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(apply_company_scope, None)


def _seed_settings_row(db) -> None:
    db.add(SystemSetting(id=str(uuid.uuid4()), name=f"{MARKER} Co"))
    db.commit()


def _seed_prompt_version(db, *, name: str = "chatbot_semantic_parser", version: int = 3) -> None:
    """A real `ai_prompt_versions` row the PUT's `resolve_shadow_version` can find - the
    endpoint validates the version exists (422 otherwise) rather than saving a name
    nothing shadows."""
    from app.models.ai_prompt import AIPromptVersion

    db.add(
        AIPromptVersion(
            id=str(uuid.uuid4()),
            name=name,
            version=version,
            type="text",
            template=f"{MARKER} prompt body",
            variables=[],
        )
    )
    db.commit()


class TestBothDictBuildersCarryTheColumn:
    def test_get_carries_the_field_before_anybody_sets_it(self, settings_api, db):
        _seed_settings_row(db)
        body = settings_api.get(SETTINGS_ENDPOINT).json()["settings"]
        assert "chatbot_parser_shadow_version" in body, (
            f"GET settings dict has no chatbot_parser_shadow_version key (keys="
            f"{sorted(body)})"
        )
        assert body["chatbot_parser_shadow_version"] is None

    def test_the_put_path_round_trips_the_version(self, settings_api, db):
        _seed_settings_row(db)
        _seed_prompt_version(db)
        saved = settings_api.post(
            SETTINGS_GENERAL_ENDPOINT,
            json={"chatbot_parser_shadow_version": "chatbot_semantic_parser@3"},
        )
        assert saved.status_code == 200, saved.text

        body = settings_api.get(SETTINGS_ENDPOINT).json()["settings"]
        assert body["chatbot_parser_shadow_version"] == "chatbot_semantic_parser@3"

    def test_a_version_that_does_not_exist_is_422(self, settings_api, db):
        """AC-1027: a shadow version naming nothing is refused at the PUT, not saved and
        left producing a row of `failed` shadow parses nobody is watching."""
        _seed_settings_row(db)
        resp = settings_api.post(
            SETTINGS_GENERAL_ENDPOINT,
            json={"chatbot_parser_shadow_version": "chatbot_semantic_parser@999"},
        )
        assert resp.status_code == 422, resp.text

        body = settings_api.get(SETTINGS_ENDPOINT).json()["settings"]
        assert body["chatbot_parser_shadow_version"] is None, (
            "a rejected version must not be saved"
        )

    def test_it_can_be_cleared(self, settings_api, db):
        _seed_settings_row(db)
        _seed_prompt_version(db)
        settings_api.post(
            SETTINGS_GENERAL_ENDPOINT,
            json={"chatbot_parser_shadow_version": "chatbot_semantic_parser@3"},
        )
        cleared = settings_api.post(
            SETTINGS_GENERAL_ENDPOINT, json={"chatbot_parser_shadow_version": None}
        )
        assert cleared.status_code == 200, cleared.text
        body = settings_api.get(SETTINGS_ENDPOINT).json()["settings"]
        assert body["chatbot_parser_shadow_version"] is None


class TestIngressKindsHasShadow:
    def test_ingress_kinds_contains_shadow(self):
        assert "shadow" in INGRESS_KINDS, (
            f"INGRESS_KINDS is {INGRESS_KINDS}, expected 'shadow' among them"
        )
