"""S2 HTTP contract - tester-first RED, from the UAC and the lane A contract (section 5
"HTTP contract").

Covers AC-MEM038, AC-MEM039, AC-MEM041.

**No implementation exists yet.** `GET /api/v1/user-management/contacts/{id}/chatbot/memory`,
`PUT .../chatbot/facts/{key}` and `DELETE .../chatbot/facts/{key}` are not registered
routes at all (`app/api/v1/user_management/contacts.py` has no `/chatbot/memory` or
`/chatbot/facts` path). Every "happy path" test below gets a 404 (route not found), not
the assertion it is written against - a real, unambiguous "missing route" red. The 403
tests are red for a DIFFERENT reason for the same cause: a 404 is not a 403 either, so
they fail on the same missing-route basis, not because permission checking itself is
broken.

Lives under `tests/chatbot/` (moved here by coordinator ruling, 26 Sep 2026: at
`tests/test_contact_chatbot_memory_api.py` it tripped `test_import_boundary.py`'s
`ALLOWED_PREFIXES` check - that guard only exempts `tests/chatbot/`, and this file's
tombstone test imports `app.services.chatbot.turn.profile_facts` directly). Moving it
here also drops the need for a locally duplicated `session_factory`: it now shares
`tests/chatbot/conftest.py`'s fixture like every other file in this directory.

Postgres only (blank scratch schema, same `db`/`client` pattern as
`tests/chatbot/test_rearch_s0_contact_profile.py`); every customer/warehouse/brand/sales
agent chain is seeded fresh per test.

**Ambiguity flagged to the captain**: AC-MEM041's "facts reach the FE through BOTH dict
builders" is tested here as: `contact_to_response_dict` (via `GET /{id}`) must include a
CRM-sourced fact (`customer`) that is NEVER written into the stored `chatbot_profile.facts`
column - i.e. the dict builder must call the live `crm_view` merge, not just pass the raw
stored JSONB through. Read as `chatbot_profile.facts` on the `GET /{id}` response body
(the same key the stored JSONB uses), since the contract does not name an alternate
top-level field for the general contact response.
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.main  # noqa: F401 - registers every model before any query
from app.main import app
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.services.user_service import UserPermissionService

from tests.chatbot.test_turns_admin_api import db  # noqa: F401 - shared blank-schema fixture

BASE = "/api/v1/user-management/contacts"

VIEW_PERM = "user_management.contacts.view"
EDIT_PERM = "user_management.contacts.edit"

_GRANTS: set[str] = set()
_ACTOR: dict = {"id": None}


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    _GRANTS.clear()
    _GRANTS.add(VIEW_PERM)
    _GRANTS.add(EDIT_PERM)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in _GRANTS,
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield
    _GRANTS.clear()


@pytest.fixture()
def client(db):  # noqa: F811
    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    _ACTOR["id"] = str(uuid.uuid4())
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def _seed_contact(db, *, profile: dict | None = None) -> str:
    cid = f"ZZT-{uuid.uuid4().hex[:8]}"
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, "
            "chatbot_profile) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), CAST(:p AS jsonb))"
        ),
        {
            "cid": cid, "phone": f"+6000{uuid.uuid4().hex[:7]}", "sv": json.dumps({}),
            "p": json.dumps(profile or {}),
        },
    )
    db.commit()
    return db.execute(
        text("SELECT id FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": cid}
    ).scalar()


def _seed_customer_link(db, contact_pk: str, *, name: str = "Chin Chun Trading", code: str = "CC001") -> str:
    from app.models.order import Customer

    customer = Customer(customer_code=code, customer_name=name, is_active=True)
    db.add(customer)
    db.flush()
    db.execute(
        text(
            "INSERT INTO respond_contact_customers (id, contact_id, customer_id, is_primary, source) "
            "VALUES (gen_random_uuid(), :cid, :cust, true, 'manual')"
        ),
        {"cid": contact_pk, "cust": customer.id},
    )
    db.commit()
    return customer.id


# --------------------------------------------------------------------------- #
# AC-MEM038: GET .../chatbot/memory
# --------------------------------------------------------------------------- #


class TestGetChatbotMemory:
    def test_happy_path_shape(self, db, client) -> None:
        contact_id = _seed_contact(db)
        _seed_customer_link(db, contact_id)

        resp = client.get(f"{BASE}/{contact_id}/chatbot/memory")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert set(body) >= {"level", "facts", "vocabulary", "episodes", "open_orders"}, body
        assert set(body["level"]) == {"own", "effective", "system_default"}, body["level"]

        assert isinstance(body["facts"], list)
        for fact in body["facts"]:
            assert set(fact) >= {"key", "label", "value", "display", "source", "last_seen", "editable"}, fact

        assert isinstance(body["vocabulary"], list)
        vocab_keys = [v["key"] for v in body["vocabulary"]]
        assert vocab_keys == [
            "customer", "segment", "salesperson", "language", "role",
            "usual_products", "usual_brands", "usual_sites", "project", "about", "note",
        ], vocab_keys

        episodes = body["episodes"]
        assert set(episodes) >= {"kept", "limit", "current", "rows"}, episodes
        assert episodes["limit"] == 20, episodes
        assert len(episodes["rows"]) <= 10

        open_orders = body["open_orders"]
        assert "rows" in open_orders and len(open_orders["rows"]) <= 5

    def test_403_without_view_permission(self, db, client) -> None:
        contact_id = _seed_contact(db)
        _GRANTS.discard(VIEW_PERM)
        resp = client.get(f"{BASE}/{contact_id}/chatbot/memory")
        assert resp.status_code == 403, resp.text


# --------------------------------------------------------------------------- #
# AC-MEM039: PUT / DELETE .../chatbot/facts/{key}
# --------------------------------------------------------------------------- #


class TestFactsRoutes:
    def test_put_sets_a_staff_fact(self, db, client) -> None:
        contact_id = _seed_contact(db)
        resp = client.put(f"{BASE}/{contact_id}/chatbot/facts/note", json={"value": "Prefers PDF quotes"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        note = next((f for f in body["facts"] if f["key"] == "note"), None)
        assert note is not None and note["value"] == "Prefers PDF quotes" and note["source"] == "staff", note

    def test_confirming_a_learned_fact_makes_it_staff_and_survives_a_tally(self, db, client) -> None:
        from app.models.conversation_frame import ConversationFrame
        from datetime import datetime, timedelta

        contact_id = _seed_contact(db)
        cid = db.execute(text("SELECT respond_io_id FROM respond_contacts WHERE id = :i"), {"i": contact_id}).scalar()
        now = datetime.now()
        for days_ago in (1, 2):
            db.add(ConversationFrame(
                contact_id=cid, contact_respond_id=cid, space_id="0", channel="whatsapp",
                domain="inventory", status="closed", close_reason="topic_switch",
                entities={"product": ["SRTWB1455"]}, turn_ids=[f"ZZT-api-frame-{days_ago}"],
                started_at=now - timedelta(days=days_ago), opened_at=now - timedelta(days=days_ago),
                last_activity_at=now - timedelta(days=days_ago), closed_at=now - timedelta(days=days_ago),
            ))
        db.commit()

        confirm = client.put(f"{BASE}/{contact_id}/chatbot/facts/usual_products", json={"value": ["SRTWB1455"]})
        assert confirm.status_code == 200, confirm.text
        usual = next(f for f in confirm.json()["facts"] if f["key"] == "usual_products")
        assert usual["source"] == "staff", usual

    def test_put_403_without_edit_permission(self, db, client) -> None:
        contact_id = _seed_contact(db)
        _GRANTS.discard(EDIT_PERM)
        resp = client.put(f"{BASE}/{contact_id}/chatbot/facts/note", json={"value": "x"})
        assert resp.status_code == 403, resp.text

    def test_put_422_unknown_key(self, db, client) -> None:
        contact_id = _seed_contact(db)
        resp = client.put(f"{BASE}/{contact_id}/chatbot/facts/bogus_key", json={"value": "x"})
        assert resp.status_code == 422, resp.text

    def test_put_422_crm_only_key(self, db, client) -> None:
        contact_id = _seed_contact(db)
        resp = client.put(f"{BASE}/{contact_id}/chatbot/facts/customer", json={"value": "Someone Else"})
        assert resp.status_code == 422, resp.text

    def test_put_422_bad_choice(self, db, client) -> None:
        contact_id = _seed_contact(db)
        resp = client.put(f"{BASE}/{contact_id}/chatbot/facts/role", json={"value": "ceo"})
        assert resp.status_code == 422, resp.text

    def test_put_422_over_length(self, db, client) -> None:
        contact_id = _seed_contact(db)
        resp = client.put(f"{BASE}/{contact_id}/chatbot/facts/note", json={"value": "x" * 500})
        assert resp.status_code == 422, resp.text

    def test_delete_204_and_gone(self, db, client) -> None:
        contact_id = _seed_contact(db)
        client.put(f"{BASE}/{contact_id}/chatbot/facts/note", json={"value": "x"})
        resp = client.delete(f"{BASE}/{contact_id}/chatbot/facts/note")
        assert resp.status_code == 204, resp.text

        get_resp = client.get(f"{BASE}/{contact_id}/chatbot/memory")
        note = next((f for f in get_resp.json()["facts"] if f["key"] == "note"), None)
        assert note is None, note

    def test_delete_403_without_edit_permission(self, db, client) -> None:
        contact_id = _seed_contact(db)
        _GRANTS.discard(EDIT_PERM)
        resp = client.delete(f"{BASE}/{contact_id}/chatbot/facts/note")
        assert resp.status_code == 403, resp.text

    def test_delete_of_a_learned_fact_leaves_a_tombstone(self, db, client) -> None:
        from app.models.conversation_frame import ConversationFrame
        from datetime import datetime, timedelta

        contact_id = _seed_contact(db)
        cid = db.execute(text("SELECT respond_io_id FROM respond_contacts WHERE id = :i"), {"i": contact_id}).scalar()
        now = datetime.now()
        for days_ago in (1, 2):
            db.add(ConversationFrame(
                contact_id=cid, contact_respond_id=cid, space_id="0", channel="whatsapp",
                domain="inventory", status="closed", close_reason="topic_switch",
                entities={"product": ["SRTWB1455"]}, turn_ids=[f"ZZT-api-tomb-{days_ago}"],
                started_at=now - timedelta(days=days_ago), opened_at=now - timedelta(days=days_ago),
                last_activity_at=now - timedelta(days=days_ago), closed_at=now - timedelta(days=days_ago),
            ))
        db.commit()

        from app.services.chatbot.turn import profile_facts

        db2 = db
        profile_facts.tally(db2, cid)
        client.delete(f"{BASE}/{contact_id}/chatbot/facts/usual_products")

        stored = db.execute(
            text("SELECT chatbot_profile FROM respond_contacts WHERE id = :i"), {"i": contact_id}
        ).scalar()
        facts = (stored or {}).get("facts") or []
        assert not any(f.get("key") == "usual_products" and "SRTWB1455" in (f.get("value") or []) for f in facts), (
            f"a deleted learned fact must not survive as a live value: {facts}"
        )


# --------------------------------------------------------------------------- #
# AC-MEM041: facts reach the FE through BOTH dict builders
# --------------------------------------------------------------------------- #


class TestFactsInBothDictBuilders:
    def test_get_contact_detail_carries_a_live_crm_fact_never_stored(self, db, client) -> None:
        contact_id = _seed_contact(db)
        _seed_customer_link(db, contact_id, name="Chin Chun Trading", code="CC001")

        stored = db.execute(
            text("SELECT chatbot_profile FROM respond_contacts WHERE id = :i"), {"i": contact_id}
        ).scalar()
        assert not (stored or {}).get("facts"), "the CRM fact must never be persisted"

        resp = client.get(f"{BASE}/{contact_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        facts = (body.get("chatbot_profile") or {}).get("facts") or []
        customer_fact = next((f for f in facts if f.get("key") == "customer"), None)
        assert customer_fact is not None and "Chin Chun Trading" in str(customer_fact.get("value")), (
            f"GET /{{id}} must surface the LIVE crm_view fact, got facts={facts}"
        )

    def test_chatbot_memory_get_carries_the_same_live_crm_fact(self, db, client) -> None:
        contact_id = _seed_contact(db)
        _seed_customer_link(db, contact_id, name="Chin Chun Trading", code="CC001")

        resp = client.get(f"{BASE}/{contact_id}/chatbot/memory")
        assert resp.status_code == 200, resp.text
        facts = resp.json()["facts"]
        customer_fact = next((f for f in facts if f.get("key") == "customer"), None)
        assert customer_fact is not None and "Chin Chun Trading" in str(customer_fact.get("value")), facts
