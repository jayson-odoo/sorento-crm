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


def test_the_access_type_attribute_round_trips(db, client):
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
