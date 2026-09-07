"""The ONE open question: seven kinds, frozen options, one resolver (AC-944 to AC-948).

Growth r1 slice B4. What is pinned here:

* a position resolves against the row the customer SAW, never a fresh lookup (AC-944);
* an unanswered question is left open and cleared by its own TTL, never answered by the
  next message that happens to arrive (AC-945);
* a quoted reply resolves against THAT message's frozen options first (AC-947);
* issue #708: a numbered pick over a partial-miss roster keeps the siblings that already
  resolved (AC-948);
* the whole lane is INERT under prompt v1 and v2, which is what lets it ship before the
  owner promotes v3 (AC-952).

The last class runs a real turn through `run_turn` with a v3-shaped emission supplied by
the harness, so the wiring is graded and not only the pure functions.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import OPEN_QUESTION_KINDS, Envelope, OpenQuestion
from app.services.chatbot.dialogue import decay as decay_mod
from app.services.chatbot.dialogue import open_question as oq
from app.services.chatbot.head import output_exchange as ox

from tests.chatbot.test_engine import (  # noqa: F401 - fixtures
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)


def _rows(*labels: str) -> list[dict[str, Any]]:
    return [
        {"idx": i, "label": label, "code": label, "uuid": f"uuid-{label}"}
        for i, label in enumerate(labels, start=1)
    ]


def _answer(**kw: Any) -> dict[str, Any]:
    return {**ox.NO_OPEN_QUESTION_ANSWER, **kw}


# --------------------------------------------------------------------------- #
# The table and the constructor
# --------------------------------------------------------------------------- #


class TestTheSevenKinds:
    def test_every_declared_kind_has_a_spec_and_a_handler(self) -> None:
        assert set(oq.KIND_SPEC) == set(OPEN_QUESTION_KINDS)
        assert set(oq._HANDLERS) == set(OPEN_QUESTION_KINDS)

    def test_ask_refuses_a_kind_nobody_declared(self) -> None:
        with pytest.raises(ValueError, match="unknown open question kind"):
            oq.ask("product_guess", turn_no=1)

    def test_ask_freezes_the_rows_and_numbers_them_as_shown(self) -> None:
        question = oq.ask("product_pick", options=_rows("A", "B"), turn_no=4)

        assert question["expects"] == "pick"
        assert question["asked_at_turn"] == 4
        assert [r["idx"] for r in question["options"]] == [1, 2]
        assert [r["uuid"] for r in question["options"]] == ["uuid-A", "uuid-B"]
        assert OpenQuestion(**question).kind == "product_pick"

    def test_a_row_without_its_own_number_gets_its_position(self) -> None:
        question = oq.ask("tier_pick", options=[{"value": "dealer"}, {"value": "office"}], turn_no=1)

        assert [r["idx"] for r in question["options"]] == [1, 2]

    def test_the_lifetimes_are_per_kind_and_not_one_number(self) -> None:
        """A roster is on screen for 3 turns; a clarify is answered next turn or not at
        all, and carrying one indefinitely masked every later offer."""
        assert oq.KIND_SPEC["member_offer"]["ttl_turns"] == 3
        assert oq.KIND_SPEC["product_pick"]["ttl_turns"] == 3
        assert oq.KIND_SPEC["team_pick"]["ttl_turns"] == 1
        assert oq.KIND_SPEC["escalate_yes_no"]["ttl_turns"] == 1


# --------------------------------------------------------------------------- #
# AC-944: a position means the row the customer saw
# --------------------------------------------------------------------------- #


class TestAPositionMeansTheRowTheCustomerSaw:
    def test_two_resolves_to_the_second_frozen_option(self) -> None:
        options = _rows("SRTWC8517", "SRTKS6091", "SRTKS8091")

        outcome = oq.resolve("product_pick", _answer(resolved=True, picks=[2]), options, {})

        assert outcome.resolved is True
        assert [r["label"] for r in outcome.picked] == ["SRTKS6091"]
        assert outcome.focus["products"][0]["uuid"] == "uuid-SRTKS6091"

    def test_the_frozen_uuid_and_code_are_carried_verbatim_never_re_resolved(self) -> None:
        options = [{"idx": 1, "label": "Old label", "code": "SRT-1", "uuid": "frozen-uuid"}]

        outcome = oq.resolve("product_pick", _answer(resolved=True, picks=[1]), options, {})

        entity = outcome.focus["products"][0]
        assert entity["uuid"] == "frozen-uuid"
        assert entity["canonical_code"] == "SRT-1"

    def test_an_out_of_range_position_is_not_a_pick(self) -> None:
        """Answering for the nearest row would be worse than asking again."""
        outcome = oq.resolve("product_pick", _answer(resolved=True, picks=[9]), _rows("A", "B"), {})

        assert outcome.resolved is False
        assert outcome.picked == []

    def test_several_positions_pick_several_rows(self) -> None:
        outcome = oq.resolve(
            "product_pick", _answer(resolved=True, picks=[1, 3]), _rows("A", "B", "C"), {}
        )

        assert [r["label"] for r in outcome.picked] == ["A", "C"]

    def test_two_again_with_no_question_alive_is_a_new_message_not_a_pick(self) -> None:
        """AC-944's second half. `decay` cleared the question, so `from_state` reads the
        explicit `None` rather than deriving one back off the legacy keys."""
        after_decay = {"open_question": None, "selection_context": "disambiguation",
                       "last_result_set": _rows("A", "B")}

        assert oq.from_state(after_decay, asked_at_turn=4) is None


# --------------------------------------------------------------------------- #
# AC-945: an unanswered question is LEFT open
# --------------------------------------------------------------------------- #


class TestAnUnansweredQuestionStaysOpen:
    def test_yes_runs_the_escalation(self) -> None:
        outcome = oq.resolve("escalate_yes_no", _answer(resolved=True, yes_no="yes"), [], {"team": "warehouse"})

        assert outcome.escalate is True
        assert outcome.routing["suggested_team"] == "warehouse"

    def test_no_renders_the_declined_copy(self) -> None:
        outcome = oq.resolve("escalate_yes_no", _answer(resolved=True, yes_no="no"), [], {})

        assert outcome.declined is True
        assert outcome.escalate is False

    def test_a_stock_question_instead_of_yes_or_no_leaves_it_unanswered(self) -> None:
        outcome = oq.resolve("escalate_yes_no", _answer(resolved=True), [], {})

        assert outcome.resolved is False
        assert outcome.escalate is False
        assert outcome.declined is False

    def test_and_the_offer_is_then_cleared_by_its_own_ttl_with_a_trace_line(self) -> None:
        session = {
            "open_question": oq.ask("escalate_yes_no", turn_no=1, options=[]),
        }
        from app.services.chatbot import trace as trace_mod

        trace = trace_mod.TurnTrace()
        result = decay_mod.apply(session, turn_no=3, ttl_turns=99, trace=trace)

        assert result.open_question is None
        entry = trace.entries("decay")[0]
        assert entry["slot"] == "open_question"
        assert entry["value"] == "escalate_yes_no"
        assert "answered silently" in entry["reason"]


# --------------------------------------------------------------------------- #
# AC-947: a quoted reply resolves against THAT message's rows
# --------------------------------------------------------------------------- #


class TestAQuotedReplyResolvesAgainstTheQuotedRows:
    def test_the_quoted_rows_win_over_the_alive_questions_own(self) -> None:
        alive = oq.ask("product_pick", options=_rows("NEW-1", "NEW-2"), turn_no=5)
        quoted = _rows("OLD-1", "OLD-2")

        outcome = oq.resolve("product_pick", _answer(resolved=True, picks=[2]), quoted, alive["payload"])

        assert [r["label"] for r in outcome.picked] == ["OLD-2"]

    def test_with_nothing_quoted_the_alive_question_answers(self) -> None:
        alive = oq.ask("product_pick", options=_rows("NEW-1", "NEW-2"), turn_no=5)

        outcome = oq.resolve(
            "product_pick", _answer(resolved=True, picks=[2]), alive["options"], alive["payload"]
        )

        assert [r["label"] for r in outcome.picked] == ["NEW-2"]


# --------------------------------------------------------------------------- #
# AC-948: issue #708
# --------------------------------------------------------------------------- #


class TestIssue708PartialMissKeepsTheSiblings:
    def test_the_pick_keeps_the_code_that_already_resolved(self) -> None:
        """"SRTKS6091 and SRTKS8091 got stock": the first resolves, the second gets a
        picker, and the pick must still answer for both."""
        resolved_sibling = {
            "raw": "SRTKS6091",
            "hint": "product",
            "canonical_code": "SRTKS6091",
            "uuid": "uuid-sibling",
        }
        options = _rows("SRTKS8091-A", "SRTKS8091-B")

        outcome = oq.resolve(
            "product_pick",
            _answer(resolved=True, picks=[2]),
            options,
            {"keep": [resolved_sibling]},
        )

        assert [e["raw"] for e in outcome.focus["products"]] == [
            "SRTKS8091-B",
            "SRTKS6091",
        ]
        assert outcome.keep == [resolved_sibling]

    def test_a_sibling_the_pick_itself_replaces_is_not_kept_twice(self) -> None:
        same = {"raw": "SRTKS8091-B", "hint": "product", "canonical_code": "SRTKS8091-B"}

        outcome = oq.resolve(
            "product_pick",
            _answer(resolved=True, picks=[2]),
            _rows("SRTKS8091-A", "SRTKS8091-B"),
            {"keep": [same]},
        )

        assert [e["raw"] for e in outcome.focus["products"]] == ["SRTKS8091-B"]

    def test_the_keep_list_is_frozen_when_the_question_is_asked(self) -> None:
        """Not re-derived at answer time: without the linkage there is nothing that says
        which token the pick answers."""
        question = oq.from_state(
            {
                "selection_context": "suggest_offer",
                "last_result_set": _rows("A", "B"),
                "entities": [{"raw": "SRTKS6091", "hint": "product"}],
            },
            asked_at_turn=3,
        )

        assert question["payload"]["keep"] == [{"raw": "SRTKS6091", "hint": "product"}]


# --------------------------------------------------------------------------- #
# The other handlers
# --------------------------------------------------------------------------- #


class TestTheRemainingHandlers:
    def test_a_customer_pick_sets_the_customer_slot(self) -> None:
        outcome = oq.resolve(
            "customer_pick",
            _answer(resolved=True, picks=[1]),
            [{"idx": 1, "label": "ABC Trading", "code": "ABC", "entity_type": "customer"}],
            {},
        )

        assert outcome.focus["customer"]["hint"] == "customer"
        assert outcome.focus["customer"]["raw"] == "ABC"

    def test_a_team_pick_sets_the_routing_and_continues_the_escalation(self) -> None:
        outcome = oq.resolve(
            "team_pick",
            _answer(resolved=True, picks=[2]),
            [
                {"idx": 1, "team": "marketing_product", "label": "Marketing Product"},
                {"idx": 2, "team": "marketing_promotion", "label": "Marketing Promotion"},
            ],
            {},
        )

        assert outcome.routing["suggested_team"] == "marketing_promotion"
        assert outcome.escalate is True

    def test_a_company_pick_names_the_company_never_its_code(self) -> None:
        outcome = oq.resolve(
            "company_pick",
            _answer(resolved=True, picks=[1]),
            [{"idx": 1, "company_name": "Sorento", "company_id": "c-1", "label": "Sorento"}],
            {},
        )

        assert outcome.routing["company_pick"] == "Sorento"
        assert outcome.routing["company_id"] == "c-1"

    def test_a_tier_pick_sets_the_tier_and_reruns_the_promotion(self) -> None:
        outcome = oq.resolve(
            "tier_pick",
            _answer(resolved=True, picks=[1]),
            [{"idx": 1, "tier": "dealer", "label": "Dealer"}],
            {},
        )

        assert outcome.tiers == ["dealer"]
        assert outcome.focus["tier"] == ["dealer"]

    def test_a_member_offer_takes_a_number_as_well_as_a_yes(self) -> None:
        """The roster is numbered in the reply the customer is looking at."""
        outcome = oq.resolve(
            "member_offer",
            _answer(resolved=True, picks=[1]),
            [{"idx": 1, "label": "Ms Tan", "uuid": "user-1", "company_id": "c-1"}],
            {},
        )

        assert outcome.routing["preferred_assignee_id"] == "user-1"
        assert outcome.escalate is True

    def test_a_kind_this_build_does_not_know_never_fails_the_turn(self) -> None:
        """The question came out of a customer's stored session."""
        outcome = oq.resolve("from_a_future_build", _answer(resolved=True, picks=[1]), [], {})

        assert outcome.resolved is False
        assert outcome.handler == "unknown"


