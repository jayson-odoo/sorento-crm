"""S6 (coordinator ruling, 16 Sep 2026, supersedes part of an earlier same-session
instruction): stock allowance moves OFF the respond.io custom field
(`contact.custom_fields[].name == "is_allowed_stock"`) and ONTO the CRM contact row,
default ON for everyone - `respond_contacts.chatbot_stock_allowed` (new column,
migration `chatbot_rearch_s6`, `down_revision = chatbot_rearch_s5`).

`engine._stock_check_denied` (contract 61/62) must read the CONTACT ROW, never the
envelope's own `custom_fields` - a console/test turn's borrowed envelope carries
whatever the LAST recorded turn's custom_fields happened to be (see
`test_rearch_s6_console_borrow.py`, the same session's other finding), so a switch that
lived on the envelope was never a reliable read for a re-run turn. `turn_runtime.
load_profile` already does one `SELECT ... FROM respond_contacts WHERE respond_io_id =
:cid` per turn (`chatbot_profile`, `chatbot_recall_enabled`) - the new column joins
that same select, one query, not a second round trip.

**RIGHT NOW every test here is RED**: the column does not exist
(`respond_contacts.chatbot_stock_allowed`), `_stock_check_denied` still reads
`envelope.contact.custom_fields`, and the two API surfaces (`PUT .../contacts/{id}/
chatbot`, the contact response dict) do not know the field exists.

Column-level tests run on the ordinary blank scratch schema (`Base.metadata.create_all`
picks up a new `RespondContact` column for free, same shape as `test_rearch_s0_contact_
profile.py` - no real Alembic migration needed for THESE tests to go green, only the
model change). The end-to-end engine tests use `tests/chatbot/conftest.py::
session_factory`, the same fixture `TestStockDenialGateEndToEnd` in `test_engine.py`
already uses for contract 61/62's OLD (envelope-based) shape.
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.main import app
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.services.chatbot import engine as engine_mod
from app.services.user_service import UserPermissionService

from tests.chatbot.test_engine import (  # noqa: F401 - stub_access/stub_parser are fixture imports
    CONTACT_ID,
    _envelope,
    _parser_output,
    stub_access,
    stub_parser,
)
from tests.chatbot.test_turns_admin_api import db  # noqa: F401 - reuses the blank-schema fixture

BASE = "/api/v1/user-management/contacts"
CONTACT_VIEW = "user_management.contacts.view"
# Coordinator fixture item, 16 Sep 2026: `PUT /contacts/{id}/chatbot` now requires
# this grant too (coder's just-merged permission gate on that route) - a fixture
# gap, not a route bug.
CONTACT_EDIT = "user_management.contacts.edit"

_GRANTS: set[str] = {CONTACT_VIEW, CONTACT_EDIT}
_ACTOR: dict = {"id": None, "name": "ZZT Stock Allowed Tester"}


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    _GRANTS.clear()
    _GRANTS.add(CONTACT_VIEW)
    _GRANTS.add(CONTACT_EDIT)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in _GRANTS,
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield
    _GRANTS.clear()


@pytest.fixture()
def client(db):  # noqa: F811 - fixture shadow is the point
    def _override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    _ACTOR["id"] = str(uuid.uuid4())
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def _seed_contact(db, *, respond_io_id: str | None = None) -> str:
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {
            "cid": respond_io_id or f"ZZT-{uuid.uuid4().hex[:8]}",
            "phone": f"+6000{uuid.uuid4().hex[:7]}",
            "sv": json.dumps({}),
        },
    )
    db.commit()
    return db.execute(text("SELECT id FROM respond_contacts ORDER BY created_at DESC LIMIT 1")).scalar()


# --------------------------------------------------------------------------------- #
# Column-level: default, migration shape (blank schema / create_all)
# --------------------------------------------------------------------------------- #


def test_new_row_inserted_without_the_column_value_reads_true(db):
    """D7-style owner default: on for everyone unless explicitly turned off."""
    contact_id = _seed_contact(db)
    value = db.execute(
        text("SELECT chatbot_stock_allowed FROM respond_contacts WHERE id = :i"),
        {"i": contact_id},
    ).scalar()
    assert value is True


# --------------------------------------------------------------------------------- #
# Route surface: PUT .../contacts/{id}/chatbot, GET contact
# --------------------------------------------------------------------------------- #


def test_put_chatbot_accepts_stock_allowed(db, client):
    contact_id = _seed_contact(db)
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={"chatbot_stock_allowed": False})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chatbot_stock_allowed"] is False, body

    stored = db.execute(
        text("SELECT chatbot_stock_allowed FROM respond_contacts WHERE id = :i"),
        {"i": contact_id},
    ).scalar()
    assert stored is False


def test_put_chatbot_absent_stock_allowed_leaves_existing_value_alone(db, client):
    contact_id = _seed_contact(db)
    # Turn it off first...
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={"chatbot_stock_allowed": False})
    assert resp.status_code == 200, resp.text
    # ...then a save that never mentions the field must not silently flip it back on -
    # the same "absent means leave it alone" rule `chatbot_recall_enabled` already has.
    resp = client.put(f"{BASE}/{contact_id}/chatbot", json={"chatbot_profile": {"language": "en"}})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chatbot_stock_allowed"] is False, body


def test_get_contact_detail_returns_chatbot_stock_allowed(db, client):
    """Through `ContactService.contact_to_response_dict` - the ONE manual dict builder
    this codebase has for a contact response (the list endpoint, `list_contacts`,
    calls the same function per row rather than a second one - confirmed by reading
    `contact_service.py`, so there is no separate "list serializer" to update here)."""
    contact_id = _seed_contact(db)
    resp = client.get(f"{BASE}/{contact_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "chatbot_stock_allowed" in body, body
    assert body["chatbot_stock_allowed"] is True


# --------------------------------------------------------------------------------- #
# Engine end to end: contract 61/62 reads the CONTACT ROW, never the envelope
# --------------------------------------------------------------------------------- #


def _set_stock_allowed(session_factory, *, contact_id, allowed: bool) -> None:
    db = session_factory()
    db.execute(
        text("UPDATE respond_contacts SET chatbot_stock_allowed = :a WHERE respond_io_id = :c"),
        {"a": allowed, "c": str(contact_id)},
    )
    db.commit()


def _seed_engine_contact(session_factory, *, contact_id) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": str(contact_id), "phone": "+60000000009", "sv": json.dumps({"variables": {}})},
    )
    db.commit()


class TestStockAllowedReadsTheContactRowNotTheEnvelope:
    def test_column_true_empty_custom_fields_denial_on_is_not_denied(
        self, session_factory, system_settings_row, stub_parser, stub_access
    ):
        from app.models.user import SystemSetting

        _seed_engine_contact(session_factory, contact_id=CONTACT_ID)
        _set_stock_allowed(session_factory, contact_id=CONTACT_ID, allowed=True)
        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        setting.chatbot_stock_denial_enabled = True
        db.commit()

        stub_parser(_parser_output(intent_hint="check_stock", domain_hint="inventory", demand_qty=5))
        stub_access()

        envelope = _envelope()
        envelope.contact["custom_fields"] = []
        envelope.message["message"]["messageId"] = "ZZT-stock-allowed-true"

        result = engine_mod.run_turn(envelope, session_factory=session_factory)
        assert result.branch_kind not in ("demand_qty", "stock_denied"), result.branch_kind

    def test_column_false_no_demand_qty_asks_for_qty(
        self, session_factory, system_settings_row, stub_parser, stub_access
    ):
        from app.models.user import SystemSetting

        _seed_engine_contact(session_factory, contact_id=CONTACT_ID)
        _set_stock_allowed(session_factory, contact_id=CONTACT_ID, allowed=False)
        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        setting.chatbot_stock_denial_enabled = True
        db.commit()

        stub_parser(_parser_output(intent_hint="check_stock", domain_hint="inventory", demand_qty=None))
        stub_access()

        envelope = _envelope()
        envelope.contact["custom_fields"] = []
        envelope.message["message"]["messageId"] = "ZZT-stock-allowed-false-no-qty"

        result = engine_mod.run_turn(envelope, session_factory=session_factory)
        assert result.branch_kind == "demand_qty", result.branch_kind

    def test_column_false_with_demand_qty_is_stock_denied(
        self, session_factory, system_settings_row, stub_parser, stub_access
    ):
        from app.models.user import SystemSetting

        _seed_engine_contact(session_factory, contact_id=CONTACT_ID)
        _set_stock_allowed(session_factory, contact_id=CONTACT_ID, allowed=False)
        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        setting.chatbot_stock_denial_enabled = True
        db.commit()

        stub_parser(_parser_output(intent_hint="check_stock", domain_hint="inventory", demand_qty=5))
        stub_access()

        envelope = _envelope()
        envelope.contact["custom_fields"] = []
        envelope.message["message"]["messageId"] = "ZZT-stock-allowed-false-with-qty"

        result = engine_mod.run_turn(envelope, session_factory=session_factory)
        assert result.branch_kind == "stock_denied", result.branch_kind

    def test_column_false_envelope_says_allowed_true_still_denied(
        self, session_factory, system_settings_row, stub_parser, stub_access
    ):
        """The envelope is IGNORED entirely - a stale/borrowed `is_allowed_stock: "true"`
        custom field must not override the contact row's own `chatbot_stock_allowed`."""
        from app.models.user import SystemSetting

        _seed_engine_contact(session_factory, contact_id=CONTACT_ID)
        _set_stock_allowed(session_factory, contact_id=CONTACT_ID, allowed=False)
        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        setting.chatbot_stock_denial_enabled = True
        db.commit()

        stub_parser(_parser_output(intent_hint="check_stock", domain_hint="inventory", demand_qty=5))
        stub_access()

        envelope = _envelope()
        envelope.contact["custom_fields"] = [{"name": "is_allowed_stock", "value": "true"}]
        envelope.message["message"]["messageId"] = "ZZT-stock-allowed-envelope-ignored"

        result = engine_mod.run_turn(envelope, session_factory=session_factory)
        assert result.branch_kind == "stock_denied", result.branch_kind

    def test_no_respond_contacts_row_fails_open_allowed(self, session_factory):
        """The owner's default is ON, and a contact with no `respond_contacts` row at
        all must fail OPEN on this one field - the same rule `turn_runtime.
        load_profile` already applies for a missing profile row.

        **Deliberately NOT a `run_turn` end-to-end test, unlike the four cases above**
        (measured this session): `engine._read_session_vars` /
        `conversation_variables_service.get_for_contact` 404s on ANY contact with no
        `respond_contacts` row at all, before the turn ever reaches the stock-check
        gate - unrelated to this feature, and true today on `main` regardless of this
        change. A row-less contact can therefore never reach `_stock_check_denied`
        through a real turn; this calls the gate directly instead, the same level
        `tests/chatbot/test_rearch_port_route_unit.py::TestStockDenialGate` already
        unit-tests the OLD envelope-based shape at.

        **Signature assumed, not specified by the ruling - flagged for the coder**:
        `_stock_check_denied(db, envelope, verdict)`, `db` added as the new leading
        argument (the same position `_stock_denial_enabled(db, row)` and every other
        `system_settings`-reading predicate in `engine.py` already takes it). If the
        coder picks a different shape this test's failure mode changes from
        "AssertionError: contact-row read denied when no row exists" to a
        TypeError/AttributeError on the call itself - still a legitimate red, just a
        different one, and worth a quick signature check before assuming this test is
        wrong.
        """
        db = session_factory()
        stub_parser_output = _parser_output(intent_hint="check_stock", domain_hint="inventory", demand_qty=5)
        envelope = _envelope()
        envelope.contact["custom_fields"] = []
        # No respond_contacts row for this contact id at all.
        denied = engine_mod._stock_check_denied(db, envelope, stub_parser_output)
        assert denied is False, (
            "a contact with no respond_contacts row at all must fail OPEN (owner "
            f"default is on), got denied={denied!r}"
        )
