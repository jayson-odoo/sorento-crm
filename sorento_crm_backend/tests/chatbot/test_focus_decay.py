"""Per-slot decay and the parser hints (AC-940, AC-941, AC-971 decay entries).

Growth r1 slice B1. Three groups:

* the pure arithmetic of `dialogue/decay.py` - what is alive, what is dropped, and the
  `decay` trace line each drop writes;
* the HINTS the parser is handed instead of the raw previous state (D6), and the property
  that a build with no dialogue state sends the byte-identical user block it sends today;
* the engine wiring - the contact's turn number, the settings column it reads, and D14
  (a dry run reads the column and writes nothing, AC-982).

Postgres only, through the blank-schema `session_factory` in `tests/chatbot/conftest.py`.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import trace as trace_mod
from app.services.chatbot.contracts import FOCUS_SLOTS, Envelope, Focus, OpenQuestion, SessionVars
from app.services.chatbot.dialogue import decay as decay_mod
from app.services.chatbot.head import parser as parser_mod

from tests.chatbot.test_engine import (  # noqa: F401 - fixtures
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)


def _slot(value: Any, *, turn: int, source: str = "current_message") -> dict[str, Any]:
    return {
        "value": value,
        "set_at_turn": turn,
        "set_at": "2026-09-07T04:00:00+00:00",
        "source": source,
    }


def _product(code: str) -> dict[str, Any]:
    return {
        "raw": code,
        "hint": "product",
        "canonical_code": code,
        "current_message": True,
        "confident": True,
    }


# --------------------------------------------------------------------------- #
# The arithmetic (AC-940)
# --------------------------------------------------------------------------- #


class TestASlotAgesInTurnsAndNothingElse:
    """D11: turns only. A wall clock decides nothing anywhere in this module."""

    @pytest.mark.parametrize(
        "turn_no,expected_alive",
        [
            (1, True),  # the turn that set it
            (2, True),  # N+1
            (3, True),  # N+2, AC-940's "carries"
            (4, True),  # N+3, the last alive turn
            (5, False),  # N+4, AC-940's "does NOT carry"
        ],
    )
    def test_a_slot_set_at_turn_one_lives_for_exactly_ttl_more_turns(
        self, turn_no: int, expected_alive: bool
    ) -> None:
        slot = _slot([_product("SRTWC8517")], turn=1)

        assert decay_mod.is_alive(slot, turn_no=turn_no, ttl_turns=3) is expected_alive

    def test_a_slot_with_no_value_is_never_alive(self) -> None:
        """An empty list is the same answer as a missing key: nothing is in scope."""
        assert decay_mod.is_alive(_slot([], turn=99), turn_no=99, ttl_turns=3) is False
        assert decay_mod.is_alive(_slot(None, turn=99), turn_no=99, ttl_turns=3) is False

    def test_a_slot_written_before_this_module_existed_is_dropped_not_kept(self) -> None:
        """No `set_at_turn` means "older than any real turn", which is the safe direction.

        The customer restates what they still mean; a wrongly-KEPT scope answers a
        question nobody asked and says nothing about having done so.
        """
        legacy = {"value": [_product("SRTWC8517")]}

        assert decay_mod.is_alive(legacy, turn_no=4, ttl_turns=3) is False


class TestApplyDropsTheDeadAndTracesEveryDrop:
    """AC-941 / AC-971: every decayed slot writes ONE `decay` entry naming its age."""

    def test_the_dead_slot_is_gone_and_the_alive_one_is_kept(self) -> None:
        variables = {
            "focus": {
                "products": _slot([_product("SRTWC8517")], turn=1),
                "domain": _slot("inventory", turn=4),
            }
        }
        trace = trace_mod.TurnTrace()

        result = decay_mod.apply(variables, turn_no=5, ttl_turns=3, trace=trace)

        assert set(result.focus) == {"domain"}
        assert [d["slot"] for d in result.dropped] == ["products"]

    def test_the_drop_is_traced_with_the_slot_the_value_and_the_age_in_turns(self) -> None:
        variables = {"focus": {"products": _slot([_product("SRTWC8517")], turn=1)}}
        trace = trace_mod.TurnTrace()

        decay_mod.apply(variables, turn_no=5, ttl_turns=3, trace=trace)

        entries = trace.entries("decay")
        assert len(entries) == 1
        entry = entries[0]
        assert entry["kind"] == "decay"
        assert entry["slot"] == "products"
        assert entry["set_at_turn"] == 1
        assert entry["age_turns"] == 4
        assert "3" in entry["reason"]
        assert entry["value"] == [_product("SRTWC8517")]

    def test_a_decay_entry_is_never_a_timeline_stage(self) -> None:
        """The trace array carries stages AND decisions; only stages have a `stage`."""
        trace = trace_mod.TurnTrace()
        trace.record("received", summary="s", why="w")
        decay_mod.apply(
            {"focus": {"products": _slot([_product("X")], turn=1)}},
            turn_no=9,
            ttl_turns=3,
            trace=trace,
        )

        assert trace.stages() == ["received"]
        assert len(trace.records) == 2

    def test_an_unanswered_open_question_dies_on_its_own_ttl_not_the_focus_one(self) -> None:
        """AC-945: an offer nobody answered is cleared with a trace line, never silently
        answered by a later reply."""
        variables = {
            "open_question": {
                "kind": "escalate_yes_no",
                "expects": "yes_no",
                "options": [],
                "asked_at_turn": 1,
                "ttl_turns": 1,
                "payload": {},
            }
        }
        trace = trace_mod.TurnTrace()

        result = decay_mod.apply(variables, turn_no=3, ttl_turns=99, trace=trace)

        assert result.open_question is None
        assert [e["slot"] for e in trace.entries("decay")] == ["open_question"]
        assert trace.entries("decay")[0]["value"] == "escalate_yes_no"

    def test_an_open_question_inside_its_ttl_survives(self) -> None:
        variables = {
            "open_question": {
                "kind": "member_offer",
                "expects": "yes_no",
                "options": [],
                "asked_at_turn": 1,
                "ttl_turns": 3,
                "payload": {},
            }
        }

        result = decay_mod.apply(variables, turn_no=4, ttl_turns=3, trace=None)

        assert (result.open_question or {}).get("kind") == "member_offer"

    def test_a_session_written_by_an_older_build_never_raises(self) -> None:
        """n8n and every pre-slice-B turn wrote a session with none of these keys."""
        result = decay_mod.apply({"domain_hint": "order"}, turn_no=2, ttl_turns=3, trace=None)

        assert result.focus == {}
        assert result.open_question is None
        assert result.focus_hints == {}
        assert result.open_question_hint is None


# --------------------------------------------------------------------------- #
# The hints (D6)
# --------------------------------------------------------------------------- #


class TestTheParserIsHandedHintsNotState:
    def test_a_product_slot_reaches_the_parser_as_the_entity_shape_it_already_emits(
        self,
    ) -> None:
        hints = decay_mod.focus_hints({"products": _slot([_product("SRTWC8517")], turn=2)})

        assert hints == {
            "products": [
                {"raw": "SRTWC8517", "hint": "product", "canonical_code": "SRTWC8517"}
            ]
        }

    def test_bookkeeping_never_reaches_the_model(self) -> None:
        hints = decay_mod.focus_hints({"domain": _slot("inventory", turn=2, source="reuse")})

        assert hints == {"domain": "inventory"}
        assert "set_at_turn" not in json.dumps(hints)
        assert "source" not in json.dumps(hints)

    def test_the_open_question_hint_carries_labels_and_never_a_uuid(self) -> None:
        """A uuid on the prompt is a value the model could hallucinate back. The engine
        resolves a position against the frozen rows itself."""
        hint = decay_mod.open_question_hint(
            {
                "kind": "product_pick",
                "expects": "pick",
                "options": [
                    {"idx": 1, "uuid": "u-1", "code": "SRTWC8517", "label": "SRTWC8517 basin"},
                    {"idx": 2, "uuid": "u-2", "code": "SRTWC8518", "label": "SRTWC8518 basin"},
                ],
                "asked_at_turn": 3,
                "ttl_turns": 1,
                "payload": {},
            }
        )

        assert hint == {
            "kind": "product_pick",
            "expects": "pick",
            "options": [
                {"idx": 1, "label": "SRTWC8517 basin"},
                {"idx": 2, "label": "SRTWC8518 basin"},
            ],
        }
        assert "u-1" not in json.dumps(hint)

    def test_no_dialogue_state_means_the_user_block_is_unchanged(self) -> None:
        """The parity property: a build mid-rollout sends today's bytes exactly."""
        without = parser_mod.build_user_block(
            previous_response="hi", latest_user_message="stock?", pending_kind=None
        )
        with_empty = parser_mod.build_user_block(
            previous_response="hi",
            latest_user_message="stock?",
            pending_kind=None,
            focus_hints={},
            open_question_hint=None,
        )

        assert without == with_empty
        assert "Focus:" not in without

    def test_alive_focus_becomes_one_compact_line(self) -> None:
        block = parser_mod.build_user_block(
            previous_response="hi",
            latest_user_message="incoming?",
            pending_kind=None,
            focus_hints={"domain": "inventory"},
            open_question_hint={"kind": "escalate_yes_no", "expects": "yes_no", "options": []},
        )

        lines = block.split("\n")
        assert lines[-2] == 'Focus: {"domain": "inventory"}'
        assert lines[-1].startswith("Open question: ")