# --------------------------------------------------------------------------- #
# The mirror
# --------------------------------------------------------------------------- #


class TestTheMirrorOffTheLegacyKeys:
    @pytest.mark.parametrize(
        "context,kind",
        [
            ("disambiguation", "product_pick"),
            ("suggest_offer", "product_pick"),
            ("member_offer", "member_offer"),
            ("tier_offer", "tier_pick"),
            ("team_clarify", "team_pick"),
            ("company_clarify", "company_pick"),
        ],
    )
    def test_each_selection_context_names_its_kind(self, context: str, kind: str) -> None:
        question = oq.from_state(
            {"selection_context": context, "last_result_set": _rows("A")}, asked_at_turn=2
        )

        assert question["kind"] == kind

    def test_a_customer_roster_under_the_same_label_is_a_customer_pick(self) -> None:
        question = oq.from_state(
            {
                "selection_context": "disambiguation",
                "last_result_set": [
                    {"idx": 1, "label": "ABC", "entity_type": "customer"},
                    {"idx": 2, "label": "ABD", "entity_type": "customer"},
                ],
            },
            asked_at_turn=2,
        )

        assert question["kind"] == "customer_pick"

    def test_a_pending_escalation_offer_with_no_roster_is_a_yes_no(self) -> None:
        question = oq.from_state(
            {"pending": {"kind": "escalation_offer", "team": "warehouse"}}, asked_at_turn=2
        )

        assert question["kind"] == "escalate_yes_no"
        assert question["expects"] == "yes_no"
        assert question["payload"]["team"] == "warehouse"

    def test_a_team_clarify_resolves_against_the_teams_the_ask_offered(self) -> None:
        """Owner rule R-a narrowed the ask, so `selection_context` alone cannot say which
        three teams were offered; the marker's own list is the roster."""
        question = oq.from_state(
            {
                "selection_context": "team_clarify",
                "last_result_set": _rows("stale", "rows"),
                "pending": {
                    "kind": "team_clarify",
                    "options": [
                        {"team": "marketing_product", "label": "Marketing Product"},
                        {"team": "marketing_form", "label": "Marketing Form"},
                    ],
                },
            },
            asked_at_turn=2,
        )

        assert [r["team"] for r in question["options"]] == [
            "marketing_product",
            "marketing_form",
        ]

    def test_nothing_open_is_none(self) -> None:
        assert oq.from_state({}, asked_at_turn=1) is None
        assert oq.from_state({"selection_context": None}, asked_at_turn=1) is None

    def test_a_stored_question_wins_over_the_derivation(self) -> None:
        stored = oq.ask("tier_pick", options=_rows("dealer"), turn_no=9)

        assert oq.from_state(
            {"open_question": stored, "selection_context": "disambiguation"}, asked_at_turn=1
        ) is stored


