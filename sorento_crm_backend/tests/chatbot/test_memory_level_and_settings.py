"""S0 schema + settings/contact-level contract - tester-first RED, from the UAC and the
lane A contract (section 2 "Context level", section 5 "HTTP contract"), UPDATED for the
round 3 UAC/plan text (merged 5b110df8): AC-MEM014, 015, 033, 049, 051 to 058, 069, 073,
PLAN section 6.0.

**Round 3 changes to this file, listed:**

1. AC-MEM051: the resolver function is RENAMED `memory.effective_level` ->
   `memory.resolve_level` (same truth table). `TestEffectiveLevel` -> `TestResolveLevel`.
2. Level values are renamed: `"past"` -> `"episodes"` everywhere (`VALID_MEMORY_LEVELS`,
   the settings `default_level` enum, the contact `chatbot_memory_level` enum). The
   LABEL stays "Past conversations" (contract 6.0's own table header); only the stored
   value changes.
3. AC-MEM054: the migration DROPS `chatbot_recall_enabled` entirely (model AND DB
   column) - not "left untouched at default false" as the S0-era version of this file
   read it. `TestNoMigrationAltersRecallEnabledDefault` (which asserted the column
   stays at its default) is RETIRED; `TestChatbotMemoryLevelCheckConstraint` replaces
   it, asserting the column is GONE and a CHECK constraint on `chatbot_memory_level`
   rejects any value outside `off | conversation | episodes | full`.
4. AC-MEM073 (updated wording): no migration writes a non-null `chatbot_memory_level`
   (unchanged intent, renamed test class); settings `enabled` still defaults false; a
   new contact's OWN level is null, so `resolve_level` gives it "off".

**No implementation exists yet.** None of the three columns exist on their models;
`app.services.chatbot.turn.memory` has no `resolve_level` (only the OLD
`effective_level`, still naming `"past"`); `SystemSetting.chatbot_memory`'s Python
default still returns the OLD four dead keys, never
`{"enabled": False, "default_level": "full"}`; the settings PUT's own key-vocabulary
check still names the old four keys, not the new two; `ContactChatbotUpdate` has no
`chatbot_memory_level` field; `chatbot_recall_enabled` still exists on the model
(`app/models/access.py:266`).

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
# AC-MEM051: memory.resolve_level truth table (renamed from effective_level;
# "past" renamed "episodes")
# --------------------------------------------------------------------------- #


class TestResolveLevel:
    @pytest.mark.parametrize(
        "contact_level,system_memory,expected",
        [
            ("full", {"enabled": False, "default_level": "full"}, "full"),
            (None, {"enabled": False, "default_level": "full"}, "off"),
            (None, {"enabled": True, "default_level": "episodes"}, "episodes"),
            ("off", {"enabled": True, "default_level": "full"}, "off"),
            (None, None, "off"),
            ("bogus", {"enabled": False, "default_level": "full"}, "off"),
            # "past" is a RETIRED value name (round 3) - a row carrying the old
            # name (a hypothetical pre-round-3 write, or a stale system default)
            # must not be treated as a recognised level.
            (None, {"enabled": True, "default_level": "past"}, "off"),
            ("past", {"enabled": False, "default_level": "full"}, "off"),
        ],
    )
    def test_truth_table(self, contact_level, system_memory, expected) -> None:
        from app.services.chatbot.turn import memory as memory_mod

        assert memory_mod.resolve_level(contact_level, system_memory) == expected


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
        # Coordinator fix, 26 Sep 2026: GET nests the body under "settings"
        # (`test_s8_settings_screen.py:236`'s own `resp.json()["settings"]`), not flat.
        memory = resp.json()["settings"].get("chatbot_memory") or {}
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

    def test_put_enabled_and_default_level_episodes_persists(self, api, db) -> None:
        """Round 3: "past" is renamed "episodes" as the STORED value (contract 6.0's
        table keeps the label "Past conversations" - only the wire value changes)."""
        client, allow = api
        allow.add(VIEW_PERMISSION)
        allow.add(EDIT_PERMISSION)
        _seed_settings(db)

        resp = client.put(
            GENERAL_ENDPOINT, json={"chatbot_memory": {"enabled": True, "default_level": "episodes"}}
        )
        assert resp.status_code == 200, resp.text

        get_resp = client.get(SETTINGS_ENDPOINT)
        memory = get_resp.json()["settings"].get("chatbot_memory") or {}
        assert memory.get("enabled") is True, memory
        assert memory.get("default_level") == "episodes", memory

    def test_put_default_level_past_is_rejected(self, api, db) -> None:
        """The OLD stored-value name is retired (round 3) - "past" must no longer be
        accepted, even though it used to be the valid name for this exact level."""
        client, allow = api
        allow.add(VIEW_PERMISSION)
        allow.add(EDIT_PERMISSION)
        _seed_settings(db)

        resp = client.put(GENERAL_ENDPOINT, json={"chatbot_memory": {"default_level": "past"}})
        assert resp.status_code == 422, (
            f"'past' is retired (renamed 'episodes', round 3) and must be rejected, "
            f"got {resp.status_code}: {resp.text}"
        )


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
    """AC-MEM055 (round 3, merged 5b110df8) RENAMES the PUT request body key from
    `chatbot_memory_level` to `memory_level` - the RESPONSE / dict-builder field
    stays `chatbot_memory_level` (both dict builders, unchanged). Every PUT body
    below is updated; every response/DB read keeps its old name."""

    def test_put_sets_chatbot_memory_level(self, db, client, _contact_perms) -> None:
        contact_id = _seed_contact(db)
        resp = client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"memory_level": "full"})
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
        client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"memory_level": "full"})
        set_value = db.execute(
            text("SELECT chatbot_memory_level FROM respond_contacts WHERE id = :i"), {"i": contact_id}
        ).scalar()
        assert set_value == "full", (
            "the field must actually persist before a 'clear' test means anything"
        )

        resp = client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"memory_level": None})
        assert resp.status_code == 200, resp.text
        cleared_value = db.execute(
            text("SELECT chatbot_memory_level FROM respond_contacts WHERE id = :i"), {"i": contact_id}
        ).scalar()
        assert cleared_value is None, cleared_value

    def test_absent_leaves_it_alone(self, db, client, _contact_perms) -> None:
        contact_id = _seed_contact(db)
        client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"memory_level": "episodes"})

        resp = client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"chatbot_profile": {"tier": "dealer"}})
        assert resp.status_code == 200, resp.text
        assert resp.json().get("chatbot_memory_level") == "episodes", resp.json()

    def test_past_value_is_422_the_stored_name_is_episodes_now(self, db, client, _contact_perms) -> None:
        contact_id = _seed_contact(db)
        resp = client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"memory_level": "past"})
        assert resp.status_code == 422, resp.text

    def test_bogus_value_is_422(self, db, client, _contact_perms) -> None:
        contact_id = _seed_contact(db)
        resp = client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"memory_level": "bogus"})
        assert resp.status_code == 422, resp.text

    def test_get_contact_carries_chatbot_memory_level(self, db, client, _contact_perms) -> None:
        contact_id = _seed_contact(db)
        client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"memory_level": "conversation"})

        resp = client.get(f"{CONTACTS_BASE}/{contact_id}")
        assert resp.status_code == 200, resp.text
        assert resp.json().get("chatbot_memory_level") == "conversation", resp.json()

    def test_403_without_contacts_edit_permission(self, db, client, monkeypatch) -> None:
        from app.services.user_service import UserPermissionService

        monkeypatch.setattr(
            UserPermissionService,
            "check_user_has_permission",
            lambda self, uid, slug: slug == "user_management.contacts.view",
        )
        monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
        contact_id = _seed_contact(db)
        resp = client.put(f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"memory_level": "full"})
        assert resp.status_code == 403, resp.text

    def test_chatbot_recall_enabled_in_the_body_is_rejected(self, db, client, _contact_perms) -> None:
        """AC-MEM054: the column is dropped, so a body still naming the retired
        field must 422, not be silently ignored - the same "unknown key rejected"
        shape `test_put_recall_default_key_is_rejected` pins on the settings PUT."""
        contact_id = _seed_contact(db)
        resp = client.put(
            f"{CONTACTS_BASE}/{contact_id}/chatbot", json={"chatbot_recall_enabled": True}
        )
        assert resp.status_code == 422, resp.text


# --------------------------------------------------------------------------- #
# AC-MEM054: chatbot_recall_enabled is DROPPED (model + DB); chatbot_memory_level
# gets a CHECK constraint. RETIRES the S0-era `TestNoMigrationAltersRecallEnabledDefault`,
# which asserted the column stayed at its default - round 3 drops it outright.
# --------------------------------------------------------------------------- #


class TestChatbotMemoryLevelCheckConstraint:
    def test_chatbot_recall_enabled_column_is_gone(self, db) -> None:
        assert not _column_exists(db, "respond_contacts", "chatbot_recall_enabled"), (
            "chatbot_recall_enabled must be DROPPED (model and DB column), round 3 "
            "AC-MEM054 - the recall re-parse it gated is deleted"
        )

    def test_bogus_level_rejected_by_a_db_check_constraint(self, db) -> None:
        """Bypasses the ORM/route validation entirely (a raw UPDATE) to prove the
        constraint lives in the DATABASE, not only in application code."""
        cid = _seed_contact(db)
        with pytest.raises(Exception):
            db.execute(
                text("UPDATE respond_contacts SET chatbot_memory_level = 'bogus' WHERE id = :i"),
                {"i": cid},
            )
            db.commit()
        db.rollback()

    @pytest.mark.parametrize("value", ["off", "conversation", "episodes", "full"])
    def test_each_of_the_four_values_is_accepted_by_the_constraint(self, db, value) -> None:
        cid = _seed_contact(db)
        db.execute(
            text("UPDATE respond_contacts SET chatbot_memory_level = :v WHERE id = :i"),
            {"v": value, "i": cid},
        )
        db.commit()
        stored = db.execute(
            text("SELECT chatbot_memory_level FROM respond_contacts WHERE id = :i"), {"i": cid}
        ).scalar()
        assert stored == value

    def test_past_is_rejected_by_the_constraint_too(self, db) -> None:
        """The retired value name must not slip past the DB constraint either."""
        cid = _seed_contact(db)
        with pytest.raises(Exception):
            db.execute(
                text("UPDATE respond_contacts SET chatbot_memory_level = 'past' WHERE id = :i"),
                {"i": cid},
            )
            db.commit()
        db.rollback()


# --------------------------------------------------------------------------- #
# AC-MEM073: no migration writes a non-null chatbot_memory_level; a new contact
# resolves to off
# --------------------------------------------------------------------------- #


class TestAC_MEM073NoMigrationTurnsMemoryOn:
    def test_no_migration_writes_a_non_null_chatbot_memory_level(self) -> None:
        """A forward guard against a migration DATA statement, not a schema one - the
        column itself is nullable by design (contract 6.0: "null for every row, so
        every contact follows the system default")."""
        versions_dir = BACKEND_ROOT / "alembic" / "versions"
        pattern = re.compile(r"chatbot_memory_level['\"]?\s*[:=]\s*['\"](off|conversation|episodes|full|past)")
        offenders = []
        for path in versions_dir.glob("*.py"):
            text_content = path.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(text_content):
                offenders.append(path.name)
        assert offenders == [], f"migrations writing a non-null chatbot_memory_level: {offenders}"

    def test_new_contact_own_level_is_null_and_resolves_to_off(self, db) -> None:
        from app.services.chatbot.turn import memory as memory_mod

        cid = _seed_contact(db)
        own_level = db.execute(
            text("SELECT chatbot_memory_level FROM respond_contacts WHERE id = :i"), {"i": cid}
        ).scalar()
        assert own_level is None
        assert memory_mod.resolve_level(own_level, {"enabled": False, "default_level": "full"}) == "off"