# --------------------------------------------------------------------------- #
# The contract (AC-940's shapes, AC-951's "nothing else moved")
# --------------------------------------------------------------------------- #


class TestTheSessionContract:
    def test_session_vars_accepts_focus_and_open_question(self) -> None:
        parsed = SessionVars(
            focus=Focus(products=None),
            open_question=OpenQuestion(kind="product_pick", expects="pick"),
        )

        assert parsed.open_question is not None
        assert parsed.open_question.ttl_turns == 1

    def test_focus_forbids_an_axis_nobody_declared(self) -> None:
        """`extra = "forbid"` stays: a stray diagnostic must not leak into a session."""
        with pytest.raises(Exception):
            Focus(**{"invented_axis": None})  # type: ignore[arg-type]

    def test_every_declared_slot_is_a_field_on_the_model(self) -> None:
        assert set(FOCUS_SLOTS) == set(Focus.model_fields)


# --------------------------------------------------------------------------- #
# The engine wiring
# --------------------------------------------------------------------------- #


class TestTheTurnNumberIsTheContactsOwn:
    """`turn_no` is derived from the rows, per world (H57), so a dry run never ages a
    real customer's conversation."""

    def _seed_turn(self, session_factory, *, is_test: bool) -> None:
        db = session_factory()
        db.add(
            ChatbotTurn(
                contact_respond_id=CONTACT_ID,
                message_id=None,
                ingress="console",
                envelope={},
                is_test=is_test,
                status="done",
                stage="sent",
                attempt=1,
                trace=[],
            )
        )
        db.commit()

    def test_the_first_turn_of_a_contact_is_turn_one(self, session_factory) -> None:
        self._seed_turn(session_factory, is_test=False)
        db = session_factory()

        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, is_test=False) == 1

    def test_live_turns_and_test_turns_count_separately(self, session_factory) -> None:
        self._seed_turn(session_factory, is_test=False)
        self._seed_turn(session_factory, is_test=False)
        self._seed_turn(session_factory, is_test=True)
        db = session_factory()

        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, is_test=False) == 2
        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, is_test=True) == 1


