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


# `TestTheSevenKinds` retired here (D5, D9): `escalate_yes_no` folds into `team_pick`
# (six kinds, not seven) and `ttl_turns` is gone from `KIND_SPEC` entirely - no counter,
# no TTL, anywhere. Ported coverage: `tests/chatbot/test_open_question_shape.py`
# (`test_kinds_are_exactly_six`, `test_option_idx_numbered_from_one_and_carries_domain`).


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

    # `test_two_again_with_no_question_alive_is_a_new_message_not_a_pick` RETIRED (S3d
    # step 4): `oq.from_state` is deleted - it was the LEGACY-SESSION DERIVATION step this
    # claim measured (an explicit `None` wins over stale legacy markers alongside it).
    # There is no derivation left to test: `output_exchange.open_question_of` reads
    # `state["open_question"]` directly and never looks at `selection_context` /
    # `last_result_set` at all, so the claim is now true by construction rather than by a
    # precedence rule - see `open_question_of`'s own docstring, `app/services/chatbot/
    # head/output_exchange.py`.


# --------------------------------------------------------------------------- #
# AC-945: an unanswered question is LEFT open
# --------------------------------------------------------------------------- #


class TestAnUnansweredQuestionStaysOpen:
    """D5: a one-team escalate offer is `team_pick` with `expects: yes_no` and no
    roster - the same yes/no shape `escalate_yes_no` used to be, folded into the one
    kind. D9 retired this class's fourth test (`...cleared_by_its_own_ttl...`): no
    counter, no TTL, anywhere - an unanswered question is cleared only by
    `dialogue/clearing.py`'s three causes (a same-axis replace, a topic reset, or the
    conversation-closed marker), never by age. See `tests/chatbot/test_open_question_clearing.py`
    for that behaviour."""

    def test_yes_runs_the_escalation(self) -> None:
        outcome = oq.resolve("team_pick", _answer(resolved=True, yes_no="yes"), [], {"team": "warehouse"})

        assert outcome.escalate is True
        assert outcome.routing["suggested_team"] == "warehouse"

    def test_no_renders_the_declined_copy(self) -> None:
        outcome = oq.resolve("team_pick", _answer(resolved=True, yes_no="no"), [], {})

        assert outcome.declined is True
        assert outcome.escalate is False

    def test_a_stock_question_instead_of_yes_or_no_leaves_it_unanswered(self) -> None:
        outcome = oq.resolve("team_pick", _answer(resolved=True), [], {})

        assert outcome.resolved is False
        assert outcome.escalate is False
        assert outcome.declined is False


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

    # `test_the_keep_list_is_frozen_when_the_question_is_asked` and
    # `test_with_no_linkage_nothing_is_kept_rather_than_guessed` RETIRED (S3d step 4):
    # both called the deleted `oq.from_state`, which derived `payload.keep` off legacy
    # `dym_offer.candidates` linkage at LEGACY-SESSION READ time. The lane that offers a
    # `product_pick` now calls `open_question.ask(..., payload={"keep": [...]})` directly
    # at the point it decides the linkage (issue #708), so the freezing claim these two
    # made is the LANE's own responsibility now, not `open_question.py`'s - covered by
    # `test_pass4_item4_issue708_partial_pick_scope.py`, which grades it end to end
    # through the real miss-suggest lane rather than a `from_state` unit call.


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


