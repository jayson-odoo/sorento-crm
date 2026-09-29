"""Issue #1178: an open ideation draft keeps short and question-shaped turns in the ideate
lane (`documentation/plans/chatbot/PLAN-chatbot-ideation-draft-keeps-lane.md`, AC-1 to
AC-11b).

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

Fix round 1 (reviewer pass at 5466562b on PR #1185) added AC-7b through AC-7e and AC-11b,
and superseded AC-4 - see `PLAN-chatbot-ideation-draft-keeps-lane.md`'s "Fix round 1"
section for the two behaviour changes (S1, S3).
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.pending import ask as pending_ask
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

#: AC-7b's roster case: an open `product_pick` roster, so `reference_positions: [1]`
#: is a real ANSWER (`decide()`'s ANSWER kind), not a stray position with nothing to
#: answer (that is AC-7d, no pending at all).
ROSTER_PENDING = pending_ask(
    "product_pick",
    [
        {
            "position": 1,
            "label": "SRTWC286-SH-200",
            "code": "SRTWC286-SH-200",
            "uuid": "u1",
            "uuids": ["u1"],
            "entity_type": "product",
            "payload": {},
        }
    ],
    asked_at_turn=1,
    expects="pick",
    payload={},
)


def _state(
    ideation: Any = OPEN_DRAFT, domains: tuple[str, ...] = ("ideate",), pending: Any = None
) -> State:
    return State(focus=Focus(domains=list(domains)), ideation=ideation, pending=pending)


def _branch(state: State, v: dict[str, Any]) -> tuple[str, Any]:
    _, plan = apply(state, v, build_policy())
    return route(plan), plan


def _question_verdict(**overrides: Any) -> dict[str, Any]:
    """"what do you mean impact?" - a question about the intake's own question."""
    base = {"message_type": "clarification", "user_goal": "asking what impact means"}
    base.update(overrides)
    return verdict(**base)


def _confirm_verdict(**overrides: Any) -> dict[str, Any]:
    """"confirm" - the parser's bare affirmative, no domain of its own."""
    base = {"message_type": "confirmation", "is_affirmative": True}
    base.update(overrides)
    return verdict(**base)


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