class TestTheEngineReadsTheTtlColumn:
    def test_the_default_is_three_when_there_is_no_settings_row(self) -> None:
        assert engine_mod._focus_ttl_turns(None) == engine_mod.DEFAULT_FOCUS_TTL_TURNS == 3

    def test_operator_nonsense_falls_back_rather_than_failing_the_turn(self) -> None:
        class _Row:
            chatbot_focus_ttl_turns = "not a number"

        assert engine_mod._focus_ttl_turns(_Row()) == 3

    def test_a_negative_is_clamped_to_this_turn_only(self) -> None:
        class _Row:
            chatbot_focus_ttl_turns = -5

        assert engine_mod._focus_ttl_turns(_Row()) == 0

    def test_the_configured_value_is_what_the_turn_runs_under(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        """AC-982: a DRY RUN reads the column, and writes nothing outside `chatbot.turns`.

        The read is what this asserts; the "writes nothing" half is already asserted by
        `test_engine.py`'s D14 block and by `test_dry_run_isolation.py`, and this adds the
        new column to the same claim by checking the contact's session blob is untouched.
        """
        db = session_factory()
        row = SystemSetting()
        row.chatbot_focus_ttl_turns = 7
        db.add(row)
        db.commit()
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(is_test=True), session_factory=session_factory)

        assert result.status != "failed"
        received = next(r for r in _trace_of(session_factory, result.turn_id) if r.get("stage") == "received")
        assert received["facts"]["focus_ttl_turns"] == 7
        assert received["facts"]["turn_no"] == 1
        stored = session_factory().execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": CONTACT_ID},
        ).scalar()
        stored = json.loads(stored) if isinstance(stored, str) else stored
        assert (stored or {}).get("variables") == {}


def _trace_of(session_factory, turn_id: str) -> list[dict[str, Any]]:
    row = (
        session_factory()
        .query(ChatbotTurn)
        .filter(ChatbotTurn.id == turn_id)
        .first()
    )
    return list(row.trace or [])
