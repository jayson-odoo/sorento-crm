"""AC-007: every trace record is plain language, for every `branch_kind`.

`test_engine.py::TestHappyPath.test_the_trace_is_sentences_not_json` proves this for the
one branch kind its happy path exercises (`business_query`). This file drives `run_turn`
through the other 12 - the AC's own wording is "any stage of a turn", not "the common
one" - and adds the "is a sentence" property `test_engine.py` did not check: a summary or
`why` a machine assembled by string-joining without a separator is not a sentence even
though it contains no `{`/`[`, so every record here must also contain a space.

Nothing here reaches an LLM, n8n, respond.io or the MCP server - same seam as
`test_engine.py`.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import BRANCH_KINDS
from tests.chatbot.test_engine import (  # noqa: F401 - re-exported fixtures used by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)


def _assert_trace_is_legible(trace: list[dict[str, Any]]) -> None:
    assert trace, "no trace records were written at all"
    for record in trace:
        assert "raw" in record, record
        summary, why = record["summary"], record["why"]
        assert summary and why, record
        assert "{" not in summary and "[" not in summary, summary
        assert "{" not in why and "[" not in why, why
        # A sentence, not a bare token or a string-joined-without-a-separator blob.
        assert " " in summary, f"not a sentence: {summary!r}"
        assert " " in why, f"not a sentence: {why!r}"


def _run(session_factory, envelope) -> Any:
    result = engine_mod.run_turn(envelope, session_factory=session_factory)
    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
    return result, row.trace


def _set_session_vars(session_factory, variables: dict[str, Any]) -> None:
    db = session_factory()
    db.execute(
        text(
            "UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) "
            "WHERE respond_io_id = :c"
        ),
        {"c": CONTACT_ID, "sv": json.dumps({"variables": variables})},
    )
    db.commit()


class TestTraceLegibilityAcrossBranchKinds:
    """One test per `contracts.BRANCH_KINDS` entry, each driving a real `run_turn` call."""

    def test_access_denied(self, session_factory, seeded, stub_parser, stub_access):
        stub_parser(_parser_output())
        stub_access(allowed=False, decision="deny_no_access")
        result, trace = _run(session_factory, _envelope())
        assert result.branch_kind == "access_denied"
        _assert_trace_is_legible(trace)

    def test_escalate_offer(self, session_factory, seeded, stub_parser, stub_access):
        """Via `is_explicit_correction`: correction=True on a non-casual, non-business
        message_type - simpler to construct than the CS-order-enquiry-pick arm. No
        entities/domain_hint, or `output_exchange`'s own normalisation re-derives
        `message_type` back to `business_query` before `route.decide` ever sees it."""
        stub_parser(
            _parser_output(
                message_type="clarification",
                domain_hint=None,
                intent_hint=None,
                entities=[],
                correction=True,
            )
        )
        stub_access()
        result, trace = _run(session_factory, _envelope())
        assert result.branch_kind == "escalate_offer"
        _assert_trace_is_legible(trace)

    def test_out_of_scope(self, session_factory, seeded, stub_parser, stub_access):
        stub_parser(_parser_output(message_type="request_for_help", domain_hint="order"))
        stub_access()
        result, trace = _run(session_factory, _envelope())
        assert result.branch_kind == "out_of_scope"
        _assert_trace_is_legible(trace)

    def test_ideate(self, session_factory, seeded, stub_parser, stub_access):
        stub_parser(_parser_output(domain_hint="ideate", intent_hint="submit_idea"))
        stub_access()
        result, trace = _run(session_factory, _envelope())
        assert result.branch_kind == "ideate"
        _assert_trace_is_legible(trace)

    def test_offer_hold(self, session_factory, seeded, stub_parser, stub_access):
        _set_session_vars(
            session_factory,
            {
                "selection_context": "member_offer",
                "routing_roster_plan": [{"id": "a"}, {"id": "b"}],
            },
        )
        stub_parser(
            _parser_output(
                message_type="clarification",
                member_pick_context=True,
                escalation={
                    "is_escalation_confirmation": False,
                    "escalation_declined": False,
                    "offer_hold": True,
                },
            )
        )
        stub_access()
        result, trace = _run(session_factory, _envelope())
        assert result.branch_kind == "offer_hold"
        _assert_trace_is_legible(trace)

    def test_escalation_declined(self, session_factory, seeded, stub_parser, stub_access):
        stub_parser(
            _parser_output(
                escalation={"is_escalation_confirmation": False, "escalation_declined": True}
            )
        )
        stub_access()
        result, trace = _run(session_factory, _envelope())
        assert result.branch_kind == "escalation_declined"
        _assert_trace_is_legible(trace)

    def test_check_promotion(self, session_factory, seeded, stub_parser, stub_access):
        stub_parser(_parser_output(intent_hint="check_promotion", domain_hint="promotion"))
        stub_access()
        result, trace = _run(session_factory, _envelope())
        assert result.branch_kind == "check_promotion"
        _assert_trace_is_legible(trace)

    def test_low_signal(self, session_factory, seeded, stub_parser, stub_access):
        stub_parser(_parser_output(message_type="casual", domain_hint=None, intent_hint=None))
        stub_access()
        result, trace = _run(session_factory, _envelope())
        assert result.branch_kind == "low_signal"
        _assert_trace_is_legible(trace)

    def test_clarify_menu(self, session_factory, seeded, stub_parser, stub_access):
        """Same normalisation caveat as `test_escalate_offer` above."""
        stub_parser(
            _parser_output(
                message_type="clarification",
                domain_hint=None,
                intent_hint=None,
                entities=[],
                correction=False,
            )
        )
        stub_access()
        result, trace = _run(session_factory, _envelope())
        assert result.branch_kind == "clarify_menu"
        _assert_trace_is_legible(trace)

    def test_not_supported(self, session_factory, seeded, stub_parser, stub_access):
        stub_parser(_parser_output(domain_hint="goods_receive", intent_hint="check_goods_receive"))
        stub_access()
        result, trace = _run(session_factory, _envelope())
        assert result.branch_kind == "not_supported"
        _assert_trace_is_legible(trace)

    def test_stock_denied(self, session_factory, seeded, system_settings_row, stub_parser, stub_access):
        from app.models.user import SystemSetting

        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        setting.chatbot_stock_denial_enabled = True
        db.commit()

        stub_parser(_parser_output(intent_hint="check_stock", domain_hint="inventory", demand_qty=5))
        stub_access()
        envelope = _envelope()
        envelope.contact["custom_fields"] = [{"name": "is_allowed_stock", "value": "false"}]
        result, trace = _run(session_factory, envelope)
        assert result.branch_kind == "stock_denied"
        _assert_trace_is_legible(trace)

    def test_demand_qty(self, session_factory, seeded, system_settings_row, stub_parser, stub_access):
        from app.models.user import SystemSetting

        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        setting.chatbot_stock_denial_enabled = True
        db.commit()

        stub_parser(
            _parser_output(intent_hint="check_stock", domain_hint="inventory", demand_qty=None)
        )
        stub_access()
        envelope = _envelope()
        envelope.contact["custom_fields"] = [{"name": "is_allowed_stock", "value": "false"}]
        result, trace = _run(session_factory, envelope)
        assert result.branch_kind == "demand_qty"
        _assert_trace_is_legible(trace)

    def test_business_query(self, session_factory, seeded, stub_parser, stub_access):
        stub_parser(_parser_output())
        stub_access()
        result, trace = _run(session_factory, _envelope())
        assert result.branch_kind == "business_query"
        _assert_trace_is_legible(trace)

    def test_every_declared_branch_kind_has_a_test_above(self) -> None:
        """A new BRANCH_KINDS entry must add a scenario here, not silently go untested."""
        tested = {
            "access_denied",
            "escalate_offer",
            "out_of_scope",
            "ideate",
            "offer_hold",
            "escalation_declined",
            "check_promotion",
            "low_signal",
            "clarify_menu",
            "not_supported",
            "stock_denied",
            "demand_qty",
            "business_query",
        }
        assert tested == set(BRANCH_KINDS)