# `TestTheMirrorOffTheLegacyKeys` retired here (AC-1033, owner 12 Sep 2026: "no
# persisted mirrors" reverses growth-r1's direction). `from_state` derived
# `open_question` FROM the legacy `pending` / `selection_context` / `last_result_set` /
# `dym_last_result_set` markers; those markers no longer exist in `SessionVars` at all
# (five keys only), so nothing is left to derive FROM. `open_question` is authoritative
# now, written directly by `dialogue/open_question.py::ask` at the point each lane
# decides to ask. Ported coverage: `tests/chatbot/test_open_question_clearing.py`.


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
        stub_parser(emits_v3=True)
        stub_access()
        emission = _parser_output(
            message_type="casual",
            domain_hint=None,
            intent_hint=None,
            entities=[],
            asks=[],
            answers_open_question={"resolved": True, "picks": [2], "yes_no": None, "free_text": None},
            anaphora=False,
            topic_reset=False,
        )

        result = self._run(
            session_factory,
            {
                "focus": {"domains": {"value": ["inventory"], "set_at_turn": 1, "set_at": None, "source": "reuse"}},
                "open_question": oq.ask(
                    "product_pick",
                    options=_rows("SRTWC8517", "SRTKS6091"),
                    turn_no=1,
                ),
                "ideation": None,
                "access_levels": [],
                "contains_flyer": False,
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

        stub_parser(emits_v3=True)
        stub_access()
        emission = _parser_output(
            message_type="casual",
            entities=[],
            asks=[],
            answers_open_question={"resolved": True, "picks": [1], "yes_no": None, "free_text": None},
            anaphora=False,
            topic_reset=False,
        )
        result = self._run(
            session_factory,
            {
                "focus": {},
                "open_question": oq.ask("product_pick", options=_rows("A", "B"), turn_no=1),
                "ideation": None,
                "access_levels": [],
                "contains_flyer": False,
            },
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

    def test_a_v1_parse_is_inert_even_when_the_emission_carries_the_keys(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        """The gate is the CONTRACT, not the key's presence: a v1 prompt held to a v3
        schema would emit all three, invented."""
        stub_parser()  # v1
        stub_access()
        emission = _parser_output(
            message_type="casual",
            entities=[],
            asks=[],
            answers_open_question={"resolved": True, "picks": [1], "yes_no": None, "free_text": None},
            anaphora=False,
            topic_reset=False,
        )

        result = self._run(
            session_factory,
            {"selection_context": "disambiguation", "last_result_set": _rows("A", "B")},
            emission,
        )

        qf = (result.ctx or {}).get("parse", {}).get("output", {})
        assert "open_question_answered" not in qf

    def test_the_lane_is_inert_without_the_v3_key(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        """AC-952: this ships before the owner promotes v3, so a v1 or v2 emission - which
        is every one of the 1,875 captures and every production turn today - must reach
        exactly the code it reaches now."""
        stub_parser()  # v1: the promoted contract
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


class TestTheClockDoesNotRestartOnACarry:
    """Blocker 4 of the 7 Sep review: a TTL that is re-stamped every turn is not a TTL.

    `compile_state` re-derives the mirror on every turn, and the legacy lifecycle keeps a
    roster alive across turns that build no offer of their own (owner ruling K rule 1). So
    without `same_question` the age was permanently 1 and nothing could ever expire.
    """

    # `test_the_same_roster_keeps_the_turn_it_was_actually_asked_on`,
    # `test_a_changed_roster_is_a_new_question` and
    # `test_a_changed_KIND_is_a_new_question_even_on_the_same_rows` RETIRED (S3d step 4):
    # all three called the deleted `oq.from_state`, which owned the
    # "same_question -> keep the old asked_at_turn" carry this class is named for. The
    # carry itself SURVIVES - `same_question` is still called for exactly this reason, now
    # inline in `tail/compile_state.py` (`if pending_open_question.same_question(asked,
    # previous) and isinstance(previous, dict): turn_no = int(previous.get(
    # "asked_at_turn", turn_no))`) - but that is a private, per-turn calculation over a
    # `ctx`-shaped state this module has no seam to drive directly, not a small pure
    # function `open_question.py` still exports. `test_identity_is_the_row_not_its_number`
    # right below keeps the ONE piece of this class `same_question` itself still owns.

    def test_identity_is_the_row_not_its_number(self) -> None:
        """A list whose numbering is identical and whose CONTENTS changed is a different
        list, and a customer answering "2" is answering about a different thing."""
        assert oq.same_question(
            {"kind": "product_pick", "options": _rows("A", "B")},
            {"kind": "product_pick", "options": _rows("A", "B")},
        )
        assert not oq.same_question(
            {"kind": "product_pick", "options": _rows("A", "B")},
            {"kind": "product_pick", "options": _rows("A", "C")},
        )

    # `test_an_unanswered_question_outlives_the_marker_that_made_it` and
    # `test_an_ANSWERED_question_is_never_re_armed` RETIRED (S3d step 4): both called the
    # deleted `oq.from_state`. Their claims survive as `compile_state.py`'s own
    # `elif`/`else` arms quoted above ("nothing asked this turn: the one the customer is
    # still looking at stands" / "CONSUMED. A question the customer has answered is never
    # re-armed") - engine-level behaviour now, covered by
    # `test_s5_escalation_lane.py`'s real-turn suite rather than a pure `open_question.py`
    # unit call.
