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
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
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
    """One slot. NO wall clock: the state ages in turns only (D11) and AC-206 wants a dry
    run's session patch byte-equal to a live run's, which a timestamp would break."""
    return {"value": value, "set_at_turn": turn, "source": source}


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
        assert len(trace.persisted()) == 2

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
            emits_v3=True,
            focus_hints={},
            open_question_hint=None,
        )

        assert without == with_empty
        assert "Focus:" not in without

    def test_a_v1_prompt_is_sent_no_hints_even_with_focus_alive(self) -> None:
        """The gate is the PROMPT VERSION, not "are there hints".

        v1 and v2 have no instruction that mentions either block, so sending them to the
        promoted prompt would hand the live model two labelled blocks it was never told
        how to read - and it would do so for exactly the contacts who have been talking
        longest, which is the worst possible population to change under.
        """
        block = parser_mod.build_user_block(
            previous_response="hi",
            latest_user_message="incoming?",
            pending_kind=None,
            emits_v3=False,
            focus_hints={"domain": "inventory", "products": [{"raw": "SRTWC8517"}]},
            open_question_hint={"kind": "escalate_yes_no", "expects": "yes_no", "options": []},
        )

        assert "Focus:" not in block
        assert "Open question:" not in block

    def test_alive_focus_becomes_one_compact_line_under_v3(self) -> None:
        block = parser_mod.build_user_block(
            previous_response="hi",
            latest_user_message="incoming?",
            pending_kind=None,
            emits_v3=True,
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
    """`turn_no` is counted STRICTLY BEFORE this row, over live turns plus this console
    run's own, attempt 1 only. Each clause is a defect the 7 Sep review caught."""

    def _seed(
        self,
        session_factory,
        *,
        is_test: bool = False,
        attempt: int = 1,
        run: str | None = None,
        seconds: int = 0,
        message_id: str | None = None,
    ) -> ChatbotTurn:
        db = session_factory()
        row = ChatbotTurn(
            contact_respond_id=CONTACT_ID,
            message_id=message_id,
            ingress="console",
            envelope={},
            is_test=is_test,
            test_run_id=run,
            status="done",
            stage="sent",
            attempt=attempt,
            trace=[],
            started_at=datetime(2026, 9, 7, 4, 0, seconds, tzinfo=timezone.utc),
        )
        db.add(row)
        db.commit()
        return row

    def test_the_first_turn_of_a_contact_is_turn_one(self, session_factory) -> None:
        row = self._seed(session_factory)

        assert engine_mod._turn_no(
            session_factory(), contact_respond_id=CONTACT_ID, row=row
        ) == 1

    def test_two_messages_in_flight_together_get_different_numbers(
        self, session_factory
    ) -> None:
        """The defect: the row goes in BEFORE the ordering ticket is taken, so two
        messages from one dealer arriving together were both counted by a plain total and
        the second turn aged nothing."""
        first = self._seed(session_factory, seconds=1)
        second = self._seed(session_factory, seconds=2)
        db = session_factory()

        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=first) == 1
        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=second) == 2

    def test_rows_written_in_one_transaction_still_order(self, session_factory) -> None:
        """`created_at` is `now()` and every row in one transaction shares it, which is
        why the anchor is `started_at`."""
        rows = [self._seed(session_factory, seconds=i) for i in range(1, 4)]
        db = session_factory()

        assert [
            engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=r) for r in rows
        ] == [1, 2, 3]

    def test_the_id_breaks_a_tie_at_identical_started_at(self, session_factory) -> None:
        """The other half of the ordering, and the reason it is a ROW comparison.

        `started_at` comes from the Python clock, so two rows written in the same
        microsecond are possible - and with the anchor alone they would both count the
        same predecessors and share a number. The id is the total order underneath it, so
        the three rows below take 1, 2, 3 in id order however they were seeded.
        """
        rows = [self._seed(session_factory, seconds=7) for _ in range(3)]
        assert len({r.started_at for r in rows}) == 1, "the tie is the point of this test"
        db = session_factory()

        by_id = sorted(rows, key=lambda r: str(r.id))
        assert [
            engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=r) for r in by_id
        ] == [1, 2, 3]

    def test_a_retry_row_never_ages_the_turns_after_it(self, session_factory) -> None:
        """A retry is the SAME customer message run again (`_insert_turn` writes attempt
        N+1 for it), so counting it would age the conversation by one every time an
        operator pressed Retry."""
        self._seed(session_factory, seconds=1, message_id="m-1")
        self._seed(session_factory, attempt=2, seconds=2, message_id="m-1")
        self._seed(session_factory, attempt=3, seconds=3, message_id="m-1")
        later = self._seed(session_factory, seconds=4, message_id="m-2")
        db = session_factory()

        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=later) == 2

    def test_a_retry_reads_the_number_its_original_read(self, session_factory) -> None:
        """It is re-running ONE customer message, not moving the conversation on.

        `attempt == 1` alone was not enough: the original is an attempt-1 row for the same
        message and it sorts before the retry, so it counted itself into the retry's number
        (measured: original 1, retry 2) and the retried turn read a memory the original
        never saw.
        """
        original = self._seed(session_factory, seconds=1, message_id="m-1")
        retry = self._seed(session_factory, attempt=2, seconds=2, message_id="m-1")
        third = self._seed(session_factory, attempt=3, seconds=3, message_id="m-1")
        db = session_factory()

        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=original) == 1
        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=retry) == 1
        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=third) == 1

    def test_a_retry_still_counts_every_OTHER_message(self, session_factory) -> None:
        self._seed(session_factory, seconds=1, message_id="m-1")
        self._seed(session_factory, seconds=2, message_id="m-2")
        retry = self._seed(session_factory, attempt=2, seconds=3, message_id="m-2")
        db = session_factory()

        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=retry) == 2

    def test_a_console_turn_with_no_message_id_is_still_counted(self, session_factory) -> None:
        """`NULL != 'x'` is NULL in SQL, so a naive exclusion would have dropped every
        preceding console turn out of the count."""
        self._seed(session_factory, seconds=1, message_id=None)
        self._seed(session_factory, seconds=2, message_id=None)
        mine = self._seed(session_factory, seconds=3, message_id="m-9")
        db = session_factory()

        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=mine) == 3

    def test_a_dry_run_reads_the_counter_a_live_turn_would(self, session_factory) -> None:
        """AC-206: the two session patches have to be byte-equal, and `set_at_turn` is in
        them. A console turn that read 1 where live read 41 would differ on every slot."""
        for i in range(1, 4):
            self._seed(session_factory, seconds=i)
        # The shape `test_complete_turn.py` runs: the dry turn first, then the live one
        # from the SAME starting state. Both must read the same number, or every slot in
        # the patch differs on `set_at_turn`.
        console = self._seed(session_factory, is_test=True, run="run-A", seconds=9)
        live = self._seed(session_factory, seconds=10)
        db = session_factory()

        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=console) == 4
        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=live) == 4, (
            "the console preview must not have aged the live conversation"
        )

    def test_a_multi_turn_console_run_still_advances(self, session_factory) -> None:
        for i in range(1, 4):
            self._seed(session_factory, seconds=i)
        first = self._seed(session_factory, is_test=True, run="run-A", seconds=8)
        second = self._seed(session_factory, is_test=True, run="run-A", seconds=9)
        db = session_factory()

        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=first) == 4
        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=second) == 5

    def test_another_console_run_never_ages_this_one(self, session_factory) -> None:
        """H57 in the counter: a test turn belongs to its own run and to nothing else."""
        self._seed(session_factory, seconds=1)
        self._seed(session_factory, is_test=True, run="run-A", seconds=2)
        self._seed(session_factory, is_test=True, run="run-A", seconds=3)
        mine = self._seed(session_factory, is_test=True, run="run-B", seconds=4)
        db = session_factory()

        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=mine) == 2

    def test_a_test_turn_with_no_run_id_reads_the_live_counter(self, session_factory) -> None:
        """`is_test` with no `test_run_id` is the chat console's single-shot preview."""
        self._seed(session_factory, seconds=1)
        self._seed(session_factory, seconds=2)
        mine = self._seed(session_factory, is_test=True, seconds=3)
        db = session_factory()

        assert engine_mod._turn_no(db, contact_respond_id=CONTACT_ID, row=mine) == 3


# `TestTheEngineReadsTheTtlColumn` retired here (D9, owner 12 Sep 2026): no counter, no
# TTL, anywhere. `system_settings.chatbot_focus_ttl_turns` and
# `engine_mod._focus_ttl_turns` go with it - a focus slot is cleared only by a
# same-axis replace, a topic reset, or the conversation-closed marker
# (`dialogue/clearing.py`, see `tests/chatbot/test_clearing.py`), never by age.


def _trace_of(session_factory, turn_id: str) -> list[dict[str, Any]]:
    row = (
        session_factory()
        .query(ChatbotTurn)
        .filter(ChatbotTurn.id == turn_id)
        .first()
    )
    return list(row.trace or [])
