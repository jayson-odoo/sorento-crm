"""S3's own two pieces of new behaviour: the lane switch, and `/turn/complete`.

`test_s3_canned_and_ideate.py` (the tester's) pins what each lane SAYS. This file pins the
two things that decide whether a lane runs at all and how n8n reaches the tail:

* **`system_settings.chatbot_completed_lanes`** - the DATA half of the completion rule.
  The code half is `lanes.canned.COMPLETED_BRANCH_KINDS`, and a lane needs BOTH, so the
  cutover is a data change the owner makes after a shadow window and the rollback is
  editing the list. The column ships EMPTY, which is why the tester's integration tests
  see a delegated turn: nothing completes until somebody says so.
* **`POST /chat/turn/complete`** - the same tail call as `/turn/{id}/complete`, with the
  turn identified from the body instead of the path. Agreed with the n8n side so their cut
  touches one workflow: `sub-output` holds the `ctx` and not the turn id.

Postgres only, through the blank schema; the parser, the access check and (for ideate) the
MCP call are stubbed at their own seams, so nothing here reaches an LLM, n8n or a live MCP
server.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.lanes import canned as canned_lanes
from tests.chatbot.test_chat_turn_endpoint import api_key, client  # noqa: F401 - fixtures
from tests.chatbot.test_engine import (  # noqa: F401 - fixtures reused by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)

_BY_BODY_URL = "/api/v1/external/chat/turn/complete"
MESSAGE_ID = "ZZT-msg-1"


def _set_completed_lanes(session_factory, lanes: list[str]) -> None:
    db = session_factory()
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting()
        db.add(row)
    row.chatbot_completed_lanes = lanes
    db.commit()


def _session_vars_raw(session_factory) -> Any:
    return session_factory().execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
        {"c": CONTACT_ID},
    ).scalar()


class TestTheCompletedLaneSwitch:
    """BOTH halves, and neither alone is enough."""

    def test_the_column_ships_empty_so_nothing_completes_on_deploy(self, session_factory):
        db = session_factory()
        row = SystemSetting()
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.chatbot_completed_lanes == [], (
            "the CRM must ship inert: a lane that completed the moment the code landed "
            "would change what a customer reads before anyone decided to"
        )

    def test_a_lane_the_owner_has_not_switched_on_still_delegates(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        _set_completed_lanes(session_factory, [])
        stub_parser(_parser_output(message_type="clarification", domain_hint=None))
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "clarify_menu"
        assert result.delegate == "clarify_menu", "the switch is off, so n8n still answers"
        assert result.reply is None

    def test_a_lane_the_owner_switched_on_is_completed(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        _set_completed_lanes(session_factory, ["clarify_menu"])
        stub_parser(
            _parser_output(
                message_type="clarification", domain_hint=None, user_goal="checking stock"
            )
        )
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "clarify_menu"
        assert result.delegate is None
        assert result.reply["text"].startswith("I see you're checking stock, Let me understand more.")
        assert result.actions[-1]["kind"] == "send_message"

    def test_a_lane_the_code_cannot_finish_is_never_completed_however_it_is_configured(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        """The CODE half is a wall: `business_query` is S6's and no list may claim it."""
        _set_completed_lanes(session_factory, ["business_query", "check_promotion"])
        stub_parser(_parser_output())
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "business_query"
        assert result.delegate == "business_query"

    def test_the_two_halves_are_declared_once_each(self):
        """A lane named in the settings list that the code cannot finish is a typo the
        engine ignores; a lane the code CAN finish is the closed set S3 ported."""
        assert canned_lanes.COMPLETED_BRANCH_KINDS == {
            "access_denied",
            "escalate_offer",
            "escalation_declined",
            "clarify_menu",
            "not_supported",
            "demand_qty",
            "offer_hold",
            "ideate",
        }
        assert canned_lanes.handles("business_query", ["business_query"]) is False
        assert canned_lanes.handles("clarify_menu", []) is False
        assert canned_lanes.handles("clarify_menu", ["clarify_menu"]) is True

    def test_switching_a_lane_off_again_is_the_rollback(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        """No deploy: the same turn delegates again the moment the list is edited."""
        _set_completed_lanes(session_factory, ["clarify_menu"])
        stub_parser(_parser_output(message_type="clarification", domain_hint=None))
        stub_access()
        first = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert first.delegate is None

        _set_completed_lanes(session_factory, [])
        envelope = _envelope()
        envelope.message["message"]["messageId"] = "ZZT-msg-rollback"
        second = engine_mod.run_turn(envelope, session_factory=session_factory)
        assert second.delegate == "clarify_menu"


class TestAccessDeniedNeverWritesTheSession:
    """The one completed lane that answers WITHOUT the tail (and so without a write)."""

    def test_access_denied_answers_and_remembers_nothing(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        _set_completed_lanes(session_factory, ["access_denied"])
        stub_parser(_parser_output())
        stub_access(allowed=False, decision="deny_unknown_agent")
        before = _session_vars_raw(session_factory)

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "access_denied"
        assert result.delegate is None
        assert result.reply["text"].startswith("Sorry, you are not allowed to access ")
        assert _session_vars_raw(session_factory) == before, (
            "a contact refused the agent must not have the turn written into their memory"
        )
        row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).one()
        assert row.status == "done"
        assert [r["stage"] for r in row.trace][-1] == "sent"


class TestCompleteByBody:
    """`/turn/complete`: same tail, turn identified from the body."""

    @pytest.fixture()
    def delegated_turn(self, session_factory, seeded, stub_parser, stub_access):
        _set_completed_lanes(session_factory, [])
        stub_parser(_parser_output(message_type="business_query", domain_hint="master_products"))
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert result.delegate, "the fixture needs a DELEGATED turn to complete"
        return result

    @staticmethod
    def _body(result) -> dict[str, Any]:
        return {
            "item": {"branch_kind": "not_supported"},
            "ctx": result.ctx,
            "result": None,
            "resolved": None,
            "gate": None,
            "offer_hold": None,
            "suggest_offer": None,
            "not_found": None,
            "incoming_picker": None,
            "access_choice": None,
            "crossdomain_render": None,
            "answer": None,
            "clarify": None,
        }

    def _post(self, client, api_key, body):
        return client.post(_BY_BODY_URL, json=body, headers={"X-API-Key": api_key})

    def test_happy_path_completes_the_turn_the_body_names(
        self, client, api_key, session_factory, monkeypatch, delegated_turn
    ):
        monkeypatch.setattr("app.api.v1.external.chat.SessionLocal", session_factory)

        resp = self._post(client, api_key, self._body(delegated_turn))

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["turn_id"] == delegated_turn.turn_id
        assert body["reply"]["text"], "the tail composed no reply"
        row = (
            session_factory()
            .query(ChatbotTurn)
            .filter(ChatbotTurn.id == delegated_turn.turn_id)
            .one()
        )
        assert row.status == "done"
        assert row.stage == "remembered"

    def test_no_matching_turn_is_a_404_that_names_the_pair(
        self, client, api_key, session_factory, monkeypatch, seeded
    ):
        monkeypatch.setattr("app.api.v1.external.chat.SessionLocal", session_factory)

        class _Fake:
            ctx = {
                "contact": {"id": CONTACT_ID},
                "text": {"message": {"messageId": "ZZT-msg-nobody"}},
            }
            turn_id = "unused"

        resp = self._post(client, api_key, self._body(_Fake()))

        assert resp.status_code == 404, resp.text
        detail = json.dumps(resp.json())
        assert "ZZT-msg-nobody" in detail and CONTACT_ID in detail

    def test_a_turn_that_never_delegated_is_a_409(
        self, client, api_key, session_factory, monkeypatch, seeded, stub_parser, stub_access
    ):
        monkeypatch.setattr("app.api.v1.external.chat.SessionLocal", session_factory)
        from app.services.chatbot.head import parser as parser_mod

        _set_completed_lanes(session_factory, [])
        stub_parser(error=parser_mod.ParserError("boom"))
        stub_access()
        failed = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert failed.status == "failed"

        class _Fake:
            ctx = {
                "contact": {"id": CONTACT_ID},
                "text": {"message": {"messageId": MESSAGE_ID}},
            }

        resp = self._post(client, api_key, self._body(_Fake()))

        assert resp.status_code == 409, resp.text
        assert "CHATBOT_TURN_NOT_DELEGATED" in json.dumps(resp.json())

    def test_the_highest_attempt_wins(
        self, client, api_key, session_factory, monkeypatch, delegated_turn
    ):
        """R4's manual retry: completing the OLDER attempt would fold the lane's result
        into the row nobody is watching, and leave the live one delegated forever.

        The unique index on `(contact_respond_id, message_id)` is what normally makes two
        rows for one message impossible, so it is DROPPED inside this test's transaction
        to reach the case at all - the ordering is defence for the day that index is
        relaxed (a console turn already carries a NULL message id, which Postgres treats
        as distinct), not for a shape production can produce today. Dropping it inside the
        savepoint means it comes back on rollback.
        """
        monkeypatch.setattr("app.api.v1.external.chat.SessionLocal", session_factory)
        from tests import _pg_fixture

        schema = f'{_pg_fixture._BLANK["name"]}_chatbot'
        db = session_factory()
        db.execute(
            text(f'ALTER TABLE "{schema}".turns DROP CONSTRAINT uq_chatbot_turns_contact_message')
        )
        first = db.query(ChatbotTurn).filter(ChatbotTurn.id == delegated_turn.turn_id).one()
        retry = ChatbotTurn(
            contact_respond_id=first.contact_respond_id,
            message_id=first.message_id,
            ingress="retry",
            envelope=first.envelope,
            is_test=False,
            status="delegated",
            stage="routed",
            attempt=2,
            trace=[],
            response=first.response,
        )
        db.add(retry)
        db.commit()

        resp = self._post(client, api_key, self._body(delegated_turn))

        assert resp.status_code == 200, resp.text
        assert resp.json()["turn_id"] == str(retry.id), "the older attempt was completed"

    def test_every_response_field_survives_serialisation(
        self, client, api_key, session_factory, monkeypatch, delegated_turn
    ):
        """`response_model` silently DROPS an undeclared field, so each one is asserted."""
        monkeypatch.setattr("app.api.v1.external.chat.SessionLocal", session_factory)
        canned = {
            "turn_id": delegated_turn.turn_id,
            "reply": {
                "text": "hi",
                "quick_replies": "a,b",
                "result_set": [{"idx": 1}],
                "attachments_src": [{"url": "s3://x"}],
            },
            "actions": [{"kind": "send_message", "text": "hi", "dry_run": False}],
            "session_patch": {"variables": {"pending": None}},
        }

        class _Fake:
            def as_dict(self):
                return canned

        monkeypatch.setattr("app.api.v1.external.chat.complete_turn", lambda *a, **k: _Fake())

        resp = self._post(client, api_key, self._body(delegated_turn))

        assert resp.status_code == 200, resp.text
        body = resp.json()
        for key in ("turn_id", "reply", "actions", "session_patch"):
            assert key in body, f"{key!r} missing from the response body: {body}"
        assert body["reply"]["attachments_src"] == [{"url": "s3://x"}]
        assert body["reply"]["result_set"] == [{"idx": 1}]
        assert body["actions"][0]["kind"] == "send_message"

    def test_the_path_form_is_unchanged(
        self, client, api_key, session_factory, monkeypatch, delegated_turn
    ):
        """The id-less route is an ADDITION; `/turn/{id}/complete` keeps working."""
        monkeypatch.setattr("app.api.v1.external.chat.SessionLocal", session_factory)

        resp = client.post(
            f"/api/v1/external/chat/turn/{delegated_turn.turn_id}/complete",
            json=self._body(delegated_turn),
            headers={"X-API-Key": api_key},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["turn_id"] == delegated_turn.turn_id
