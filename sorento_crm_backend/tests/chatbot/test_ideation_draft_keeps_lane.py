"""Issue #1178: an open ideation draft keeps short and question-shaped turns in the ideate
lane (`documentation/plans/chatbot/PLAN-chatbot-ideation-draft-keeps-lane.md`, AC-1 to AC-11).

Evidence: `documentation/plans/ideation/REVIEW-ideation-flow-ux-24sep.md` findings 2 and 3.
"what do you mean impact?" typed mid-draft answered with the eight-topic domain menu
(`clarify_menu`); a bare "confirm", the word the intake's own template asks for, answered
"Hi! How can I help today?" (`low_signal`).

Two seams, both after the parse and both reading structured state only:

* the pure one, `apply()` + `route()` over a `State` carrying the five-key `ideation`
  pointer - the verdict is built with `_turn_helpers.verdict`, never a message;
* the engine one, `engine.run_turn` on Postgres with the draft seeded on the contact's
  session and `lanes.ideate.call_ideation_tool` stubbed, so the assertion is that the
  customer's words reached the intake tool and nothing else answered them.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.route import route
from app.services.chatbot.turn.state import Focus, State
from tests.chatbot._turn_helpers import build_policy, entity, verdict
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

OPEN_DRAFT: dict[str, Any] = {
    "draft_id": "ZZT-draft-1",
    "status": "collecting",
    "missing": ["proposed_solution", "impact", "department"],
}

RULE = "open_idea_draft_keeps_lane"


def _state(ideation: Any = OPEN_DRAFT, domains: tuple[str, ...] = ("ideate",)) -> State:
    return State(focus=Focus(domains=list(domains)), ideation=ideation)


def _branch(state: State, v: dict[str, Any]) -> tuple[str, Any]:
    _, plan = apply(state, v, build_policy())
    return route(plan), plan


def _question_verdict(**overrides: Any) -> dict[str, Any]:
    """"what do you mean impact?" - a question about the intake's own question."""
    return verdict(message_type="clarification", user_goal="asking what impact means", **overrides)


def _confirm_verdict(**overrides: Any) -> dict[str, Any]:
    """"confirm" - the parser's bare affirmative, no domain of its own."""
    return verdict(message_type="confirmation", is_affirmative=True, **overrides)


class TestOpenDraftKeepsTheLane:
    def test_a_question_about_the_field_stays_in_ideate(self) -> None:
        """AC-1."""
        branch, _ = _branch(_state(), _question_verdict())
        assert branch == "ideate"

    def test_the_parsers_own_ideate_domain_is_honoured_on_a_question(self) -> None:
        """AC-2: a verdict that followed the prompt's IDEATION CONTINUATION rule still
        landed on the domain menu, because `_lane` read the message type before the
        domain."""
        branch, plan = _branch(
            _state(), _question_verdict(domain_hint="ideate", intent_hint="submit_idea")
        )
        assert branch == "ideate", (plan.trace.lane, plan.domains)

    def test_a_bare_confirm_stays_in_ideate(self) -> None:
        """AC-3."""
        branch, plan = _branch(_state(), _confirm_verdict())
        assert branch == "ideate", (plan.trace.lane, plan.trace.rules_fired)

    def test_a_hesitation_stays_in_ideate(self) -> None:
        """AC-4: "dunno lah, can skip this one?"."""
        branch, _ = _branch(_state(), verdict(message_type="casual"))
        assert branch == "ideate"

    def test_the_rule_is_named_on_the_trace(self) -> None:
        """AC-5."""
        _, plan = _branch(_state(), _question_verdict())
        assert RULE in plan.trace.rules_fired
        assert plan.trace.lane is None
        assert plan.domains == ["ideate"]


class TestNoDraftNothingChanges:
    """AC-6: the rule reads the draft pointer and nothing else, so without one every
    verdict routes exactly as it did before."""

    @pytest.mark.parametrize("ideation", [None, {}, {"status": "collecting"}])
    def test_a_question_without_a_draft_is_the_domain_menu(self, ideation: Any) -> None:
        branch, plan = _branch(_state(ideation=ideation), _question_verdict())
        assert branch == "clarify_menu"
        assert RULE not in plan.trace.rules_fired

    @pytest.mark.parametrize("ideation", [None, {}, {"status": "collecting"}])
    def test_a_confirm_without_a_draft_is_low_signal(self, ideation: Any) -> None:
        branch, plan = _branch(_state(ideation=ideation), _confirm_verdict())
        assert branch == "low_signal"
        assert RULE not in plan.trace.rules_fired


