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
