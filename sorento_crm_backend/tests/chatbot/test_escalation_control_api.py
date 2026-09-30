"""ESCALATION-CONTROL: the contact's override and the access type attribute over the API.

`PUT .../contacts/{id}/chatbot` takes `escalation_allowed` (absent = leave alone, null =
inherit), and every contact read carries the override, the inherited value and the type
that barred it - asserted here because `contact_to_response_dict` is built by hand and
`response_model` drops any field it does not declare. Harness copied from
`test_stock_ask_contact_toggles.py`.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.chatbot.test_stock_ask_contact_toggles import (  # noqa: F401 - fixtures by name
    _GRANTS,
    BASE,
    _permissions,
    _seed_contact,
    client,
)
from tests.chatbot.test_turns_admin_api import db  # noqa: F401 - reuses the blank-schema fixture


def _bar_by_dealer_type(db, contact_id: str) -> None:
    db.execute(
        text(
            "INSERT INTO contact_access_types (code, name, is_active, escalation_allowed) "
            "VALUES ('zzt_sd', 'Sorento Dealer', true, false) ON CONFLICT (code) DO NOTHING"
        )
    )
    db.execute(
        text("INSERT INTO respond_contact_access_types (contact_id, access_type_code) VALUES (:c, 'zzt_sd')"),
        {"c": contact_id},
    )
    db.commit()


def test_a_plain_contact_inherits_allowed(db, client):
    contact_id = _seed_contact(db)
    body = client.get(f"{BASE}/{contact_id}").json()
    assert body["escalation_allowed"] is None
    assert body["escalation_allowed_inherited"] is True
    assert body["escalation_allowed_inherited_from"] is None


def test_a_dealer_inherits_blocked_and_names_the_type(db, client):
    contact_id = _seed_contact(db)
    _bar_by_dealer_type(db, contact_id)
    body = client.get(f"{BASE}/{contact_id}").json()
    assert body["escalation_allowed_inherited"] is False
    assert body["escalation_allowed_inherited_from"] == "Sorento Dealer"


@pytest.mark.parametrize("value", [True, False])
def test_put_sets_the_override_and_null_clears_it(db, client, value):
    contact_id = _seed_contact(db)
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={"escalation_allowed": value})
    assert resp.status_code == 200, resp.text
    assert resp.json()["escalation_allowed"] is value

    # Absent leaves it alone.
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={"notify_salesman": True})
    assert resp.json()["escalation_allowed"] is value

    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={"escalation_allowed": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["escalation_allowed"] is None
    stored = db.execute(
        text("SELECT escalation_allowed FROM respond_contacts WHERE id = :c"), {"c": contact_id}
    ).scalar()
    assert stored is None


ACCESS_TYPES = "/api/v1/user-management/contact-access-types"


def _grant_access_type_writes() -> None:
    _GRANTS.update(
        {"user_management.access_agents.add", "user_management.access_agents.edit", "user_management.access_agents.delete"}
    )


def test_the_access_type_attribute_round_trips(db, client):
    _grant_access_type_writes()
    resp = client.post(
        "/api/v1/user-management/contact-access-types",
        json={"code": "zzt_esc", "name": "ZZT Esc", "escalation_allowed": False},
    )
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["escalation_allowed"] is False
    resp = client.put(
        "/api/v1/user-management/contact-access-types/zzt_esc", json={"escalation_allowed": True}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["escalation_allowed"] is True
    # A null in the body leaves the NOT NULL column alone rather than failing.
    resp = client.put(
        "/api/v1/user-management/contact-access-types/zzt_esc", json={"escalation_allowed": None}
    )
    assert resp.status_code == 200 and resp.json()["escalation_allowed"] is True, resp.text


def test_a_mixed_office_and_dealer_contact_inherits_allowed_via_the_office_type(db, client):
    """Owner hand test (Mr Loo): the Chatbot tab says which type decided it."""
    contact_id = _seed_contact(db)
    _bar_by_dealer_type(db, contact_id)
    db.execute(
        text(
            "INSERT INTO contact_access_types (code, name, is_active, escalation_allowed, sort_order) "
            "VALUES ('zzt_so', 'Sorento Office', true, true, 1) ON CONFLICT (code) DO NOTHING"
        )
    )
    db.execute(
        text("INSERT INTO respond_contact_access_types (contact_id, access_type_code) VALUES (:c, 'zzt_so')"),
        {"c": contact_id},
    )
    db.commit()
    body = client.get(f"{BASE}/{contact_id}").json()
    assert body["escalation_allowed_inherited"] is True
    assert body["escalation_allowed_inherited_from"] == "Sorento Office"


def test_writing_an_access_type_needs_the_access_agents_grant(db, client):
    """Security review S1: the switch bars every contact holding the type, so a login
    alone no longer writes it (superadmin / admin still bypass)."""
    db.execute(
        text(
            "INSERT INTO contact_access_types (code, name, is_active, escalation_allowed) "
            "VALUES ('zzt_gate', 'ZZT Gate', true, true) ON CONFLICT (code) DO NOTHING"
        )
    )
    db.commit()
    assert client.put(f"{ACCESS_TYPES}/zzt_gate", json={"escalation_allowed": False}).status_code == 403
    assert client.post(ACCESS_TYPES, json={"code": "zzt_gate2", "name": "ZZT Gate 2"}).status_code == 403
    assert client.delete(f"{ACCESS_TYPES}/zzt_gate").status_code == 403
    _grant_access_type_writes()
    assert client.put(f"{ACCESS_TYPES}/zzt_gate", json={"escalation_allowed": False}).status_code == 200


@pytest.mark.parametrize(
    "name, sent, expected",
    [
        ("ZZT NL Dealer", None, False),
        ("zzt cabana DEALER", None, False),
        ("ZZT End User", None, True),
        ("ZZT Dealer Office", None, True),
        ("ZZT Mocha Dealer", True, True),
    ],
)
def test_a_new_dealer_type_starts_blocked(db, client, name, sent, expected):
    """Grill Q4 (owner, 30 Sep 2026): a dealer type created later starts blocked, by the
    seed's rule; an explicit value from the admin still wins."""
    _grant_access_type_writes()
    body = {"code": f"zzt_{abs(hash(name)) % 10**8}", "name": name}
    if sent is not None:
        body["escalation_allowed"] = sent
    resp = client.post(ACCESS_TYPES, json=body)
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["escalation_allowed"] is expected


def test_the_python_dealer_rule_matches_the_seed_migration():
    from app.services.escalation_policy import is_dealer_type_name
    from tests.test_migration_esc1_0001_escalation_allowed import DEALERS, NOT_DEALERS

    assert all(is_dealer_type_name(n) for n in DEALERS)
    assert not any(is_dealer_type_name(n) for n in NOT_DEALERS)
