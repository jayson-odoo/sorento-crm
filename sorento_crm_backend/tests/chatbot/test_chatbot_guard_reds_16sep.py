"""Guard reds, coordinator queue item 3 (16 Sep 2026): named contract lines with no
existing coverage, pinned as their own focused tests rather than folded into the CRUD
files that happened to touch the same route/module.

S9 - the last chatbot domain cannot be deleted, on BOTH arms that delete one
(`DELETE /system/chatbot/domains/{id}` and the deferred `chatbot_domain.delete` pending
action's own `_delete_chatbot_domain` handler) - `app/api/v1/system/chatbot_config.py::
refuse_if_last_domain` is the one guard both arms import, so both need their own test:
a coder who wired the pending-action arm to call the ORM directly instead of importing
the guard would pass a route-only test.

`load_profile` two-rows fails closed - AC-1503/S6: two `respond_contacts` rows for the
same `respond_io_id` (a namesake contact in another workspace, the docstring's own
scenario) must deny stock and recall rather than pick one.

Everything here runs on the blank-schema fixture (`tests/chatbot/conftest.py::
session_factory`), seeding its own ZZT-prefixed rows - no shared/migration-seeded data
touched, so the destructive S9 tests cannot affect the real seeded chatbot_domains rows
`test_rearch_s5_config_routes.py`'s own tests (on the real migrated DB) read.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.main import app
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.chatbot_policy import ChatbotDomain
from app.services.user_service import UserPermissionService

from tests.chatbot.test_turns_admin_api import db  # noqa: F401 - blank-schema session fixture
from tests._pg_fixture import unique_code

MANAGE = "system.chatbot_config.manage"
DOMAINS_BASE = "/api/v1/system/chatbot/domains"

_GRANTS: set[str] = {MANAGE}
_ACTOR: dict = {"id": None, "name": "ZZT Guard Reds Tester"}


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    _GRANTS.clear()
    _GRANTS.add(MANAGE)
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


def _domain_row(db, *, name: str) -> ChatbotDomain:
    row = ChatbotDomain(
        name=name,
        label=f"ZZT {name}",
        intents=["zzt_check"],
        tools=[],
        primary_tool=None,
        escalation_team_code=None,
        switch_words=["zzt"],
        narrowing={},
        takes_date_filter=False,
        reveal_key=None,
        supported=True,
        ladder=[],
        sort_order=999,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestS9LastChatbotDomainCannotBeDeleted:
    def test_the_route_refuses_with_409_on_the_last_domain(self, client, db) -> None:
        only = _domain_row(db, name=unique_code("only_domain"))

        resp = client.delete(f"{DOMAINS_BASE}/{only.id}")

        assert resp.status_code == 409, resp.text
        still_there = db.query(ChatbotDomain).filter(ChatbotDomain.id == only.id).first()
        assert still_there is not None, "a 409 must not have deleted the row anyway"

    def test_the_route_allows_deleting_down_to_one(self, client, db) -> None:
        first = _domain_row(db, name=unique_code("first"))
        second = _domain_row(db, name=unique_code("second"))

        resp = client.delete(f"{DOMAINS_BASE}/{second.id}")

        assert resp.status_code in (200, 204), resp.text
        remaining = db.query(ChatbotDomain).filter(ChatbotDomain.id == first.id).first()
        assert remaining is not None

    def test_the_pending_action_handler_refuses_the_same_way(self, db) -> None:
        """`_delete_chatbot_domain` (`app/services/record_actions.py`), the deferred
        `chatbot_domain.delete` pending action's own execute callback - driven directly
        rather than through the full stage/countdown/commit HTTP cycle `test_pending_
        actions.py` already covers generically, because what this guards is the DOMAIN-
        SPECIFIC refusal, not the generic pending-action mechanism."""
        from app.services.record_actions import _delete_chatbot_domain

        only = _domain_row(db, name=unique_code("only_domain_deferred"))

        from app.services.error_handler import AppException

        with pytest.raises(AppException) as excinfo:
            _delete_chatbot_domain(db, {"entity_id": only.id})
        assert excinfo.value.status_code == 409

        still_there = db.query(ChatbotDomain).filter(ChatbotDomain.id == only.id).first()
        assert still_there is not None

    def test_the_pending_action_handler_allows_deleting_down_to_one(self, db) -> None:
        from app.services.record_actions import _delete_chatbot_domain

        first = _domain_row(db, name=unique_code("first_deferred"))
        second = _domain_row(db, name=unique_code("second_deferred"))

        _delete_chatbot_domain(db, {"entity_id": second.id})
        db.commit()

        remaining = db.query(ChatbotDomain).filter(ChatbotDomain.id == first.id).first()
        assert remaining is not None
        gone = db.query(ChatbotDomain).filter(ChatbotDomain.id == second.id).first()
        assert gone is None


class TestLoadProfileTwoRowsFailsClosed:
    def _seed_two_rows_same_respond_id(self, db, *, respond_io_id: str) -> None:
        for _ in range(2):
            db.execute(
                text(
                    "INSERT INTO respond_contacts "
                    "(id, respond_io_id, phone_number, session_vars, chatbot_stock_allowed) "
                    "VALUES (gen_random_uuid()::text, :cid, :phone, CAST('{}' AS jsonb), true)"
                ),
                {"cid": respond_io_id, "phone": f"+60{uuid.uuid4().int % 10**9}"},
            )
        db.commit()

    def test_two_matching_rows_deny_stock_and_recall(self, db) -> None:
        from app.services.chatbot import turn_runtime

        respond_io_id = unique_code("ambiguous_contact")
        self._seed_two_rows_same_respond_id(db, respond_io_id=respond_io_id)

        profile, recall_enabled = turn_runtime.load_profile(db, respond_io_id, space_id=None)

        assert profile.stock_allowed is False, (
            "an ambiguous contact (two rows for the same respond_io_id) must deny "
            "stock, even though both seeded rows have chatbot_stock_allowed=true"
        )
        assert recall_enabled is False

    def test_a_single_matching_row_is_unaffected(self, db) -> None:
        from app.services.chatbot import turn_runtime

        respond_io_id = unique_code("single_contact")
        db.execute(
            text(
                "INSERT INTO respond_contacts "
                "(id, respond_io_id, phone_number, session_vars, chatbot_stock_allowed, "
                "chatbot_recall_enabled) "
                "VALUES (gen_random_uuid()::text, :cid, :phone, CAST('{}' AS jsonb), true, true)"
            ),
            {"cid": respond_io_id, "phone": f"+60{uuid.uuid4().int % 10**9}"},
        )
        db.commit()

        profile, recall_enabled = turn_runtime.load_profile(db, respond_io_id, space_id=None)

        assert profile.stock_allowed is True
        assert recall_enabled is True


class TestB4FocusFromWireToleratesTheOrderStatusRename:
    """`turn/state.py::focus_from_wire` is "tolerant by design": a slot written by an
    older build may hold a shape this one no longer writes, and a focus that cannot be
    read is a forgotten conversation, not a failed turn - the function's own docstring
    already states this and already honours it for `customer` (singular) -> `customers`
    (plural). `order_status` -> `status` is the SAME class of rename (the wire shape's
    own `focus_to_wire`/`focus_from_wire` pair calls the field `status` today) and has
    no fallback at all (grep-confirmed: `raw.get("status")` is the only read,
    `raw.get("order_status")` appears nowhere in the module) - a contact whose focus was
    persisted by an older build under the old name loses its order-status filter
    silently the next time this build reads it back, exactly the compatibility class
    the singular/plural fallback exists to prevent.

    CONFIRMED GAP, kept red (AC-1592, this session): pure unit test, no DB, no engine -
    `focus_from_wire` in isolation.
    """

    def test_a_legacy_order_status_key_is_read_as_status(self) -> None:
        from app.services.chatbot.turn.state import focus_from_wire

        focus = focus_from_wire({"order_status": "so_outstanding"})

        assert focus.status == "so_outstanding", (
            "an older build's `focus.order_status` must still be read as `status` - "
            f"got {focus.status!r}"
        )

    def test_the_current_status_key_still_wins_when_both_are_present(self) -> None:
        from app.services.chatbot.turn.state import focus_from_wire

        focus = focus_from_wire({"status": "do_outstanding", "order_status": "so_outstanding"})

        assert focus.status == "do_outstanding"