# --------------------------------------------------------------------------- #
# The wiring, on a real turn
# --------------------------------------------------------------------------- #


class TestTheAnsweredStepOnARealTurn:
    """The harness supplies the emission, so this grades the WIRING and not the model."""

    def _session(self, session_factory, variables: dict[str, Any]) -> None:
        from sqlalchemy import text

        db = session_factory()
        db.execute(
            text(
                "UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) "
                "WHERE respond_io_id = :c"
            ),
            {"c": CONTACT_ID, "sv": json.dumps({"variables": variables})},
        )
        db.commit()

    def _run(self, session_factory, variables: dict[str, Any], emission: dict[str, Any]):
        self._session(session_factory, variables)
        envelope = _envelope(is_test=True, mock_reformulator_output=emission)
        return engine_mod.run_turn(envelope, session_factory=session_factory)

    def test_a_v3_pick_resolves_against_the_frozen_rows_and_scopes_the_turn(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        stub_parser()
        stub_access()
        emission = _parser_output(
            message_type="casual",
            domain_hint=None,
            intent_hint=None,
            entities=[],
            answers_open_question={"resolved": True, "picks": [2], "yes_no": None, "free_text": None},
            anaphora=False,
            topic_reset=False,
        )

        result = self._run(
            session_factory,
            {
                "selection_context": "disambiguation",
                "domain_hint": "inventory",
                "last_result_set": _rows("SRTWC8517", "SRTKS6091"),
            },
            emission,
        )

        assert result.status != "failed", result.error
        qf = (result.ctx or {}).get("parse", {}).get("output", {})
        assert [e["raw"] for e in qf["entities"]] == ["SRTKS6091"]
        assert qf["open_question_answered"] == "product_pick"
        assert qf["domain_hint"] == "inventory"

    def test_the_turn_traces_the_question_the_answer_and_the_handler(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        """AC-971's open-question half, and slice D's `{before, answer, after, handler,
        outcome}` shape."""
        from app.models.chatbot_turn import ChatbotTurn

        stub_parser()
        stub_access()
        emission = _parser_output(
            message_type="casual",
            entities=[],
            answers_open_question={"resolved": True, "picks": [1], "yes_no": None, "free_text": None},
        )
        result = self._run(
            session_factory,
            {"selection_context": "disambiguation", "last_result_set": _rows("A", "B")},
            emission,
        )

        row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
        entries = [r for r in (row.trace or []) if r.get("kind") == "open_question"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["before"]["kind"] == "product_pick"
        assert entry["handler"] == "product_pick"
        assert entry["outcome"] == "Picked A."
        assert entry["answer"]["picks"] == [1]

    def test_the_lane_is_inert_without_the_v3_key(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        """AC-952: this ships before the owner promotes v3, so a v1 or v2 emission - which
        is every one of the 1,875 captures and every production turn today - must reach
        exactly the code it reaches now."""
        stub_parser()
        stub_access()
        emission = _parser_output(message_type="casual", entities=[])
        emission.pop("answers_open_question", None)

        result = self._run(
            session_factory,
            {"selection_context": "disambiguation", "last_result_set": _rows("A", "B")},
            emission,
        )

        qf = (result.ctx or {}).get("parse", {}).get("output", {})
        assert "open_question_answered" not in qf
