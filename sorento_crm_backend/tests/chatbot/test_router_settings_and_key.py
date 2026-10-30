"""AGENTIC-P2 slice 1: the router's settings columns, the contact override and the Jev key.

Harness is `tests/chatbot/agent/test_agent_settings.py`'s. Over the API on purpose: `response_model`
drops undeclared fields and the settings and contact responses are hand-built dicts.

Assumptions flagged in the report: the AI assistant write field is `jev_api_key` and the response
field `jev_api_key_masked` (the gemini pattern); the contact override accepts explicit null to clear.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests.chatbot.test_escalation_control_api import (  # noqa: F401 - fixtures + helpers
    BASE,
    _ACTOR,
    _GRANTS,
    _permissions,
    _seed_contact,
    client,
    db,
)

SETTINGS = "/api/v1/user-management/settings/"
SETTINGS_GENERAL = "/api/v1/user-management/settings/general"
AI_CONFIG = "/api/v1/system/ai-assistant/config"
OVERRIDE = "chatbot_agent_daily_turns"
KEY = "ZZT-jev-secret-key-5566"

DEFAULTS = {
    "chatbot_router_enabled": False,
    "chatbot_router_min_score": 0.7,
    "chatbot_agent_daily_turns": 50,
}


def _settings_row(db, **columns):
    from app.models.user import SystemSetting

    db.add(SystemSetting(id=str(uuid.uuid4()), name="ZZT router co", **columns))
    db.commit()


# ------------------------------------------------------------------ system settings


def test_settings_carry_the_three_router_keys_with_defaults(db, client):  # noqa: F811
    _GRANTS.update({"user_management.settings.view", "user_management.settings.edit"})
    _settings_row(db)
    body = client.get(SETTINGS).json()["settings"]
    for key, value in DEFAULTS.items():
        assert key in body, key
        assert body[key] == value, key


def test_the_model_columns_carry_the_defaults():
    from app.models.user import SystemSetting

    columns = SystemSetting.__table__.c
    assert columns["chatbot_router_enabled"].default.arg is False
    assert columns["chatbot_router_min_score"].default.arg == 0.7
    assert columns["chatbot_agent_daily_turns"].default.arg == 50


def test_settings_save_and_read_back(db, client):  # noqa: F811
    _GRANTS.update({"user_management.settings.view", "user_management.settings.edit"})
    _settings_row(db)
    payload = {"chatbot_router_enabled": True, "chatbot_router_min_score": 0.85, "chatbot_agent_daily_turns": 12}
    saved = client.put(SETTINGS_GENERAL, json=payload)
    assert saved.status_code == 200, saved.text
    body = client.get(SETTINGS).json()["settings"]
    for key, value in payload.items():
        assert body[key] == value, key


@pytest.mark.parametrize(
    "key, bad",
    [
        ("chatbot_router_min_score", 0.49),
        ("chatbot_router_min_score", 0.96),
        ("chatbot_router_min_score", 1.5),
        ("chatbot_agent_daily_turns", -1),
    ],
)
def test_out_of_range_values_are_refused(db, client, key, bad):  # noqa: F811
    _GRANTS.update({"user_management.settings.edit"})
    _settings_row(db)
    assert client.put(SETTINGS_GENERAL, json={key: bad}).status_code == 422


@pytest.mark.parametrize(
    "key, edge",
    [
        ("chatbot_router_min_score", 0.5),
        ("chatbot_router_min_score", 0.95),
        ("chatbot_agent_daily_turns", 0),
        ("chatbot_agent_daily_turns", 1),
    ],
)
def test_the_range_edges_are_accepted(db, client, key, edge):  # noqa: F811
    _GRANTS.update({"user_management.settings.edit", "user_management.settings.view"})
    _settings_row(db)
    resp = client.put(SETTINGS_GENERAL, json={key: edge})
    assert resp.status_code == 200, resp.text
    assert client.get(SETTINGS).json()["settings"][key] == edge


def test_writing_the_router_settings_needs_the_settings_edit_grant(db, client):  # noqa: F811
    _settings_row(db)
    _GRANTS.update({"user_management.settings.view", "user_management.settings.edit"})
    assert client.put(SETTINGS_GENERAL, json={"chatbot_router_enabled": True}).status_code == 200  # control
    assert client.get(SETTINGS).json()["settings"]["chatbot_router_enabled"] is True
    _GRANTS.discard("user_management.settings.edit")
    resp = client.put(SETTINGS_GENERAL, json={"chatbot_router_enabled": False})
    assert resp.status_code == 403


# ------------------------------------------------------------------ contact override


def test_the_override_defaults_to_null_and_is_on_the_get(db, client):  # noqa: F811
    contact_id = _seed_contact(db)
    stored = db.execute(text(f"SELECT {OVERRIDE} FROM respond_contacts WHERE id = :c"), {"c": contact_id}).scalar()
    assert stored is None
    body = client.get(f"{BASE}/{contact_id}").json()
    assert OVERRIDE in body
    assert body[OVERRIDE] is None


def test_put_sets_leaves_and_clears_the_override(db, client):  # noqa: F811
    contact_id = _seed_contact(db)
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={OVERRIDE: 20})
    assert resp.status_code == 200, resp.text
    assert resp.json()[OVERRIDE] == 20
    stored = db.execute(text(f"SELECT {OVERRIDE} FROM respond_contacts WHERE id = :c"), {"c": contact_id}).scalar()
    assert stored == 20

    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={"notify_salesman": True})
    assert resp.json()[OVERRIDE] == 20  # absent leaves it alone

    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={OVERRIDE: 0})
    assert resp.json()[OVERRIDE] == 0  # zero is a value (no cap), not "unset"

    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={OVERRIDE: None})
    assert resp.status_code == 200, resp.text
    assert resp.json()[OVERRIDE] is None  # explicit null falls back to the global value
    stored = db.execute(text(f"SELECT {OVERRIDE} FROM respond_contacts WHERE id = :c"), {"c": contact_id}).scalar()
    assert stored is None


def test_a_negative_override_is_refused(db, client):  # noqa: F811
    contact_id = _seed_contact(db)
    assert client.put(f"{BASE}/{contact_id}/chatbot", json={OVERRIDE: 5}).json()[OVERRIDE] == 5  # control
    assert client.put(f"{BASE}/{contact_id}/chatbot", json={OVERRIDE: -1}).status_code == 422


def test_writing_the_override_needs_the_contact_edit_grant(db, client):  # noqa: F811
    contact_id = _seed_contact(db)
    assert client.put(f"{BASE}/{contact_id}/chatbot", json={OVERRIDE: 5}).json()[OVERRIDE] == 5  # control
    _GRANTS.discard("user_management.contacts.edit")
    assert client.put(f"{BASE}/{contact_id}/chatbot", json={OVERRIDE: 6}).status_code == 403


# ------------------------------------------------------------------ the Jev key


def _real_actor(db):
    """The ai-assistant PUT writes updated_by_user_id (FK to users): the caller must be a real row."""
    from tests.chatbot.agent._seed import seed_user

    _ACTOR["id"] = seed_user(db, contact_pk=None)
    db.commit()


def _payload(**over) -> dict:
    body = {
        "provider": "openai", "model": "gpt-4o-mini", "temperature": 0, "system_prompt": "",
        "enabled_tools": [], "rag_enabled": True, "is_enabled": True,
    }
    body.update(over)
    return body


def _raw(db, column):
    return db.execute(text(f"SELECT {column} FROM ai_assistant_configs LIMIT 1")).scalar()


def test_the_jev_key_is_stored_encrypted_and_read_back_in_clear_by_the_service(db):  # noqa: F811
    from app.schemas.ai_assistant import AIAssistantConfigUpdate
    from app.services.ai_assistant_service import AIAssistantConfigService

    service = AIAssistantConfigService(db)
    row = service.update(
        AIAssistantConfigUpdate(**_payload(gemini_api_key="ZZT-gemini-key-1111", jev_api_key=KEY)), user_id=None
    )
    assert row.jev_api_key_ciphertext == KEY
    # Control: the existing key column is encrypted at rest in this environment.
    assert _raw(db, "gemini_api_key_ciphertext") != "ZZT-gemini-key-1111"
    raw = _raw(db, "jev_api_key_ciphertext")
    assert raw and raw != KEY and KEY not in raw


def test_the_service_response_masks_the_jev_key(db):  # noqa: F811
    from app.schemas.ai_assistant import AIAssistantConfigResponse, AIAssistantConfigUpdate
    from app.services.ai_assistant_service import AIAssistantConfigService

    service = AIAssistantConfigService(db)
    row = service.update(AIAssistantConfigUpdate(**_payload(jev_api_key=KEY)), user_id=None)
    body = service.to_response_dict(row)
    assert body["jev_api_key_masked"] == "****5566"
    assert AIAssistantConfigResponse(**body).jev_api_key_masked == "****5566"
    assert KEY not in repr(body)


def test_a_blank_or_absent_jev_key_leaves_the_stored_one_alone(db):  # noqa: F811
    from app.schemas.ai_assistant import AIAssistantConfigUpdate
    from app.services.ai_assistant_service import AIAssistantConfigService

    service = AIAssistantConfigService(db)
    service.update(AIAssistantConfigUpdate(**_payload(jev_api_key=KEY)), user_id=None)
    assert service.update(AIAssistantConfigUpdate(**_payload(jev_api_key="   ")), user_id=None).jev_api_key_ciphertext == KEY
    assert service.update(AIAssistantConfigUpdate(**_payload()), user_id=None).jev_api_key_ciphertext == KEY


def test_the_jev_key_does_not_disturb_the_other_provider_keys(db):  # noqa: F811
    from app.schemas.ai_assistant import AIAssistantConfigUpdate
    from app.services.ai_assistant_service import AIAssistantConfigService

    service = AIAssistantConfigService(db)
    row = service.update(
        AIAssistantConfigUpdate(**_payload(api_key="ZZT-openai-key-1111", gemini_api_key="ZZT-gemini-key-2222", jev_api_key=KEY)),
        user_id=None,
    )
    body = service.to_response_dict(row)
    assert body["api_key_masked"] == "****1111"
    assert body["gemini_api_key_masked"] == "****2222"
    assert body["jev_api_key_masked"] == "****5566"


def test_the_key_never_appears_in_any_api_response(db, client):  # noqa: F811
    _GRANTS.update({
        "system.ai_assistant_settings.view", "system.ai_assistant_settings.edit",
        "user_management.settings.view",
    })
    _settings_row(db)
    contact_id = _seed_contact(db)
    _real_actor(db)
    put = client.put(AI_CONFIG, json=_payload(jev_api_key=KEY))
    assert put.status_code == 200, put.text
    assert put.json()["jev_api_key_masked"] == "****5566"
    responses = [
        put,
        client.get(AI_CONFIG),
        client.get(SETTINGS),
        client.get(f"{BASE}/{contact_id}"),
    ]
    for resp in responses:
        assert resp.status_code == 200, resp.text
        assert KEY not in resp.text
    assert client.get(AI_CONFIG).json()["jev_api_key_masked"] == "****5566"
    assert "jev_api_key" not in client.get(AI_CONFIG).json()


def test_writing_the_jev_key_needs_the_ai_settings_edit_grant(db, client):  # noqa: F811
    _GRANTS.update({"system.ai_assistant_settings.edit"})
    _real_actor(db)
    assert client.put(AI_CONFIG, json=_payload(jev_api_key=KEY)).json()["jev_api_key_masked"] == "****5566"  # control
    _GRANTS.discard("system.ai_assistant_settings.edit")
    resp = client.put(AI_CONFIG, json=_payload(jev_api_key="ZZT-other-key-0000"))
    assert resp.status_code == 403
