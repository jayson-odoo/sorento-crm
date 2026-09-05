"""`run_turn`: the head end to end, on Postgres, with the LLM stubbed at the seam.

Covers AC-101 (the response shape and the five stages), AC-105 (a failed parse is a failed
`understood` stage with no default routing), AC-106 (the R3 dual read), AC-107 (audio that
media intake did not patch), AC-108 (the human-intervened action), AC-007 (the trace),
D14 (dry run writes nothing outside `chatbot.turns`), D15 (a duplicate message runs once)
and the plan's capacity rule (no DB session is held across the parser call).

Nothing here reaches an LLM, n8n, respond.io or the MCP server.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import TURN_STAGES, Envelope
from app.services.chatbot.head import parser as parser_mod

CONTACT_ID = "ZZT-contact-900000009"


def _parser_output(**overrides: Any) -> dict[str, Any]:
    """A well-formed parser emission: every declared key present, as the schema demands."""
    base = {
        "message_type": "business_query",
        "intent_hint": "check_product",
        "domain_hint": "master_products",
        "scope_intent": "specific",
        "is_affirmative": None,
        "user_goal": "checking a product",
        "access_levels": [],
        "broaden_axis": None,
        "date_mode": None,
        "date_filter_start": None,
        "date_filter_end": None,
        "match_mode": "and",
        "demand_qty": None,
        "entities": [
            {
                "raw": "SRTWC8517",
                "hint": "product",
                "canonical_code": None,
                "current_message": True,
                "confident": True,
            }
        ],
        "entity_op": "replace_combine",
        "scope_exclusive": False,
        "requested_attributes": [],
        "contains_flyer": False,
        "reference_positions": [],
        "reference_target": None,
        "person_mention": None,
        "is_active": None,
        "order_status": None,
        "correction": False,
        "routing": {"suggested_team": None, "suggested_agent": None, "team_source": None},
        "escalation": {"is_escalation_confirmation": False, "company_pick": None},
    }
    base.update(overrides)
    return base


def _envelope(**overrides: Any) -> Envelope:
    payload: dict[str, Any] = {
        "contact": {
            "id": CONTACT_ID,
            "firstName": "ZZT",
            "custom_fields": [{"name": "is_human_intervened", "value": "false"}],
        },
        "message": {
            "event_type": "message.received",
            "contact": {"id": CONTACT_ID},
            "message": {
                "messageId": "ZZT-msg-1",
                "contactId": CONTACT_ID,
                "channelId": "whatsapp",
                "traffic": "incoming",
                "message": {"type": "text", "text": "price for SRTWC8517"},
            },
        },
    }
    payload.update(overrides)
    return Envelope(**payload)


@pytest.fixture()
def seeded(session_factory):
    """A respond contact with empty session vars, plus the access agent the turn needs."""
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": CONTACT_ID, "phone": "+60000000009", "sv": json.dumps({"variables": {}})},
    )
    db.commit()
    return db


@pytest.fixture()
def stub_parser(monkeypatch):
    """Stub the provider call, the way `test_ideation_turn` stubs the ideate extractor."""

    def _install(output: dict[str, Any] | None = None, *, error: Exception | None = None, on_call=None):
        def fake_resolve_config(db, *, current_date):
            return parser_mod.ParserConfig(
                system_prompt="stub",
                prompt_version=1,
                provider="openai",
                model="gpt-test",
                api_key="sk-test",
            )

        def fake_parse(config, user_block):
            if on_call is not None:
                on_call(user_block)
            if error is not None:
                raise error
            return output if output is not None else _parser_output()

        monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
        monkeypatch.setattr(parser_mod, "parse", fake_parse)

    return _install


@pytest.fixture()
def stub_access(monkeypatch):
    def _install(allowed: bool = True, decision: str = "allow"):
        monkeypatch.setattr(
            engine_mod,
            "check_access",
            lambda db, *, agent_code, contact_id, space_id: {
                "allowed": allowed,
                "decision": decision,
                "agent_name": "General Enquiries",
                "attributes": None,
                "all_attributes_allowed": None,
            },
        )
        monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")

    return _install


def _turn_row(session_factory, turn_id: str) -> ChatbotTurn:
    return session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()


class TestHappyPath:
    def test_returns_ctx_item_branch_and_delegate(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        stub_parser()
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "business_query"
        # S1 still hands the lane to n8n; S3 onwards shrinks this to null.
        assert result.delegate == "business_query"
        assert set(result.ctx) == {"contact", "text", "session", "parse", "access", "media"}
        # AC-101: `item` is what route-turn emits - the access response plus branch_kind.
        assert result.item["branch_kind"] == "business_query"
        assert result.item["allowed"] is True
        assert result.item["decision"] == "allow"

    def test_the_turn_row_is_recorded_as_delegated(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        stub_parser()
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        row = _turn_row(session_factory, result.turn_id)
        assert row.status == "delegated", row.error
        assert row.stage == "routed"
        assert row.branch_kind == "business_query"
        assert row.message_id == "ZZT-msg-1"
        assert row.ingress == "webhook"
        assert row.error is None

    def test_the_trace_is_sentences_not_json(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        """AC-007: `summary` and `why` are plain language; `raw` holds the payload."""
        stub_parser()
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        trace = _turn_row(session_factory, result.turn_id).trace
        assert [r["stage"] for r in trace] == ["received", "understood", "access", "routed"]
        for record in trace:
            assert record["summary"] and record["why"]
            assert "{" not in record["summary"], record["summary"]
            assert "{" not in record["why"], record["why"]
            assert record["ms"] >= 0
            assert "raw" in record

    def test_every_stage_the_head_owns_is_a_declared_turn_stage(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        stub_parser()
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        trace = _turn_row(session_factory, result.turn_id).trace
        assert all(r["stage"] in TURN_STAGES for r in trace)
        # The four the HEAD owns. `looked_up` onwards arrive with the lanes and the tail;
        # a stage that did not run is omitted, never recorded empty (AC-252).
        assert [r["stage"] for r in trace] == list(TURN_STAGES[:4])


class TestParserFailure:
    def test_a_failed_parse_is_a_failed_understood_stage_with_no_routing(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        """AC-105 / R5 / H44: no soft default, no default routing."""
        stub_parser(error=parser_mod.ParserError("provider timeout"))
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind is None
        assert result.delegate is None
        assert result.reply["text"] == parser_mod.PARSER_ERROR_REPLY

        row = _turn_row(session_factory, result.turn_id)
        assert row.status == "failed"
        assert row.stage == "understood"
        assert "provider timeout" in row.error
        assert row.trace[-1]["stage"] == "understood"
        assert row.trace[-1]["status"] == "failed"

    def test_the_caller_is_handed_the_error_reply_as_an_action(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        stub_parser(error=parser_mod.ParserError("boom"))
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert [a["kind"] for a in result.actions] == ["send_message"]
        assert result.actions[0]["text"] == parser_mod.PARSER_ERROR_REPLY


class TestAudioDeadEnd:
    def test_an_unpatched_voice_note_fails_at_intake(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        """AC-107 / H5: n8n's audio branch had no successor and the turn vanished."""
        stub_parser()
        stub_access()
        envelope = _envelope()
        envelope.message["message"]["message"] = {"type": "audio", "attachment": {"type": "audio"}}

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert result.branch_kind is None
        assert result.reply["text"] == parser_mod.PARSER_ERROR_REPLY
        row = _turn_row(session_factory, result.turn_id)
        assert row.status == "failed"
        assert row.stage == "intake"
        assert "transcribe" in row.error

    def test_it_never_reaches_the_parser(self, session_factory, seeded, stub_parser, stub_access):
        calls: list[str] = []
        stub_parser(on_call=calls.append)
        stub_access()
        envelope = _envelope()
        envelope.message["message"]["message"] = {"type": "audio", "attachment": {"type": "audio"}}
        engine_mod.run_turn(envelope, session_factory=session_factory)
        assert calls == []


