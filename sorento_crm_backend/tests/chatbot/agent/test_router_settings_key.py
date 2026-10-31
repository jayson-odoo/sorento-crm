"""AGENTIC-P2-ROUTE: the Jev key (K1), the two system settings (K2) and the contact cap (K3 API).

Red tests, written before any implementation exists. Postgres only, blank schema.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.schemas.ai_assistant import AIAssistantConfigResponse, AIAssistantConfigUpdate
from app.services.ai_assistant_service import AIAssistantConfigService
from tests._pg_fixture import blank_session
from tests.chatbot.test_escalation_control_api import (  # noqa: F401 - fixtures + helpers
    BASE,
    _GRANTS,
    _permissions,
    _seed_contact,
    client,
    db,
)

SETTINGS = "/api/v1/user-management/settings/"
SETTINGS_GENERAL = "/api/v1/user-management/settings/general"
KEY = "ZZT-jev-secret-key-1234"


def _payload(**overrides) -> AIAssistantConfigUpdate:
    fields = {
        "provider": "gemini", "model": "gemini-2.5-flash", "temperature": 0, "system_prompt": "",
        "enabled_tools": [], "rag_enabled": True, "is_enabled": True,
    }
    fields.update(overrides)
    return AIAssistantConfigUpdate(**fields)


# ------------------------------------------------------------------ K1: the key


def test_K1_the_typesafe_key_is_stored_and_returned_masked():
    with blank_session() as session:
        service = AIAssistantConfigService(session)
        row = service.update(_payload(typesafe_api_key=KEY), user_id=None)
        assert row.typesafe_api_key_ciphertext == KEY
        body = service.to_response_dict(row)
        assert body["typesafe_api_key_masked"] == "****1234"
        assert AIAssistantConfigResponse(**body).typesafe_api_key_masked == "****1234"
        assert KEY not in str(body)


def test_K1_the_stored_value_is_encrypted_at_rest():
    with blank_session() as session:
        AIAssistantConfigService(session).update(_payload(typesafe_api_key=KEY), user_id=None)
        session.commit()
        raw = session.execute(
            text("SELECT typesafe_api_key_ciphertext FROM ai_assistant_configs")
        ).scalar()
        assert raw and raw != KEY and KEY not in raw


def test_K1_a_blank_save_keeps_the_stored_key():
    with blank_session() as session:
        service = AIAssistantConfigService(session)
        service.update(_payload(typesafe_api_key=KEY), user_id=None)
        row = service.update(_payload(typesafe_api_key="   "), user_id=None)
        assert row.typesafe_api_key_ciphertext == KEY
        row = service.update(_payload(typesafe_api_key=None), user_id=None)
        assert row.typesafe_api_key_ciphertext == KEY


def test_K1_an_unset_key_is_masked_as_empty():
    with blank_session() as session:
        service = AIAssistantConfigService(session)
        row = service.update(_payload(), user_id=None)
        assert not service.to_response_dict(row)["typesafe_api_key_masked"]


def test_K1_the_typesafe_key_does_not_disturb_the_other_provider_keys():
    with blank_session() as session:
        service = AIAssistantConfigService(session)
        row = service.update(
            _payload(provider="openai", model="gpt-4o-mini", api_key="ZZT-openai-key-1111",
                     gemini_api_key="ZZT-gemini-key-3333", typesafe_api_key=KEY),
            user_id=None,
        )
        body = service.to_response_dict(row)
        assert body["api_key_masked"] == "****1111"
        assert body["gemini_api_key_masked"] == "****3333"
        assert body["typesafe_api_key_masked"] == "****1234"


def test_K1_the_resolver_returns_the_stored_key():
    from app.services.llm_provider import resolve_typesafe_key

    with blank_session() as session:
        row = AIAssistantConfigService(session).update(_payload(typesafe_api_key=KEY), user_id=None)
        assert resolve_typesafe_key(row) == KEY


def test_K1_the_resolver_never_reads_the_environment(monkeypatch):
    from app.services.llm_provider import resolve_typesafe_key

    for name in ("TYPESAFE_API_KEY", "JEV_API_KEY", "TYPESAFE_AI_API_KEY"):
        monkeypatch.setenv(name, "ZZT-env-jev-key")
    with blank_session() as session:
        row = AIAssistantConfigService(session).update(_payload(), user_id=None)
        assert resolve_typesafe_key(row) == ""
    assert resolve_typesafe_key(None) == ""


def test_K1_the_key_is_in_the_reencrypt_list():
    from scripts.reencrypt_field_secrets import COLUMNS

    assert ("ai_assistant_configs", "typesafe_api_key_ciphertext", True) in COLUMNS


def test_K1_jev_is_not_a_chat_provider():
    from app.services import llm_provider

    for name in ("typesafe", "jev"):
        with pytest.raises(Exception):
            llm_provider.get_provider(name, "k", "m")


# ------------------------------------------------------------------ K2: system settings


def _settings_row(session, **columns):
    from app.models.user import SystemSetting

    session.add(SystemSetting(id=str(uuid.uuid4()), name="ZZT router co", **columns))
    session.commit()


def test_K2_the_model_columns_carry_the_defaults():
    from app.models.user import SystemSetting

    columns = SystemSetting.__table__.c
    assert float(columns["chatbot_router_min_score"].default.arg) == 0.7
    assert columns["chatbot_agent_daily_turns"].default.arg == 50
    assert float(columns["chatbot_router_min_score"].server_default.arg) == 0.7
    assert columns["chatbot_agent_daily_turns"].server_default.arg == "50"


def test_K2_settings_carry_both_keys_with_defaults(db, client):  # noqa: F811
    _GRANTS.update({"user_management.settings.view", "user_management.settings.edit"})
    _settings_row(db)
    body = client.get(SETTINGS).json()["settings"]
    assert body["chatbot_router_min_score"] == pytest.approx(0.7)
    assert body["chatbot_agent_daily_turns"] == 50


def test_K2_settings_save_and_read_back(db, client):  # noqa: F811
    _GRANTS.update({"user_management.settings.view", "user_management.settings.edit"})
    _settings_row(db)
    saved = client.put(SETTINGS_GENERAL, json={"chatbot_router_min_score": 0.8, "chatbot_agent_daily_turns": 12})
    assert saved.status_code == 200, saved.text
    body = client.get(SETTINGS).json()["settings"]
    assert body["chatbot_router_min_score"] == pytest.approx(0.8)
    assert body["chatbot_agent_daily_turns"] == 12


@pytest.mark.parametrize(
    "key, bad",
    [
        ("chatbot_router_min_score", 0.49),
        ("chatbot_router_min_score", 0.96),
        ("chatbot_router_min_score", 1.5),
        ("chatbot_agent_daily_turns", -1),
    ],
)
def test_K2_out_of_range_values_are_refused(db, client, key, bad):  # noqa: F811
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
def test_K2_the_range_edges_are_accepted(db, client, key, edge):  # noqa: F811
    _GRANTS.update({"user_management.settings.edit"})
    _settings_row(db)
    resp = client.put(SETTINGS_GENERAL, json={key: edge})
    assert resp.status_code == 200, resp.text
    _GRANTS.add("user_management.settings.view")
    assert client.get(SETTINGS).json()["settings"][key] == pytest.approx(edge)


# ------------------------------------------------------------------ K3: the contact cap over the API

CAP = "chatbot_agent_daily_turns"


def test_K3_the_contact_cap_defaults_to_null(db, client):  # noqa: F811
    contact_id = _seed_contact(db)
    stored = db.execute(text(f"SELECT {CAP} FROM respond_contacts WHERE id = :c"), {"c": contact_id}).scalar()
    assert stored is None
    assert client.get(f"{BASE}/{contact_id}").json()[CAP] is None


def test_K3_put_sets_clears_and_absent_leaves_it_alone(db, client):  # noqa: F811
    contact_id = _seed_contact(db)
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={CAP: 7})
    assert resp.status_code == 200, resp.text
    assert resp.json()[CAP] == 7
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={"notify_salesman": True})
    assert resp.json()[CAP] == 7
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={CAP: None})
    assert resp.json()[CAP] is None
    stored = db.execute(text(f"SELECT {CAP} FROM respond_contacts WHERE id = :c"), {"c": contact_id}).scalar()
    assert stored is None


def test_K3_a_negative_contact_cap_is_refused(db, client):  # noqa: F811
    contact_id = _seed_contact(db)
    assert client.put(f"{BASE}/{contact_id}/chatbot", json={CAP: 5}).status_code == 200
    assert client.put(f"{BASE}/{contact_id}/chatbot", json={CAP: -1}).status_code == 422


def test_K3_writing_the_cap_needs_the_contact_edit_grant(db, client):  # noqa: F811
    contact_id = _seed_contact(db)
    _GRANTS.discard("user_management.contacts.edit")
    assert client.put(f"{BASE}/{contact_id}/chatbot", json={CAP: 3}).status_code == 403
