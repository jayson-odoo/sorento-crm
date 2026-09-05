"""Everything that can go wrong AFTER the turn row exists is recorded, never dropped.

Review B1: `parser.resolve_config`, `check_access` and `decide()` all sat outside the one
try/except, so a provider error or the stock predicate throwing on a contact with no
`is_allowed_stock` field escaped `run_turn` entirely - the row stayed `processing` with a
null error and no trace, and the endpoint's generic handler turned it into a 500. That is
H32's dropped turn, arriving by a different route than the one H32 named.

Review S2: a duplicate delivery returned `ctx: null` / `item: null`, which n8n's AC-110
re-emitters (`$('build-ctx').first().json.ctx.<key>`) throw on. The turn's answer is now
persisted and replayed.

Reuses the fixtures in `tests/chatbot/test_engine.py` rather than restating them - the
envelope shape and the stubbing seams are the same, and two copies would drift.
"""
from __future__ import annotations

import pytest

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import Envelope, TurnRequest
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_engine import (  # noqa: F401  - fixtures are used by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)


def _row(session_factory, turn_id: str) -> ChatbotTurn:
    return session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()


def _only_row(session_factory) -> ChatbotTurn:
    rows = (
        session_factory()
        .query(ChatbotTurn)
        .filter(ChatbotTurn.contact_respond_id == CONTACT_ID)
        .all()
    )
    assert len(rows) == 1, f"expected exactly one turn row, found {len(rows)}"
    return rows[0]


class TestNothingEscapesRunTurn:
    """B1. Each of these used to leave a `processing` row and raise out of `run_turn`."""

    def test_resolve_config_failing_is_a_recorded_failed_turn(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        stub_parser()
        stub_access()

        def _boom(db, *, current_date):
            raise parser_mod.ParserError("AI assistant configuration is not set")

        monkeypatch.setattr(parser_mod, "resolve_config", _boom)

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.status == "failed"
        assert result.reply["text"] == parser_mod.PARSER_ERROR_REPLY
        row = _only_row(session_factory)
        assert row.status == "failed"
        assert row.stage == "received"
        assert "configuration is not set" in row.error
        assert row.trace and row.trace[-1]["status"] == "failed"

    def test_the_access_service_failing_is_a_recorded_failed_turn(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        stub_parser()
        stub_access()
        monkeypatch.setattr(
            engine_mod,
            "check_access",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("access service down")),
        )

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.status == "failed"
        row = _only_row(session_factory)
        assert row.status == "failed"
        assert row.stage == "access"
        assert "access service down" in row.error

    def test_the_stock_predicate_throwing_is_a_recorded_failed_turn(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        """S8's real consequence: with the flag ON and no `is_allowed_stock` field, live's
        own expression throws. The port reproduces the throw; this proves the turn is
        recorded rather than dropped when it does."""
        qf = {
            **_parser_output(),
            "intent_hint": "check_stock",
            "domain_hint": "inventory",
        }
        stub_parser(qf)
        stub_access()
        monkeypatch.setattr(engine_mod, "_stock_denial_enabled", lambda db: True)

        envelope = _envelope()
        envelope.contact["custom_fields"] = []  # no is_allowed_stock at all

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert result.status == "failed"
        row = _only_row(session_factory)
        assert row.status == "failed"
        assert row.stage == "routed"
        assert row.error

    def test_the_error_reply_is_still_handed_to_the_caller_to_send(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        stub_parser()
        stub_access()
        monkeypatch.setattr(
            engine_mod,
            "check_access",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert [a["kind"] for a in result.actions] == ["send_message"]
        assert result.actions[0]["text"] == parser_mod.PARSER_ERROR_REPLY

    def test_the_human_intervened_action_survives_a_later_failure(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        """The caller must still clear the flag even though the turn failed after it."""
        stub_parser()
        stub_access()
        monkeypatch.setattr(
            engine_mod,
            "check_access",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        envelope = _envelope()
        envelope.contact["custom_fields"] = [{"name": "is_human_intervened", "value": "true"}]

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert [a["kind"] for a in result.actions] == ["update_contact_fields", "send_message"]


class TestDuplicateReplaysTheAnswer:
    """S2. n8n's re-emitters read `response.ctx.<key>`; a null there throws."""

    def test_the_second_delivery_gets_the_original_ctx_and_item(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        stub_parser()
        stub_access()
        first = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        second = engine_mod.run_turn(
            _envelope(ingress="poller"), session_factory=session_factory
        )

        assert second.duplicate is True
        assert second.ctx == first.ctx
        assert second.item == first.item
        assert second.branch_kind == first.branch_kind
        assert second.delegate == first.delegate

    def test_the_stored_response_is_the_answer_not_a_summary_of_it(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        stub_parser()
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        stored = _row(session_factory, result.turn_id).response
        # S6a added `delegate_payload`: a duplicate delivery must replay the business
        # lane's resolve+gate result too, or the caller re-enters `resolve-arm` with
        # nothing and n8n's presence gates all take their FALSE arms. Null here because
        # `CHATBOT_BUSINESS_LANE_ENABLED` is off by default; the KEY is the contract.
        assert set(stored) == {
            "ctx",
            "item",
            "actions",
            "delegate_payload",
            "delegate_error",
        }
        assert stored["delegate_payload"] is None
        # Null on a turn where the shadow lane did not run OR did not fail. Non-null is
        # the operator's "the CRM lane disagreed with n8n today" signal (review S1).
        assert stored["delegate_error"] is None
        assert set(stored["ctx"]) == {"contact", "text", "session", "parse", "access", "media"}
        assert stored["item"]["branch_kind"] == result.branch_kind

    def test_a_duplicate_of_a_FAILED_turn_replays_the_failure_not_a_null_ctx(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        """A failed turn stores no answer, so `ctx` is legitimately absent - but the
        caller still learns it is a duplicate and still gets the branch_kind (null) and
        status, rather than a fresh LLM call."""
        stub_parser(error=parser_mod.ParserError("boom"))
        stub_access()
        first = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        second = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert first.status == "failed"
        assert second.duplicate is True
        assert second.turn_id == first.turn_id
        assert second.status == "failed"
        assert second.ctx is None


class TestStageIsNamedOnEveryFailure:
    @pytest.mark.parametrize(
        ("seam", "expected_stage"),
        [
            ("resolve_config", "received"),
            ("access", "access"),
        ],
    )
    def test_the_recorded_stage_is_where_it_actually_stopped(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch, seam, expected_stage
    ) -> None:
        stub_parser()
        stub_access()
        if seam == "resolve_config":
            monkeypatch.setattr(
                parser_mod,
                "resolve_config",
                lambda db, *, current_date: (_ for _ in ()).throw(RuntimeError("x")),
            )
        else:
            monkeypatch.setattr(
                engine_mod,
                "check_access",
                lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")),
            )

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert result.stage == expected_stage
        assert _only_row(session_factory).stage == expected_stage


class TestEnvelopeValidation:
    """A malformed envelope is the CALLER's mistake, so it must read as 422, not 500."""

    def test_a_contact_without_an_id_is_refused_at_the_schema(self) -> None:
        import pydantic

        with pytest.raises(pydantic.ValidationError) as excinfo:
            Envelope(message={}, contact={"firstName": "ZZT"})
        error = excinfo.value.errors()[0]
        assert error["loc"] == ("contact",)
        assert "contact.id is required" in error["msg"]

    @pytest.mark.parametrize("contact", [{}, {"id": None}, {"id": ""}])
    def test_every_empty_form_of_the_id_is_refused(self, contact: dict) -> None:
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            Envelope(message={}, contact=contact)

    def test_a_real_id_passes(self) -> None:
        assert Envelope(message={}, contact={"id": "900000009"}).contact["id"] == "900000009"

    def test_the_endpoint_answers_422_and_names_the_field(self) -> None:
        """The whole point: an operator reading the response learns what to fix.

        Built on a bare app around the real request model, so the assertion is about
        `TurnRequest`'s validation rather than about auth or the module guard, which have
        their own tests in `test_module_and_endpoint.py`.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        api = FastAPI()

        @api.post("/turn")
        def turn(payload: TurnRequest):  # pragma: no cover - never reached
            return {"ok": True}

        client = TestClient(api, raise_server_exceptions=False)
        response = client.post(
            "/turn", json={"envelope": {"message": {}, "contact": {"firstName": "ZZT"}}}
        )
        assert response.status_code == 422
        body = response.text
        assert "contact" in body
        assert "contact.id is required" in body


class TestDuplicateWhileTheFirstTurnIsStillRunning:
    """The LIKELY timing, not the edge case.

    `response` is written when a turn CLOSES, so a duplicate arriving mid-turn has nothing
    to replay. Two injectors seconds apart against a turn that takes seconds means this is
    the common shape, and the engine does NOT try to solve it: waiting would buy nothing,
    because the caller must not answer twice either way. What it MUST do is say so clearly,
    so `status` tells a caller "not finished yet" apart from "failed, nothing to say".
    """

    def test_it_returns_duplicate_with_status_processing_and_null_ctx(
        self, session_factory, seeded
    ) -> None:
        from app.models.chatbot_turn import ChatbotTurn

        db = session_factory()
        row = ChatbotTurn(
            contact_respond_id=CONTACT_ID,
            message_id="ZZT-msg-1",
            ingress="webhook",
            envelope={},
            is_test=False,
            status="processing",   # inserted, not yet closed
            stage="received",
            attempt=1,
            trace=[],
        )
        db.add(row)
        db.commit()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.duplicate is True
        assert result.status == "processing"
        assert result.ctx is None and result.item is None
        assert result.branch_kind is None

    def test_a_finished_duplicate_is_distinguishable_from_an_in_flight_one(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        stub_parser()
        stub_access()
        engine_mod.run_turn(_envelope(), session_factory=session_factory)
        finished = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert finished.duplicate is True
        assert finished.status == "delegated"
        assert finished.ctx is not None, (
            "a duplicate of a CLOSED turn must replay the stored answer; only the "
            "in-flight and failed cases legitimately hand back nulls"
        )


class TestTheBusinessLaneWithTheSwitchOn:
    """S6c round 2: what a turn does when the CRM owns the lane and something breaks.

    Three cells, and they are not the same answer:

    * the resolver RAISES - the lane is broken in a way it does not model, so the turn
      goes to the n8n lane that can still answer it (its Switch output exists until
      AC-610). Without the restored delegate the row closed `done` with no reply and no
      delegate: a silent turn.
    * the fetch found NO TOOL (`outcome == "not_found"`) - a genuine absence, and H11 /
      AC-604 say the CRM answers it through the miss lane.
    * the fetch FAILED (MCP raise, error envelope, tool search down) - the read never ran,
      so the customer must not be told "I could not find anything". Recorded `failed` at
      `looked_up` with the generic error reply, which is what R4's manual retry acts on.
      Live agrees: `Call 'sub-get-results'` is `continueErrorOutput` into
      `set-ran-query-formulator` ("There is some error encountered by the AI: ..."), never
      into `not-found-error-message`.

    Both switch positions are graded for every cell, because "the lane is off" is the
    state every install starts in.
    """

    @staticmethod
    def _enable(session_factory, row, lanes):
        from app.models.user import SystemSetting

        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == row.id).one()
        setting.chatbot_completed_lanes = lanes
        db.commit()

    def _wire(self, monkeypatch, *, fetch=None, resolve_raises=False):
        """Route the turn into the business lane and stub the two lane seams."""
        from app.config import settings
        from app.services.chatbot.lanes.business.services import ResolveGateServices

        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", True)
        monkeypatch.setattr(
            engine_mod, "decide", lambda ctx, *, stock_denial_enabled, **_: ("business_query", {})
        )
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: ResolveGateServices(
                access_types=lambda **_: [],
                resolve_entity=lambda body: {
                    "tokens": [],
                    "resolutions": [],
                    "unresolved_tokens": [],
                },
                probe=lambda **_: None,
            ),
        )
        if resolve_raises:
            monkeypatch.setattr(
                engine_mod.business,
                "run_until_exit",
                lambda *a, **k: (_ for _ in ()).throw(RuntimeError("resolver unavailable")),
            )
            return []
        monkeypatch.setattr(
            engine_mod.business,
            "run_until_exit",
            lambda *a, **k: {
                "delegate": "business_query",
                "payload": {"_exit_kind": "continue", "resolved": {}, "gate": {}},
            },
        )
        monkeypatch.setattr(engine_mod.business, "run_fetch", lambda *a, **k: fetch)
        answered: list = []
        monkeypatch.setattr(
            engine_mod.business,
            "complete_answer",
            lambda payload, **kwargs: answered.append(payload)
            or {"reply": {"text": "Couldn't find that.", "quick_replies": []}, "actions": []},
            raising=False,
        )
        return answered

    @staticmethod
    def _error_fragment(reason, outcome=None):
        from app.services.chatbot.lanes import business

        return business._error_fragment(reason, outcome=outcome)

    # -- the resolver raises ------------------------------------------------ #

    def test_a_resolver_failure_on_an_enabled_lane_still_delegates(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        self._enable(session_factory, system_settings_row, ["business_query"])
        self._wire(monkeypatch, resolve_raises=True)
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.delegate == "business_query", (
            "the lane crashed, so the turn belongs to n8n while its Switch output exists - "
            "a None delegate here is a turn nobody answers"
        )
        assert result.stage == "looked_up"
        row = _only_row(session_factory)
        assert row.status == "delegated"
        assert row.stage == "looked_up"
        assert not (row.status == "done" and result.reply is None), "a silent turn"

    def test_a_resolver_failure_with_the_lane_off_is_unchanged(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        assert (system_settings_row.chatbot_completed_lanes or []) == []
        self._wire(monkeypatch, resolve_raises=True)
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.delegate == "business_query"
        assert result.stage == "looked_up"
        assert _only_row(session_factory).status == "delegated"

    # -- the fetch found no tool (a genuine absence) ------------------------- #

    def test_no_tool_matched_on_an_enabled_lane_is_answered_by_the_crm(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        self._enable(session_factory, system_settings_row, ["business_query"])
        answered = self._wire(
            monkeypatch,
            fetch=self._error_fragment("no MCP tool matched this question", "not_found"),
        )
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert answered, "H11 / AC-604: a genuine absence is answered, not left silent"
        assert answered[0]["fetch"]["outcome"] == "not_found", (
            "the arm's own outcome is what tells the answer half it may say 'not found'"
        )
        assert result.delegate is None
        assert result.status != "failed"

    def test_no_tool_matched_with_the_lane_off_delegates(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        answered = self._wire(
            monkeypatch,
            fetch=self._error_fragment("no MCP tool matched this question", "not_found"),
        )
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert not answered
        assert result.delegate == "business_query"
        assert result.stage == "looked_up"

    # -- the fetch itself failed (infrastructure) --------------------------- #

    def test_an_mcp_failure_on_an_enabled_lane_is_a_failed_turn_not_a_not_found(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        self._enable(session_factory, system_settings_row, ["business_query"])
        answered = self._wire(
            monkeypatch,
            fetch=self._error_fragment("MCP tool crm_master_products_list failed: timeout"),
        )
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert not answered, (
            "an outage must not render the miss lane - that asserts an absence the read "
            "never established"
        )
        assert result.status == "failed"
        assert result.stage == "looked_up"
        assert result.reply["text"] == engine_mod.GENERIC_ERROR_REPLY
        assert result.actions[-1]["kind"] == "send_message"
        assert result.branch_kind == "business_query", "the turn keeps where it got to"
        row = _only_row(session_factory)
        assert row.status == "failed"
        assert row.stage == "looked_up"
        assert "timeout" in (row.error or "")

    def test_an_mcp_failure_with_the_lane_off_delegates_as_before(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        answered = self._wire(
            monkeypatch,
            fetch=self._error_fragment("MCP tool crm_master_products_list failed: timeout"),
        )
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert not answered
        assert result.delegate == "business_query"
        assert result.status == "delegated"
        assert result.stage == "looked_up"
        row = _only_row(session_factory)
        assert row.status == "delegated"
        assert (row.response or {}).get("delegate_error"), (
            "the operator's query needs the reason beside the delegated row"
        )


class TestTheRowKeepsTheFirstOutcome:
    """`_close_turn` is write-once for a TERMINAL status, and first-write-wins.

    The sequence is real, not hypothetical: a failure inside the tail closes the row
    itself (`failed` at `remembered`, where it actually stopped) and re-raises, and the
    lane handler that called it catches the same exception and closes again (`failed` at
    `replied`). The second write names the CALLER's stage, so letting it win loses the
    only fact an operator needs. `delegated` is deliberately not terminal: it is the
    handover `close_turn_for_tail` writes and `complete_turn` supersedes with `done`.
    """

    def test_a_second_terminal_close_is_refused(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        stub_parser()
        stub_access()
        monkeypatch.setattr(
            parser_mod,
            "resolve_config",
            lambda db, *, current_date: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        row = _only_row(session_factory)
        assert (row.status, row.stage) == ("failed", "received")
        first_error, first_finished = row.error, row.finished_at

        db = session_factory()
        engine_mod._close_turn(
            db,
            result.turn_id,
            status="failed",
            stage="replied",
            branch_kind="business_query",
            error="the caller's own message",
            records=[],
            response={"reply": {"text": "later"}},
        )

        row = _only_row(session_factory)
        assert (row.status, row.stage) == ("failed", "received"), (
            "the first close records where the turn actually stopped; a later one names "
            "the stage of whoever caught the exception"
        )
        assert row.error == first_error
        assert row.finished_at == first_finished
        assert row.response is None

    def test_the_delegated_handover_is_still_superseded_by_the_tail(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        """The two-phase close every completed lane makes must keep working: `delegated`
        at `routed` first, `done` at `remembered` when the tail has folded the result in.
        """
        from app.services.chatbot.lanes import casual

        from tests.chatbot.test_s4_casual_lane import _install_stub_lane

        stub_parser(
            _parser_output(
                message_type="casual",
                domain_hint=None,
                intent_hint=None,
                user_goal="hi there",
                entities=[],
            )
        )
        stub_access()
        monkeypatch.setattr(
            engine_mod, "_enabled_lanes", lambda db, row=None: frozenset({"low_signal"})
        )
        _install_stub_lane(monkeypatch, casual, response_json='{"response": "Hi there!"}')

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.status == "done", result.error
        row = _only_row(session_factory)
        assert (row.status, row.stage) == ("done", "remembered"), (
            "the tail's own close must still supersede the delegated handover"
        )
