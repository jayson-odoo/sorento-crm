"""Contact memory surface findings of the reviewer pass on PR #1304 at d89110c0:
B4, S6, S7, S8, S9, S10, S11, N4, N5.

Same blank-schema `db` / `client` harness as `test_contact_chatbot_memory_api.py`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.services.chatbot.turn import profile_facts
from tests.chatbot.test_contact_chatbot_memory_api import (  # noqa: F401 - fixtures
    BASE,
    EDIT_PERM,
    EPISODES_VIEW_PERM,
    _GRANTS,
    _permissions,
    _seed_contact,
    _seed_customer_link,
    client,
)
from tests.chatbot.test_turns_admin_api import db  # noqa: F401 - shared blank-schema fixture


def _stored_facts(db, contact_id: str) -> list[dict]:  # noqa: F811
    stored = db.execute(
        text("SELECT chatbot_profile FROM respond_contacts WHERE id = :i"), {"i": contact_id}
    ).scalar()
    return list((stored or {}).get("facts") or [])


def _respond_id(db, contact_id: str) -> str:  # noqa: F811
    return db.execute(
        text("SELECT respond_io_id FROM respond_contacts WHERE id = :i"), {"i": contact_id}
    ).scalar()


def _set_system_memory(db, value: dict) -> None:  # noqa: F811
    from app.models.user import SystemSetting

    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting()
        db.add(row)
    row.chatbot_memory = value
    db.commit()


class TestB4FactPutHidesEpisodes:
    def test_put_response_has_no_episodes_without_chat_history_view(self, db, client) -> None:  # noqa: F811
        contact_id = _seed_contact(db)
        _GRANTS.discard(EPISODES_VIEW_PERM)
        resp = client.put(f"{BASE}/{contact_id}/chatbot/facts/note", json={"value": "Prefers PDF quotes"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["episodes"] is None, resp.json()["episodes"]

    def test_put_response_keeps_episodes_with_it(self, db, client) -> None:  # noqa: F811
        contact_id = _seed_contact(db)
        resp = client.put(f"{BASE}/{contact_id}/chatbot/facts/note", json={"value": "x"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["episodes"] is not None


class TestS6SystemDefaultFollowsTheSwitch:
    def test_switch_off_reads_off(self, db, client) -> None:  # noqa: F811
        _set_system_memory(db, {"enabled": False, "default_level": "full"})
        contact_id = _seed_contact(db)
        level = client.get(f"{BASE}/{contact_id}/chatbot/memory").json()["level"]
        assert level["system_default"] == "off", level
        assert level["effective"] == "off", level

    def test_switch_on_reads_the_default(self, db, client) -> None:  # noqa: F811
        _set_system_memory(db, {"enabled": True, "default_level": "episodes"})
        contact_id = _seed_contact(db)
        level = client.get(f"{BASE}/{contact_id}/chatbot/memory").json()["level"]
        assert level["system_default"] == "episodes", level


class TestS7ChatbotPutKeepsAFactWrittenMeanwhile:
    def test_a_fact_committed_after_the_read_survives(self, db, client, monkeypatch) -> None:  # noqa: F811
        from app.services.contact_service import ContactService

        contact_id = _seed_contact(db, profile={"tier": "gold"})
        real_get = ContactService.get_contact

        def get_then_a_turn_writes(self, cid):
            contact = real_get(self, cid)
            _ = contact.chatbot_profile  # the route's snapshot, taken now
            # Another session's turn commits a stated fact between the route's read
            # and its write; a raw UPDATE stands in for it (the ORM snapshot above is
            # not expired by it, exactly as it would not be by another connection).
            db.execute(
                text(
                    "UPDATE respond_contacts SET chatbot_profile = jsonb_set(coalesce(chatbot_profile, "
                    "'{}'::jsonb), '{facts}', CAST(:f AS jsonb)) WHERE id = :i"
                ),
                {"f": '[{"key": "role", "value": "purchaser", "source": "stated"}]', "i": cid},
            )
            return contact

        monkeypatch.setattr(ContactService, "get_contact", get_then_a_turn_writes)
        resp = client.put(f"{BASE}/{contact_id}/chatbot", json={"chatbot_profile": {"tier": "silver"}})
        assert resp.status_code == 200, resp.text

        facts = _stored_facts(db, contact_id)
        assert any(f.get("key") == "role" and f.get("value") == "purchaser" for f in facts), facts
        stored = db.execute(
            text("SELECT chatbot_profile FROM respond_contacts WHERE id = :i"), {"i": contact_id}
        ).scalar()
        assert stored.get("tier") == "silver", stored


class TestS8GenericPutNeverWritesFacts:
    def test_generic_put_keeps_the_stored_facts(self, db, client) -> None:  # noqa: F811
        contact_id = _seed_contact(db)
        client.put(f"{BASE}/{contact_id}/chatbot/facts/note", json={"value": "Prefers PDF quotes"})
        resp = client.put(
            f"{BASE}/{contact_id}",
            json={"chatbot_profile": {"facts": [{"key": "role", "value": "boss", "source": "staff"}]}},
        )
        assert resp.status_code == 200, resp.text
        facts = _stored_facts(db, contact_id)
        assert [f.get("key") for f in facts] == ["note"], facts

    def test_generic_put_needs_contacts_edit(self, db, client) -> None:  # noqa: F811
        contact_id = _seed_contact(db)
        _GRANTS.discard(EDIT_PERM)
        resp = client.put(f"{BASE}/{contact_id}", json={"name": "Renamed"})
        assert resp.status_code == 403, resp.text


class TestS10Tombstone:
    def _tombstoned(self, db, *, key: str, removed: list) -> str:  # noqa: F811
        return _seed_contact(
            db,
            profile={"facts": [{
                "key": key, "value": None, "source": "staff", "source_ref": None,
                "first_seen": "2026-09-01", "last_seen": "2026-09-20", "seen_count": 2,
                "set_by": None, "removed": removed,
            }]},
        )

    def test_a_tally_may_learn_a_value_that_was_not_removed(self, db) -> None:  # noqa: F811
        contact_id = self._tombstoned(db, key="usual_products", removed=["SRTWB1455"])
        entry = profile_facts._write_fact(
            db, by_pk=contact_id, key="usual_products", value=["SRTWB1455", "M483-BL"],
            source="tallied", source_ref=None, set_by=None,
        )
        assert entry is not None and entry["value"] == ["M483-BL"], entry
        (fact,) = _stored_facts(db, contact_id)
        assert fact["value"] == ["M483-BL"] and "SRTWB1455" in fact.get("removed", []), fact

    def test_a_tally_of_only_removed_values_writes_nothing(self, db) -> None:  # noqa: F811
        contact_id = self._tombstoned(db, key="usual_products", removed=["SRTWB1455"])
        entry = profile_facts._write_fact(
            db, by_pk=contact_id, key="usual_products", value=["SRTWB1455"],
            source="tallied", source_ref=None, set_by=None,
        )
        assert entry is None
        (fact,) = _stored_facts(db, contact_id)
        assert fact["value"] is None, fact

    def test_a_newer_statement_replaces_the_tombstone(self, db) -> None:  # noqa: F811
        contact_id = self._tombstoned(db, key="role", removed=["purchaser"])
        entry = profile_facts.apply_statement(
            db, _respond_id(db, contact_id), "role", "owner", turn_id="t-2", contact_pk=contact_id
        )
        assert entry is not None and entry["value"] == "owner", entry

    def test_the_get_does_not_list_a_tombstone(self, db, client) -> None:  # noqa: F811
        contact_id = self._tombstoned(db, key="role", removed=["purchaser"])
        facts = client.get(f"{BASE}/{contact_id}/chatbot/memory").json()["facts"]
        assert not any(f["key"] == "role" for f in facts), facts

    def test_a_repeat_delete_keeps_the_tombstone(self, db) -> None:  # noqa: F811
        contact_id = self._tombstoned(db, key="usual_products", removed=["SRTWB1455"])
        profile_facts.delete_fact(db, contact_id, "usual_products")
        (fact,) = _stored_facts(db, contact_id)
        assert fact["value"] is None and fact.get("removed") == ["SRTWB1455"], fact


class TestS11CustomerLink:
    def test_the_customer_row_links_to_the_customer(self, db, client) -> None:  # noqa: F811
        contact_id = _seed_contact(db)
        customer_id = _seed_customer_link(db, contact_id)
        facts = client.get(f"{BASE}/{contact_id}/chatbot/memory").json()["facts"]
        customer = next(f for f in facts if f["key"] == "customer")
        assert customer["link"] == f"/order-management/customers/{customer_id}", customer
        assert all(f.get("link") is None for f in facts if f["key"] != "customer"), facts


class TestN4Values:
    def test_a_list_for_a_text_key_is_rejected(self, db, client) -> None:  # noqa: F811
        contact_id = _seed_contact(db)
        resp = client.put(f"{BASE}/{contact_id}/chatbot/facts/note", json={"value": ["a", "b"]})
        assert resp.status_code == 422, resp.text

    def test_more_than_three_brands_is_rejected(self, db, client) -> None:  # noqa: F811
        from app.models.product import Brand
        from app.services.company_scope import DEFAULT_COMPANY_ID

        names = [f"ZZT-brand-{uuid.uuid4().hex[:6]}" for _ in range(4)]
        for name in names:
            db.add(Brand(brand_name=name, brand_code=name[-6:], company_id=DEFAULT_COMPANY_ID))
        db.commit()
        contact_id = _seed_contact(db)
        resp = client.put(f"{BASE}/{contact_id}/chatbot/facts/usual_brands", json={"value": names})
        assert resp.status_code == 422, resp.text

    def test_an_empty_project_is_rejected(self, db, client) -> None:  # noqa: F811
        contact_id = _seed_contact(db)
        resp = client.put(f"{BASE}/{contact_id}/chatbot/facts/project", json={"value": "   "})
        assert resp.status_code == 422, resp.text


class TestN5:
    def test_delete_of_a_crm_only_key_is_422(self, db, client) -> None:  # noqa: F811
        contact_id = _seed_contact(db)
        resp = client.delete(f"{BASE}/{contact_id}/chatbot/facts/customer")
        assert resp.status_code == 422, resp.text

    def test_a_cancelled_order_is_not_open(self, db, client) -> None:  # noqa: F811
        from datetime import date

        from app.models.order import SalesOrder
        from app.services.company_scope import DEFAULT_COMPANY_ID

        contact_id = _seed_contact(db)
        customer_id = _seed_customer_link(db, contact_id)
        for number, status in (("ZZT-SO-OPEN", "open"), ("ZZT-SO-CXL", "cancelled")):
            db.add(SalesOrder(
                so_number=f"{number}-{uuid.uuid4().hex[:4]}", customer_id=customer_id, status=status,
                order_date=date(2026, 9, 20), company_id=DEFAULT_COMPANY_ID,
            ))
        db.commit()
        rows = client.get(f"{BASE}/{contact_id}/chatbot/memory").json()["open_orders"]["rows"]
        assert [r["document"].rsplit("-", 1)[0] for r in rows] == ["ZZT-SO-OPEN"], rows


def test_s9_a_partial_settings_put_keeps_the_other_key(db) -> None:  # noqa: F811
    """S9 at the one line that decides it: `_update_general_settings_impl` merges a
    partial `chatbot_memory` over what is stored."""
    from app.api.v1.user_management.settings import SystemSettingUpdate, _update_general_settings_impl
    from app.models.user import SystemSetting

    _set_system_memory(db, {"enabled": False, "default_level": "episodes"})
    _update_general_settings_impl(SystemSettingUpdate(chatbot_memory={"enabled": True}), db)
    stored = db.query(SystemSetting).first().chatbot_memory
    assert stored == {"enabled": True, "default_level": "episodes"}, stored


class TestS13ContactsListFiltersOwnLevel:
    def test_own_lists_only_contacts_with_their_own_level(self, db, client) -> None:  # noqa: F811
        own = _seed_contact(db)
        follows = _seed_contact(db)
        db.execute(
            text("UPDATE respond_contacts SET chatbot_memory_level = 'episodes' WHERE id = :i"), {"i": own}
        )
        db.commit()
        resp = client.get(f"{BASE}/", params={"chatbot_memory_level": "own", "limit": 1000})
        assert resp.status_code == 200, resp.text
        ids = {row["id"] for row in resp.json()["data"]}
        assert own in ids and follows not in ids, ids
