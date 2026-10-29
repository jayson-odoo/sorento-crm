"""AGENTIC-P1 card sections 5 and 8: the contact switch and the four budget settings.

Same shape as `tests/chatbot/test_files_as_links_api.py`: `contact_to_response_dict` and the
settings dict are built by hand, and `response_model` drops undeclared fields, so every field
is asserted over the API.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests.chatbot.test_escalation_control_api import (  # noqa: F401 - fixtures + helpers
    BASE,
    _GRANTS,
    _permissions,
    _seed_contact,
    client,
    db,
)

SWITCH = "chatbot_agent_enabled"
SETTINGS = "/api/v1/user-management/settings/"
SETTINGS_GENERAL = "/api/v1/user-management/settings/general"

DEFAULTS = {
    "chatbot_agent_max_rounds": 8,
    "chatbot_agent_max_seconds": 45,
    "chatbot_agent_max_input_tokens": 150000,
    "chatbot_agent_compact_tokens": 40000,
}


def _settings_row(db, **columns):
    from app.models.user import SystemSetting

    db.add(SystemSetting(id=str(uuid.uuid4()), name="ZZT agent co", **columns))
    db.commit()


# ------------------------------------------------------------------ the contact switch


def test_the_switch_defaults_to_off(db):  # noqa: F811
    contact_id = _seed_contact(db)
    stored = db.execute(text(f"SELECT {SWITCH} FROM respond_contacts WHERE id = :c"), {"c": contact_id}).scalar()
    assert stored is False


def test_get_carries_the_switch(db, client):  # noqa: F811
    contact_id = _seed_contact(db)
    assert client.get(f"{BASE}/{contact_id}").json()[SWITCH] is False
    db.execute(text(f"UPDATE respond_contacts SET {SWITCH} = true WHERE id = :c"), {"c": contact_id})
    db.commit()
    assert client.get(f"{BASE}/{contact_id}").json()[SWITCH] is True


def test_put_sets_and_clears_it_and_absent_leaves_it_alone(db, client):  # noqa: F811
    contact_id = _seed_contact(db)
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={SWITCH: True})
    assert resp.status_code == 200, resp.text
    assert resp.json()[SWITCH] is True
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={"notify_salesman": True})
    assert resp.json()[SWITCH] is True
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={SWITCH: False})
    assert resp.json()[SWITCH] is False
    stored = db.execute(text(f"SELECT {SWITCH} FROM respond_contacts WHERE id = :c"), {"c": contact_id}).scalar()
    assert stored is False


def test_writing_the_switch_needs_the_contact_edit_grant(db, client):  # noqa: F811
    contact_id = _seed_contact(db)
    _GRANTS.discard("user_management.contacts.edit")
    assert client.put(f"{BASE}/{contact_id}/chatbot", json={SWITCH: True}).status_code == 403


# ------------------------------------------------------------------ the budget settings


def test_settings_carry_the_four_budget_keys_with_defaults(db, client):  # noqa: F811
    _GRANTS.update({"user_management.settings.view", "user_management.settings.edit"})
    _settings_row(db)
    body = client.get(SETTINGS).json()["settings"]
    for key, value in DEFAULTS.items():
        assert key in body, key
        assert body[key] == value, key


def test_the_model_columns_carry_the_defaults():
    from app.models.user import SystemSetting

    columns = SystemSetting.__table__.c
    for key, value in DEFAULTS.items():
        assert columns[key].server_default.arg == str(value), key
        assert columns[key].default.arg == value, key


def test_settings_save_and_read_back_the_four_budgets(db, client):  # noqa: F811
    _GRANTS.update({"user_management.settings.view", "user_management.settings.edit"})
    _settings_row(db)
    payload = {
        "chatbot_agent_max_rounds": 12,
        "chatbot_agent_max_seconds": 90,
        "chatbot_agent_max_input_tokens": 300000,
        "chatbot_agent_compact_tokens": 20000,
    }
    saved = client.put(SETTINGS_GENERAL, json=payload)
    assert saved.status_code == 200, saved.text
    body = client.get(SETTINGS).json()["settings"]
    for key, value in payload.items():
        assert body[key] == value, key


@pytest.mark.parametrize(
    "key, bad",
    [
        ("chatbot_agent_max_rounds", 0),
        ("chatbot_agent_max_rounds", 31),
        ("chatbot_agent_max_seconds", 4),
        ("chatbot_agent_max_seconds", 301),
        ("chatbot_agent_max_input_tokens", 9999),
        ("chatbot_agent_max_input_tokens", 2000001),
        ("chatbot_agent_compact_tokens", 4999),
        ("chatbot_agent_compact_tokens", 500001),
    ],
)
def test_out_of_range_budgets_are_refused(db, client, key, bad):  # noqa: F811
    _GRANTS.update({"user_management.settings.edit"})
    _settings_row(db)
    assert client.put(SETTINGS_GENERAL, json={key: bad}).status_code == 422


@pytest.mark.parametrize(
    "key, edge",
    [
        ("chatbot_agent_max_rounds", 1),
        ("chatbot_agent_max_rounds", 30),
        ("chatbot_agent_max_seconds", 5),
        ("chatbot_agent_max_seconds", 300),
        ("chatbot_agent_max_input_tokens", 10000),
        ("chatbot_agent_max_input_tokens", 2000000),
        ("chatbot_agent_compact_tokens", 5000),
        ("chatbot_agent_compact_tokens", 500000),
    ],
)
def test_the_range_edges_are_accepted(db, client, key, edge):  # noqa: F811
    _GRANTS.update({"user_management.settings.edit"})
    _settings_row(db)
    resp = client.put(SETTINGS_GENERAL, json={key: edge})
    assert resp.status_code == 200, resp.text
    _GRANTS.add("user_management.settings.view")
    assert client.get(SETTINGS).json()["settings"][key] == edge