class TestHumanIntervened:
    def test_the_flag_becomes_an_action_and_the_turn_continues(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        """AC-108: today's `set-human-intervened` path, as an action the caller executes."""
        stub_parser()
        stub_access()
        envelope = _envelope()
        envelope.contact["custom_fields"] = [{"name": "is_human_intervened", "value": "true"}]

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert result.branch_kind == "business_query"  # the turn CONTINUES
        assert result.actions[0] == {
            "kind": "update_contact_fields",
            "fields": {"is_human_intervened": False},
            "dry_run": False,
        }

    def test_no_action_when_the_flag_is_not_set(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        stub_parser()
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert result.actions == []


class TestAccessDenied:
    def test_a_refused_contact_routes_to_access_denied_with_the_tag_only_item(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        stub_parser()
        stub_access(allowed=False, decision="deny_no_access")
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert result.branch_kind == "access_denied"
        # `access_denied` is NOT a tag-only arm: it keeps the access response.
        assert result.item["decision"] == "deny_no_access"


class TestDryRun:
    def test_a_test_envelope_writes_nothing_outside_chatbot_turns(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        """D14: `is_test` / `test_run_id` make the turn side-effect free."""
        stub_parser()
        stub_access()
        db = session_factory()
        before = db.execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": CONTACT_ID},
        ).scalar()

        envelope = _envelope(test_run_id="ZZT-run-1")
        assert envelope.dry_run is True
        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        after = db.execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": CONTACT_ID},
        ).scalar()
        assert after == before
        assert _turn_row(session_factory, result.turn_id).is_test is True
        # S1's head writes no session state, so there is nothing to patch yet.
        assert result.session_patch is None

    def test_every_action_carries_dry_run_true(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        stub_parser()
        stub_access()
        envelope = _envelope(is_test=True)
        envelope.contact["custom_fields"] = [{"name": "is_human_intervened", "value": "true"}]
        result = engine_mod.run_turn(envelope, session_factory=session_factory)
        assert result.actions
        assert all(a["dry_run"] is True for a in result.actions)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"is_test": True},
            {"test_run_id": "ZZT-run"},
            {"mode": "uac"},
        ],
    )
    def test_all_three_test_markers_mean_dry_run(self, overrides):
        assert _envelope(**overrides).dry_run is True

    def test_a_live_envelope_is_not_a_dry_run(self):
        assert _envelope(mode="live").dry_run is False
        assert _envelope().dry_run is False


