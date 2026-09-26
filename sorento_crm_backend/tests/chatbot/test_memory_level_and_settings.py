"""S0 schema + settings/contact-level contract - tester-first RED, from the UAC and the
lane A contract (section 2 "Context level", section 5 "HTTP contract").

Covers: the three new/changed columns (`respond_contacts.chatbot_memory_level`,
`conversation_frames.is_test`, `ai_assistant_usage_logs.chatbot_turn_id`),
`memory.effective_level`'s truth table, AC-MEM026 (the settings screen's
`chatbot_memory` shape), the contact `PUT .../chatbot` body's new
`chatbot_memory_level` field, and AC-MEM073's migration-touch guard.

**No implementation exists yet.** None of the three columns exist on their models;
`app.services.chatbot.turn.memory` has no `effective_level`; `SystemSetting.
chatbot_memory`'s Python default (`app.modules.chatbot.lane_vocabulary.
default_chatbot_memory`) still returns the OLD four dead keys
(`recall_default`/`episode_retention_days`/`profile_fields`/`focus_reset_events`), never
`{"enabled": False, "default_level": "full"}`; the settings PUT's own key-vocabulary
check (`CHATBOT_MEMORY_KEYS`) still names the old four keys, not the new two;
`ContactChatbotUpdate` has no `chatbot_memory_level` field.

**Ambiguity flagged to the captain**: `test_put_chatbot_memory_default_level_off_is_422`
passes against TODAY's code, but for the WRONG reason - `default_level` is not yet a
recognised `chatbot_memory` key at all, so today's "unknown key" check 422s it before any
value-range check could run. Once the coder renames the key vocabulary, this test starts
exercising the real value-range validation (`default_level` may never be `"off"`, contract
section 2) instead. Kept rather than dropped, and flagged here instead of silently relied
on.

Postgres only: schema checks run on `tests/chatbot/conftest.py::session_factory`'s blank
scratch schema (model-level column additions, same pattern as
`test_rearch_s0_contact_profile.py`); HTTP-level tests use the same `db`/`client`
fixtures `test_rearch_s0_contact_profile.py` established, and `db`/`api` from
`test_s8_settings_screen.py` for the settings routes.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.chatbot.test_rearch_s0_contact_profile import BASE as CONTACTS_BASE
from tests.chatbot.test_rearch_s0_contact_profile import client  # noqa: F401
from tests.chatbot.test_turns_admin_api import db  # noqa: F401
from tests.chatbot.test_s8_settings_screen import (  # noqa: F401
    EDIT_PERMISSION,
    GENERAL_ENDPOINT,
    SETTINGS_ENDPOINT,
    VIEW_PERMISSION,
    api,
    _seed_settings,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _column_exists(db, table: str, column: str) -> bool:
    row = db.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).first()
    return row is not None


def _seed_contact(db) -> str:
    cid = f"ZZT-{uuid.uuid4().hex[:8]}"
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": cid, "phone": f"+6011{uuid.uuid4().hex[:8]}", "sv": json.dumps({})},
    )
    db.commit()
    return db.execute(
        text("SELECT id FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": cid}
    ).scalar()


# --------------------------------------------------------------------------- #
# Schema: the three new/changed columns (S0 migration)
# --------------------------------------------------------------------------- #


class TestNewColumnsExist:
    def test_respond_contacts_has_chatbot_memory_level(self, db) -> None:
        assert _column_exists(db, "respond_contacts", "chatbot_memory_level"), (
            "respond_contacts.chatbot_memory_level VARCHAR(16) NULL is missing"
        )

    def test_conversation_frames_has_is_test(self, session_factory) -> None:
        assert _column_exists(session_factory(), "conversation_frames", "is_test"), (
            "conversation_frames.is_test boolean not null default false is missing"
        )

    def test_ai_assistant_usage_logs_has_chatbot_turn_id(self, session_factory) -> None:
        assert _column_exists(session_factory(), "ai_assistant_usage_logs", "chatbot_turn_id"), (
            "ai_assistant_usage_logs.chatbot_turn_id VARCHAR(64) NULL is missing"
        )


# --------------------------------------------------------------------------- #
# memory.effective_level truth table (contract section 2)
# --------------------------------------------------------------------------- #


class TestEffectiveLevel:
    @pytest.mark.parametrize(
        "contact_level,system_memory,expected",
        [
            ("full", {"enabled": False, "default_level": "full"}, "full"),
            (None, {"enabled": False, "default_level": "full"}, "off"),
            (None, {"enabled": True, "default_level": "past"}, "past"),
            ("off", {"enabled": True, "default_level": "full"}, "off"),
            (None, None, "off"),
            ("bogus", {"enabled": False, "default_level": "full"}, "off"),
        ],
    )
    def test_truth_table(self, contact_level, system_memory, expected) -> None:
        from app.services.chatbot.turn import memory as memory_mod

        assert memory_mod.effective_level(contact_level, system_memory) == expected


# --------------------------------------------------------------------------- #
# AC-MEM026: the settings `chatbot_memory` shape
# --------------------------------------------------------------------------- #


class TestSettingsChatbotMemoryShape:
    def test_system_setting_python_default_is_the_new_two_key_shape(self, system_settings_row) -> None:
        assert system_settings_row.chatbot_memory == {"enabled": False, "default_level": "full"}, (
            system_settings_row.chatbot_memory
        )

    def test_get_settings_returns_exactly_enabled_default_level_own_level_count(
        self, api, db
    ) -> None:
        client, allow = api
        allow.add(VIEW_PERMISSION)
        _seed_settings(db)

        resp = client.get(SETTINGS_ENDPOINT)
        assert resp.status_code == 200, resp.text
        memory = resp.json().get("chatbot_memory") or {}
        assert set(memory) == {"enabled", "default_level", "own_level_count"}, memory

    def test_put_default_level_off_is_rejected(self, api, db) -> None:
        """See module docstring's ambiguity note: 422 today, but via the OLD
        unknown-key check, not the new value-range rule."""
        client, allow = api
        allow.add(VIEW_PERMISSION)
        allow.add(EDIT_PERMISSION)
        _seed_settings(db)

        resp = client.put(GENERAL_ENDPOINT, json={"chatbot_memory": {"default_level": "off"}})
        assert resp.status_code == 422, resp.text

    def test_put_recall_default_key_is_rejected(self, api, db) -> None:
        client, allow = api
        allow.add(VIEW_PERMISSION)
        allow.add(EDIT_PERMISSION)
        _seed_settings(db)

        resp = client.put(GENERAL_ENDPOINT, json={"chatbot_memory": {"recall_default": True}})
        assert resp.status_code == 422, (
            f"recall_default is a dead key (Q7/Q11) and must be rejected, got {resp.status_code}: {resp.text}"
        )

    def test_put_enabled_and_default_level_past_persists(self, api, db) -> None:
        client, allow = api
        allow.add(VIEW_PERMISSION)
        allow.add(EDIT_PERMISSION)
        _seed_settings(db)

        resp = client.put(
            GENERAL_ENDPOINT, json={"chatbot_memory": {"enabled": True, "default_level": "past"}}
        )
        assert resp.status_code == 200, resp.text

        get_resp = client.get(SETTINGS_ENDPOINT)
        memory = get_resp.json().get("chatbot_memory") or {}
        assert memory.get("enabled") is True, memory
        assert memory.get("default_level") == "past", memory


# --------------------------------------------------------------------------- #
# Contact PUT .../chatbot gains chatbot_memory_level
# --------------------------------------------------------------------------- #


@pytest.fixture()
def _contact_perms(monkeypatch):
    """Grants `user_management.contacts.view` + `.edit` for the contact-route tests
    below. NOT imported from `test_rearch_s0_contact_profile.py`'s own autouse
    `_permissions` fixture: an autouse fixture only auto-applies within the module it
    is COLLECTED from, and importing just `client`/`BASE` does not pull that in."""
    from app.services.user_service import UserPermissionService

    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug
        in {"user_management.contacts.view", "user_management.contacts.edit"},
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())


class TestContactChatbotMemoryLevel:
    def test_put_sets_chatbot_memory_level(self, db, client, _contact_perms) -> None:
        contact_id = _seed_contact(db)
        resp = client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"chatbot_memory_level": "full"})
        assert resp.status_code == 200, resp.text
        assert resp.json().get("chatbot_memory_level") == "full", resp.json()

        stored = db.execute(
            text("SELECT chatbot_memory_level FROM respond_contacts WHERE id = :i"), {"i": contact_id}
        ).scalar()
        assert stored == "full"

    def test_put_null_clears_to_null(self, db, client, _contact_perms) -> None:
        """Asserts against the STORED column, not the response body: the field is
        absent from today's response either way (set or cleared), which would let a
        body-only assertion pass for the wrong reason. Setting to "full" first must
        actually land in the database, or the clear that follows proves nothing."""
        contact_id = _seed_contact(db)
        client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"chatbot_memory_level": "full"})
        set_value = db.execute(
            text("SELECT chatbot_memory_level FROM respond_contacts WHERE id = :i"), {"i": contact_id}
        ).scalar()
        assert set_value == "full", (
            "the field must actually persist before a 'clear' test means anything"
        )

        resp = client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"chatbot_memory_level": None})
        assert resp.status_code == 200, resp.text
        cleared_value = db.execute(
            text("SELECT chatbot_memory_level FROM respond_contacts WHERE id = :i"), {"i": contact_id}
        ).scalar()
        assert cleared_value is None, cleared_value

    def test_absent_leaves_it_alone(self, db, client, _contact_perms) -> None:
        contact_id = _seed_contact(db)
        client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"chatbot_memory_level": "past"})

        resp = client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"chatbot_profile": {"tier": "dealer"}})
        assert resp.status_code == 200, resp.text
        assert resp.json().get("chatbot_memory_level") == "past", resp.json()

    def test_bogus_value_is_422(self, db, client, _contact_perms) -> None:
        contact_id = _seed_contact(db)
        resp = client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"chatbot_memory_level": "bogus"})
        assert resp.status_code == 422, resp.text

    def test_get_contact_carries_chatbot_memory_level(self, db, client, _contact_perms) -> None:
        contact_id = _seed_contact(db)
        client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"chatbot_memory_level": "conversation"})

        resp = client.get(f"{CONTACTS_BASE}/{contact_id}")
        assert resp.status_code == 200, resp.text
        assert resp.json().get("chatbot_memory_level") == "conversation", resp.json()


# --------------------------------------------------------------------------- #
# AC-MEM073: no migration other than the lane's own alters chatbot_recall_enabled
# --------------------------------------------------------------------------- #


class TestNoMigrationAltersRecallEnabledDefault:
    def test_no_migration_other_than_chatbot_rearch_s0_touches_the_column(self) -> None:
        """The ORIGINAL `chatbot_rearch_s0.py` (a prior, already-merged lane) ADDS the
        column; this lane's OWN new migration (not yet written) must not ALTER its
        default or any existing row. A forward guard: currently vacuously true (no
        lane migration exists yet to violate it), flagged rather than relied on as the
        sole evidence for AC-MEM073."""
        versions_dir = BACKEND_ROOT / "alembic" / "versions"
        pattern = re.compile(r"alter_column\([^)]*chatbot_recall_enabled", re.DOTALL)
        offenders = []
        for path in versions_dir.glob("*.py"):
            if path.name == "chatbot_rearch_s0.py":
                continue
            text_content = path.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(text_content):
                offenders.append(path.name)
        assert offenders == [], f"migrations altering chatbot_recall_enabled: {offenders}"

    def test_column_default_is_false_after_create_all(self, db) -> None:
        cid = _seed_contact(db)
        value = db.execute(
            text("SELECT chatbot_recall_enabled FROM respond_contacts WHERE id = :i"), {"i": cid}
        ).scalar()
        assert value is False
