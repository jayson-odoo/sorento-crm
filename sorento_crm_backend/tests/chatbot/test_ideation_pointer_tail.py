"""RED tests for the tail dropping the ideate lane's own draft pointer.

Contract: `documentation/plans/chatbot/PLAN-chatbot-ideation-pointer-tail-25sep.md`,
`chatbot-ideation-pointer-tail-25sep-acceptance-criteria.md` (AC-1 to AC-4).

Measured 25 Sep 2026 (owner console walk, PR #1222 head f64373c95): every `ideate` turn
minted a NEW draft because `engine.run_tail`'s five-key payload wrote
`"ideation": before.get("ideation")` - the pointer the turn STARTED with - and never read
back what `lanes/ideate.py::build_reply` put on the tail item. A dry run therefore handed
the caller a stale `session_patch` and a live turn had the tail's own
`overwrite_for_contact` wipe what `ideation_turn_service.handle_turn` had just written.

Modelled on `tests/chatbot/test_s3_canned_and_ideate.py::TestIdeateBranchCallsMcpTool` for
the fixtures and the way a turn is run; on `tests/chatbot/test_ideation_draft_keeps_lane.py`
for stubbing `lanes.ideate.call_ideation_tool`; and on
`tests/chatbot/test_harness_injections.py::TestHarnessInjectionsG8` for feeding a prior
turn's `session_patch` forward as `previous_conversation_state`.

Nothing here reaches an LLM, n8n, respond.io or a live MCP server.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.services.chatbot import engine as engine_mod

from tests.chatbot.test_engine import (  # noqa: F401 - fixtures reused by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)
from tests.chatbot.test_s3_canned_and_ideate import (
    _seed_completed_lanes,
    _seed_session_variables,
)

# The pointer the intake tool answers, per the brief: a draft mid-collection, with the
# `is_test` flag threaded through matching whichever turn is calling it.
POINTER: dict[str, Any] = {
    "draft_id": "d-ptr-1",
    "status": "collecting",
    "missing": ["proposed_solution", "impact"],
    "next_field": "proposed_solution",
    "captured": {"problem": "x"},
    "transcript": [],
    "updated_at": "2026-09-25T00:00:00+00:00",
}


def _pointer_for(is_test: bool) -> dict[str, Any]:
    return {**POINTER, "is_test": is_test}


def _stub_ideation_tool(monkeypatch, *, is_test: bool, status: str = "collecting"):
    """Stub `call_ideation_tool` to answer the pointer above, recording every call."""
    from app.services.chatbot.lanes import ideate as ideate_mod

    captured: list[dict[str, Any]] = []

    def _record(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {
            "status": status,
            "reply_text": "Got it - what department is this for?",
            "link": None,
            "session_vars": {"ideation": _pointer_for(is_test)},
        }

    monkeypatch.setattr(ideate_mod, "call_ideation_tool", _record)
    return captured


def _ideate_parser_output(**overrides: Any) -> dict[str, Any]:
    base = _parser_output(
        message_type="business_query",
        intent_hint="submit_idea",
        domain_hint="ideate",
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    base.update(overrides)
    return base


def _session_vars_raw(session_factory) -> Any:
    return session_factory().execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
        {"c": str(CONTACT_ID)},
    ).scalar()


class TestDryRunKeepsThePointer:
    def test_ac1_dry_run_session_patch_carries_the_pointer(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        _seed_completed_lanes(session_factory, system_settings_row)
        _stub_ideation_tool(monkeypatch, is_test=True)
        stub_parser(_ideate_parser_output())
        stub_access()

        result = engine_mod.run_turn(_envelope(is_test=True), session_factory=session_factory)

        assert result.branch_kind == "ideate"
        assert result.session_patch is not None
        assert result.session_patch["ideation"] == _pointer_for(True)


class TestLiveTurnKeepsThePointer:
    def test_ac2_live_turn_writes_the_pointer_not_the_turn_start_value(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        _seed_completed_lanes(session_factory, system_settings_row)
        _stub_ideation_tool(monkeypatch, is_test=False)
        stub_parser(_ideate_parser_output())
        stub_access()
        # The turn starts with NO pointer - `overwrite_for_contact` must not merely
        # preserve this; it must write the tool's ANSWER, which is a different value.
        before = _session_vars_raw(session_factory)
        assert (before or {}).get("ideation") in (None, {})

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "ideate"
        after = _session_vars_raw(session_factory)
        assert after["ideation"] == _pointer_for(False)


class TestOtherLanesUntouched:
    def test_ac3_a_non_ideate_turn_leaves_an_existing_pointer_unchanged(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access
    ):
        """`escalation_declined` - the simplest canned lane, no seam of its own - must not
        let the fallback-vs-item-key branch touch a pointer some earlier ideate turn left
        on the contact."""
        _seed_completed_lanes(session_factory, system_settings_row)
        existing_pointer = _pointer_for(False)
        _seed_session_variables(session_factory, {"ideation": existing_pointer})
        stub_parser(
            _parser_output(
                message_type="casual",
                domain_hint=None,
                correction=False,
                escalation={"is_escalation_confirmation": False, "escalation_declined": True},
            )
        )
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "escalation_declined"
        after = _session_vars_raw(session_factory)
        assert after["ideation"] == existing_pointer


class TestTheDraftContinues:
    def test_ac4_a_second_dry_run_sends_the_first_turns_draft_id(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        _seed_completed_lanes(session_factory, system_settings_row)
        _stub_ideation_tool(monkeypatch, is_test=True)
        stub_parser(_ideate_parser_output())
        stub_access()

        turn_1 = engine_mod.run_turn(_envelope(is_test=True), session_factory=session_factory)
        assert turn_1.session_patch["ideation"]["draft_id"] == "d-ptr-1"

        captured = _stub_ideation_tool(monkeypatch, is_test=True)
        stub_parser(_ideate_parser_output())
        envelope_2 = _envelope(is_test=True, previous_conversation_state=turn_1.session_patch)
        envelope_2.message["message"]["messageId"] = "ZZT-msg-2"
        turn_2 = engine_mod.run_turn(envelope_2, session_factory=session_factory)

        assert turn_2.branch_kind == "ideate"
        assert len(captured) == 1
        assert captured[0]["session_vars"]["ideation"]["draft_id"] == "d-ptr-1"


class TestTerminalStatusClearsThePointer:
    def test_a_completed_draft_clears_the_stored_pointer(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        """The intake tool answers with no `ideation` key at all (a completed / cancelled
        draft, per `lanes/ideate.py::build_reply`'s own `None` default) - the contact's
        stored pointer must clear, not keep the value the turn started with."""
        from app.services.chatbot.lanes import ideate as ideate_mod

        _seed_completed_lanes(session_factory, system_settings_row)
        _seed_session_variables(session_factory, {"ideation": _pointer_for(False)})

        def _complete(**kwargs: Any) -> dict[str, Any]:
            return {
                "status": "complete",
                "reply_text": "Idea IDEA-42 recorded. Thank you!",
                "link": None,
                "session_vars": {},
            }

        monkeypatch.setattr(ideate_mod, "call_ideation_tool", _complete)
        stub_parser(_ideate_parser_output())
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "ideate"
        after = _session_vars_raw(session_factory)
        assert after["ideation"] is None