class TestIdempotency:
    def test_the_same_message_twice_runs_one_turn(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        """D15: the webhook producer and the failover poller are two injectors, one message."""
        calls: list[str] = []
        stub_parser(on_call=calls.append)
        stub_access()

        first = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        second = engine_mod.run_turn(
            _envelope(ingress="poller"), session_factory=session_factory
        )

        assert second.duplicate is True
        assert second.turn_id == first.turn_id
        assert second.branch_kind == first.branch_kind
        assert len(calls) == 1  # no second LLM call

        rows = (
            session_factory()
            .query(ChatbotTurn)
            .filter(ChatbotTurn.contact_respond_id == CONTACT_ID)
            .all()
        )
        assert len(rows) == 1

    def test_a_different_message_runs_normally(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        stub_parser()
        stub_access()
        engine_mod.run_turn(_envelope(), session_factory=session_factory)
        other = _envelope()
        other.message["message"]["messageId"] = "ZZT-msg-2"
        result = engine_mod.run_turn(other, session_factory=session_factory)
        assert result.duplicate is False
        assert result.branch_kind == "business_query"


class TestSessionDiscipline:
    def test_no_db_session_is_open_during_the_parser_call(
        self, counting_session_factory, session_factory, seeded, stub_parser, stub_access
    ):
        """The plan's capacity rule. The 96/100-connection incident is the evidence."""
        observed: list[int] = []
        stub_parser(on_call=lambda _block: observed.append(counting_session_factory.state["open"]))
        stub_access()

        engine_mod.run_turn(_envelope(), session_factory=counting_session_factory)

        assert observed == [0], (
            "a DB session was held across the parser call - the engine must close it "
            "before provider I/O and reopen afterwards"
        )


class TestPendingMarkerRead:
    def test_the_parser_is_told_what_the_bot_is_waiting_for(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        """R3: the ONE prompt-input change S1 makes (D16 slimming is S1b)."""
        db = session_factory()
        db.execute(
            text(
                "UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) "
                "WHERE respond_io_id = :c"
            ),
            {
                "c": CONTACT_ID,
                "sv": json.dumps({"variables": {"pending": {"kind": "escalation_offer"}}}),
            },
        )
        db.commit()

        blocks: list[str] = []
        stub_parser(on_call=blocks.append)
        stub_access()
        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert "Pending: the assistant is waiting for a escalation_offer reply." in blocks[0]

    def test_nothing_is_added_when_nothing_is_pending(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        blocks: list[str] = []
        stub_parser(on_call=blocks.append)
        stub_access()
        engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert "Pending:" not in blocks[0]


class TestLatestUserMessage:
    def test_it_is_the_two_line_shape_the_ported_blocks_split_back_apart(self):
        envelope = _envelope()
        assert engine_mod.build_latest_user_message(envelope) == "price for SRTWC8517\n\n"

    def test_a_quoted_reply_appends_the_reply_to_line(self):
        envelope = _envelope()
        envelope.message["message"]["replyTo"] = {
            "id": "ZZT-quoted",
            "message": {"text": "1. SRTWC8517"},
        }
        assert (
            engine_mod.build_latest_user_message(envelope)
            == "price for SRTWC8517\nreply to: 1. SRTWC8517\n"
        )

    def test_an_image_description_stands_in_for_missing_text(self):
        envelope = _envelope()
        envelope.message["message"]["message"] = {
            "type": "image",
            "attachment": {"type": "image", "description": "a photo of a basin"},
        }
        assert engine_mod.build_latest_user_message(envelope) == "a photo of a basin\n\n"


class TestStockDenialGateEndToEnd:
    """R1 / AC-306, wired end to end through `run_turn` (not just `route.decide`).

    `test_route_unit.py` already proves the pure predicate; this proves
    `engine._stock_denial_enabled` actually reads `system_settings.chatbot_stock_denial_enabled`
    off the row the fixture flips and hands it to `decide` unchanged, on the real Postgres
    fixture used everywhere else in this suite.
    """

    @staticmethod
    def _stock_envelope(*, message_id: str) -> Envelope:
        envelope = _envelope()
        envelope.message["message"]["messageId"] = message_id
        # A contact without stock access - not one missing the field outright, which is
        # the OTHER covered property (test_route_unit's "still throws exactly as live does").
        envelope.contact["custom_fields"] = [
            {"name": "is_human_intervened", "value": "false"},
            {"name": "is_allowed_stock", "value": "false"},
        ]
        return envelope

    def test_off_by_default_a_stock_check_still_answers_business_query(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access
    ):
        assert system_settings_row.chatbot_stock_denial_enabled in (False, None)
        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                demand_qty=5,
            )
        )
        stub_access()

        result = engine_mod.run_turn(
            self._stock_envelope(message_id="ZZT-msg-stock-off"),
            session_factory=session_factory,
        )
        assert result.branch_kind == "business_query"

    def test_flipped_on_the_same_contact_is_denied(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access
    ):
        from app.models.user import SystemSetting

        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        setting.chatbot_stock_denial_enabled = True
        db.commit()

        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                demand_qty=5,
            )
        )
        stub_access()

        result = engine_mod.run_turn(
            self._stock_envelope(message_id="ZZT-msg-stock-on"),
            session_factory=session_factory,
        )
        assert result.branch_kind == "stock_denied"