class TestTheDraftYieldsToWhatTheMessageNames:
    def test_a_decisive_domain_switch_still_wins(self) -> None:
        """AC-7: the prompt's own rule - asking stock mid-idea switches domain normally."""
        branch, plan = _branch(
            _state(),
            verdict(
                domain_hint="inventory",
                intent_hint="check_stock",
                domain_in_message=True,
                entities=[entity("SRTWC286")],
            ),
        )
        assert branch == "business_query"
        assert plan.domains == ["inventory"]
        assert RULE not in plan.trace.rules_fired

    def test_an_escalation_still_wins(self) -> None:
        """AC-8."""
        branch, _ = _branch(_state(), verdict(message_type="escalation"))
        assert branch == "out_of_scope"

    def test_a_request_for_a_human_still_wins(self) -> None:
        """AC-8: "get me a human" mid-draft is still a handover, not an idea turn."""
        branch, _ = _branch(_state(), verdict(message_type="request_for_help"))
        assert branch == "out_of_scope"

    def test_a_standing_subject_in_another_domain_is_not_pulled_back(self) -> None:
        """AC-9: the customer asked stock mid-idea and the focus moved with them; the
        draft resumes by a fresh ideate turn (the prompt's own detour wording)."""
        branch, plan = _branch(_state(domains=("inventory",)), _confirm_verdict())
        assert branch == "low_signal"
        assert RULE not in plan.trace.rules_fired


# --------------------------------------------------------------------------- #
# The engine, with the draft seeded on the contact's own session (AC-10, AC-11).
# --------------------------------------------------------------------------- #

SEEDED_SESSION: dict[str, Any] = {
    "focus": {"domains": ["ideate"]},
    "ideation": dict(OPEN_DRAFT),
}

IDEATE_TOOL_RESULT: dict[str, Any] = {
    "status": "collecting",
    "reply_text": "Impact means what changes for the team once the idea is live.",
    "link": None,
    "session_vars": {"ideation": dict(OPEN_DRAFT)},
}


def _stub_ideation_tool(monkeypatch) -> list[dict[str, Any]]:
    from app.services.chatbot.lanes import ideate as ideate_mod

    captured: list[dict[str, Any]] = []

    def _record(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return dict(IDEATE_TOOL_RESULT)

    monkeypatch.setattr(ideate_mod, "call_ideation_tool", _record)
    return captured


def _run(session_factory, system_settings_row, stub_parser, stub_access, monkeypatch, *, text: str, parser: dict):
    _seed_completed_lanes(session_factory, system_settings_row)
    _seed_session_variables(session_factory, SEEDED_SESSION)
    captured = _stub_ideation_tool(monkeypatch)
    stub_parser(parser)
    stub_access()
    envelope = _envelope()
    envelope.message["message"]["message"]["text"] = text
    result = engine_mod.run_turn(envelope, session_factory=session_factory)
    return result, captured


class TestEngineWithAnOpenDraft:
    def test_a_question_about_the_field_reaches_the_ideation_tool(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ) -> None:
        """AC-10."""
        result, captured = _run(
            session_factory,
            system_settings_row,
            stub_parser,
            stub_access,
            monkeypatch,
            text="what do you mean impact?",
            parser=_parser_output(
                message_type="clarification",
                intent_hint=None,
                domain_hint=None,
                scope_intent=None,
                user_goal="asking what impact means",
                entities=[],
                entity_op=None,
            ),
        )
        assert result.branch_kind == "ideate", result.reply
        assert len(captured) == 1
        assert captured[0]["message_text"] == "what do you mean impact?"
        assert captured[0]["session_vars"] == {"ideation": OPEN_DRAFT}
        assert result.reply["text"] == IDEATE_TOOL_RESULT["reply_text"]

    def test_a_bare_confirm_reaches_the_ideation_tool(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ) -> None:
        """AC-11."""
        result, captured = _run(
            session_factory,
            system_settings_row,
            stub_parser,
            stub_access,
            monkeypatch,
            text="confirm",
            parser=_parser_output(
                message_type="confirmation",
                intent_hint=None,
                domain_hint=None,
                scope_intent=None,
                is_affirmative=True,
                user_goal="confirming",
                entities=[],
                entity_op=None,
            ),
        )
        assert result.branch_kind == "ideate", result.reply
        assert len(captured) == 1
        assert captured[0]["message_text"] == "confirm"
        assert captured[0]["session_vars"] == {"ideation": OPEN_DRAFT}