class TestIdleChatIsNotAbsorbedIntoTheDraft:
    """AC-4 (superseded, fix round 1, S1): "dunno lah, can skip this one?" is
    `message_type: casual`, and `_lane` sends `casual`, `unknown` AND `confirmation`
    turns to the very same "casual" lane - so keying the rule on the lane alone
    absorbed idle chat too. The open draft pointer has no expiry (the intake keeps it
    on `collecting`/`review` until `complete`/`duplicate`), so a contact who abandoned
    a draft and later said "hi" would have had it resurrected and re-served
    "Still need: ...". Narrowed to `_DRAFT_MESSAGE_TYPES`: a `casual` or `unknown` turn
    over an open draft now routes exactly as it would with no draft at all.
    """

    @pytest.mark.parametrize("message_type", ["casual", "unknown"])
    def test_idle_chat_types_are_not_absorbed(self, message_type: str) -> None:
        v = verdict(message_type=message_type)
        branch, plan = _branch(_state(), v)
        no_draft_branch, _ = _branch(_state(ideation=None), v)
        assert branch == no_draft_branch == "low_signal"
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

    @pytest.mark.parametrize(
        "verdict_factory", [_question_verdict, _confirm_verdict], ids=["clarification", "confirmation"]
    )
    @pytest.mark.parametrize(
        "overrides, pending",
        [
            pytest.param({"entities": [entity("SRTWC286")]}, None, id="current_message_entity"),
            pytest.param({"domain_in_message": True}, None, id="domain_in_message"),
            # Fix round 2 (B1-r2): an ask naming a domain (e.g. "inventory") also moves
            # `focus.domains` in `_focus_rules` (`elif asks: focus.domains = [...]`), so
            # the focus guard at `apply.py:1056` rejected the turn first and the asks
            # guard at `:1067-1071` was never reached - the round 1 case went green for
            # the wrong reason. An empty `domain` is filtered out of that list
            # (`if a.get("domain")`), so `focus.domains` stays `["ideate"]` and only the
            # asks guard stands between this verdict and `ideate`.
            pytest.param(
                {"asks": [{"domain": "", "intent": "check_stock"}]},
                None,
                id="asks_non_ideate",
            ),
            pytest.param({"requested_attributes": ["price"]}, None, id="requested_attributes"),
            pytest.param({"intent_hint": "check_stock"}, None, id="intent_hint_other_domain"),
            # `is_affirmative: true` explicitly (redundant for `_confirm_verdict`,
            # additive for `_question_verdict`) over an open pending: `decide()`'s
            # "affirmative" path (`turn/decide.py`) makes this an ANSWER without
            # touching `entities` or `reference_positions`, so it isolates the
            # `decision.answers` guard - a positional pick would also trip the S3
            # disqualifier guard below it, on the same verdict, for a different reason.
            pytest.param({"is_affirmative": True}, ROSTER_PENDING, id="answers_open_roster"),
        ],
    )
    def test_every_guard_one_at_a_time_matches_the_no_draft_baseline(
        self, overrides: dict[str, Any], pending: Any, verdict_factory
    ) -> None:
        """AC-7b (reviewer B1): each guard that lets the message name something of its
        own, tested in isolation, over both a question-shaped and a bare-confirm
        verdict. The assertion is the branch WITH the draft open against the branch
        for the IDENTICAL verdict (and pending) with no draft at all, rather than a
        hard-coded lane name - exactly what B1 asks for, regardless of which lane each
        guard's own verdict shape would otherwise reach.

        Kill-tested (B1's own method, N5 wording fix round 2): five of the six guards
        isolate on the `clarification` id - removing that guard alone turns exactly
        that one case red. The confirmation cases for `current_message_entity`,
        `requested_attributes` and `intent_hint_other_domain` are baseline-equality
        checks, not guard isolations: a `confirmation` verdict carrying an entity, a
        requested attribute or an intent hint is never idle chat, so `_lane` never
        sends it to the casual lane in the first place, and it reaches the no-draft
        branch by the ordinary carried-focus path regardless of whether the guard in
        `_continues_open_draft` is there at all.
        """
        v = verdict_factory(**overrides)
        with_draft, with_plan = _branch(_state(pending=pending), v)
        without_draft, _ = _branch(_state(ideation=None, pending=pending), v)
        assert with_draft == without_draft
        assert RULE not in with_plan.trace.rules_fired

    def test_submit_idea_intent_with_no_domain_hint_stays_in_ideate(self) -> None:
        """AC-7c (S2): before `_turn_helpers.POLICY_DOMAIN_ROWS` carried an `ideate` row,
        `policy.domain("ideate")` was `None` in every pure test and `own_intents` was
        always empty, so `intent_hint: "submit_idea"` with no `domain_hint` (the ideate
        row's own intent, named nowhere else in the fixture) could not be told apart
        from an intent that names nothing at all - both passed by accident. The
        fixture now carries `intents: ["submit_idea"]`, matching `policy_rows.py:273`.

        `_question_verdict` only, not `_confirm_verdict`: a `confirmation` verdict
        carrying its own `intent_hint` disqualifies `_is_idle_chat` before `_lane` ever
        runs, so it reaches `ideate` by the ordinary carried-focus business path
        (`trace.lane is None`) rather than by this rule - a real difference worth
        keeping visible, not a case this guard needs to cover twice.
        """
        branch, plan = _branch(_state(), _question_verdict(intent_hint="submit_idea"))
        assert branch == "ideate", (plan.trace.lane, plan.trace.rules_fired)
        assert RULE in plan.trace.rules_fired

    def test_a_stray_position_with_no_roster_open_still_disqualifies(self) -> None:
        """AC-7d (S3): the `reference_positions` exemption is dropped - a position
        naming nothing (no pending to answer at all) is read like any other
        `_IDLE_CHAT_DISQUALIFIERS` key, matching the plan's own wording exactly ("none
        of the subject signals `_IDLE_CHAT_DISQUALIFIERS` already lists"). An answer to
        an actually open roster is unaffected: AC-7b's `answers_open_roster` case is
        caught earlier, by the `decision.answers` guard.

        `_question_verdict`, not `_confirm_verdict`: `reference_positions` is itself
        one of `_is_idle_chat`'s own disqualifiers, so a bare confirm carrying it never
        reaches the "casual" lane in the first place (`_lane` sees a carried, non-idle
        `domains` and returns `None`, a business lane) - this guard is only reachable
        through the `clarification` lane, which `_lane` sets from the message type
        alone, with no idle-chat reading at all.
        """
        v = _question_verdict(reference_positions=[1])
        with_draft, with_plan = _branch(_state(), v)
        without_draft, _ = _branch(_state(ideation=None), v)
        assert with_draft == without_draft
        assert RULE not in with_plan.trace.rules_fired

    def test_domain_hint_guard_agrees_with_the_focus_guard(self) -> None:
        """AC-7e (N1): `domain_hint: "inventory"` already moves `focus.domains` to
        `["inventory"]` in `_focus_rules`, so the focus-axis guard rejects this before
        the explicit `domain_hint is not None` guard in `_continues_open_draft` ever
        runs. Harmless as a second guard; this pins that both agree the parser's own
        domain is never overruled.
        """
        v = _question_verdict(domain_hint="inventory")
        with_draft, with_plan = _branch(_state(), v)
        without_draft, _ = _branch(_state(ideation=None), v)
        assert with_draft == without_draft
        assert RULE not in with_plan.trace.rules_fired

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


def _seed_flat_session_variables(session_factory, variables: dict[str, Any]) -> None:
    """AC-11b (N2): the five keys directly at the top of `session_vars`, with no
    `variables` wrapper - the OTHER shape `session_state.five_keys` reads
    (`turn_runtime.py:325`). `_seed_session_variables` (reused above from
    `test_s3_canned_and_ideate`) always wraps its argument under `"variables"`, which
    is the n8n-nested shape AC-10/AC-11 already cover.
    """
    db = session_factory()
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE respond_io_id = :c"),
        {"c": str(CONTACT_ID), "sv": json.dumps(variables)},
    )
    db.commit()


def _run(
    session_factory,
    system_settings_row,
    stub_parser,
    stub_access,
    monkeypatch,
    *,
    text: str,
    parser: dict,
    seed_fn=_seed_session_variables,
):
    _seed_completed_lanes(session_factory, system_settings_row)
    seed_fn(session_factory, SEEDED_SESSION)
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


class TestEngineWithTheFlatSessionShape:
    def test_a_question_reaches_the_ideation_tool_over_the_flat_shape(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ) -> None:
        """AC-11b (N2)."""
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
            seed_fn=_seed_flat_session_variables,
        )
        assert result.branch_kind == "ideate", result.reply
        assert len(captured) == 1
        assert captured[0]["message_text"] == "what do you mean impact?"
        assert captured[0]["session_vars"] == {"ideation": OPEN_DRAFT}
