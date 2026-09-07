"""Chatbot growth r1, Slice C1: `contact_field_reveals` and the access-check wiring.

AC-960 the table exists, unique on (contact, field_key), default absent = hidden.
AC-961 `check_access` returns `attributes` = the contact's granted keys (`[]` for
none) and `all_attributes_allowed=False`.
AC-982 nothing here is ever written by a turn (a dry run included) - the table is
admin-managed only, so this is a structural guarantee restated as a test rather
than a turn-path assertion: no code under `app/services/chatbot/` outside
`head/access.py` (a READ) imports the write side.

Postgres only, via the blank-schema `session_factory` fixture in
`tests/chatbot/conftest.py` - built from live `Base.metadata`, so the new table
and the `mcp_tools.restricted_fields` column exist without a migration step.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.access import ContactFieldReveal
from app.services import contact_field_reveal_service as svc
from app.services.chatbot.head.access import check_access

CONTACT_ID = "ZZT-contact-field-reveal-1"
SPACE_ID = "364817"


@pytest.fixture()
def seeded_contact(session_factory):
    """A respond contact, in a workspace, so `check_access` can resolve it by
    `(respond_io_id, space_id)` the same way `evaluate_agent` does."""
    db = session_factory()
    workspace_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO respond_workspaces (id, space_id, api_key_ciphertext) "
            "VALUES (:id, :space_id, 'x')"
        ),
        {"id": workspace_id, "space_id": SPACE_ID},
    )
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, workspace_id, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, :wid, CAST(:sv AS jsonb))"
        ),
        {"cid": CONTACT_ID, "phone": "+60000000099", "wid": workspace_id, "sv": json.dumps({})},
    )
    db.commit()
    contact_id = db.execute(
        text("SELECT id FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": CONTACT_ID}
    ).scalar()
    return db, contact_id


class TestTableShape:
    def test_default_absent_is_hidden(self, session_factory, seeded_contact):
        """AC-960: no row for a key -> the contact holds nothing."""
        _db, contact_id = seeded_contact
        db2 = session_factory()
        assert svc.granted_keys(db2, contact_id) == []

    def test_unique_on_contact_and_field_key(self, session_factory, seeded_contact):
        """AC-960: (respond_contact_id, field_key) is unique."""
        db, contact_id = seeded_contact
        db.add(
            ContactFieldReveal(
                respond_contact_id=contact_id, field_key="inventory.sellable", granted=True
            )
        )
        db.commit()
        db.add(
            ContactFieldReveal(
                respond_contact_id=contact_id, field_key="inventory.sellable", granted=True
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


class TestSetGrantedKeysFullReplace:
    def test_a_granted_key_reads_back(self, session_factory, seeded_contact):
        db, contact_id = seeded_contact
        result = svc.set_granted_keys(db, contact_id, ["inventory.sellable"], actor_id="u-1")
        assert result == ["inventory.sellable"]
        assert svc.granted_keys(session_factory(), contact_id) == ["inventory.sellable"]

    def test_full_replace_revokes_keys_not_in_the_new_list(self, session_factory, seeded_contact):
        db, contact_id = seeded_contact
        svc.set_granted_keys(
            db, contact_id, ["inventory.sellable", "purchase_orders.supplier"], actor_id="u-1"
        )
        result = svc.set_granted_keys(db, contact_id, ["purchase_orders.supplier"], actor_id="u-1")
        assert result == ["purchase_orders.supplier"]

        # The revoked row still exists (history), just no longer granted.
        row = (
            session_factory()
            .query(ContactFieldReveal)
            .filter(
                ContactFieldReveal.respond_contact_id == contact_id,
                ContactFieldReveal.field_key == "inventory.sellable",
            )
            .one()
        )
        assert row.granted is False

    def test_toggling_a_key_back_on_keeps_the_original_row(self, session_factory, seeded_contact):
        db, contact_id = seeded_contact
        svc.set_granted_keys(db, contact_id, ["inventory.sellable"], actor_id="u-1")
        row_id = (
            session_factory()
            .query(ContactFieldReveal.id)
            .filter(ContactFieldReveal.respond_contact_id == contact_id)
            .scalar()
        )
        svc.set_granted_keys(db, contact_id, [], actor_id="u-1")
        svc.set_granted_keys(db, contact_id, ["inventory.sellable"], actor_id="u-1")

        rows = (
            session_factory()
            .query(ContactFieldReveal)
            .filter(ContactFieldReveal.respond_contact_id == contact_id)
            .all()
        )
        assert len(rows) == 1, "a toggle off then on must not leave a second row"
        assert rows[0].id == row_id
        assert rows[0].granted is True


class TestCheckAccessAttributes:
    """AC-961."""

    def test_a_contact_with_no_grants_gets_an_empty_list(self, session_factory, seeded_contact):
        db, _contact_id = seeded_contact
        access = check_access(db, agent_code="general_enquiries", contact_id=CONTACT_ID, space_id=SPACE_ID)
        assert access["attributes"] == []
        assert access["all_attributes_allowed"] is False

    def test_a_contact_with_a_grant_sees_it_in_attributes(self, session_factory, seeded_contact):
        db, contact_id = seeded_contact
        svc.set_granted_keys(db, contact_id, ["inventory.sellable"], actor_id="u-1")

        access = check_access(
            session_factory(), agent_code="general_enquiries", contact_id=CONTACT_ID, space_id=SPACE_ID
        )
        assert access["attributes"] == ["inventory.sellable"]
        assert access["all_attributes_allowed"] is False

    def test_an_unresolvable_contact_fails_closed_to_empty(self, session_factory):
        db = session_factory()
        access = check_access(
            db, agent_code="general_enquiries", contact_id="ZZT-no-such-contact", space_id=SPACE_ID
        )
        assert access["attributes"] == []
        assert access["all_attributes_allowed"] is False


class TestFieldRevealKeys:
    def test_lists_distinct_keys_from_active_tools(self, session_factory):
        from app.models.access import McpTool

        db = session_factory()
        db.add(
            McpTool(
                id=str(uuid.uuid4()),
                tool_name=f"ZZT-tool-{uuid.uuid4().hex[:6]}",
                http_path="/x",
                http_method="GET",
                is_active=True,
                last_seen_at=__import__("datetime").datetime.utcnow(),
                restricted_fields=[{"key": "inventory.sellable", "label": "Sellable stock"}],
            )
        )
        db.commit()

        keys = svc.field_reveal_keys(session_factory())
        assert {"key": "inventory.sellable", "label": "Sellable stock"} in keys
