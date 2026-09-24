"""Dealer stock verdict - S3, the apply-level task lifecycle: open/fill/park/resume/
close/tie (AC-1765, AC-1766, AC-1775, AC-1777, AC-1779, AC-1786).

UAC "The open task on the focus (D21 to D23)" + rulings D13, D15, D16, D21 to D26. PLAN
"The engine (S3)" seam 3 (`turn/task.py`) and its lifecycle bullet list.

Style: hand-built `State`/verdict/`policy` through `apply()`, the same shape
`test_rearch_s2_focus_rules.py` and `test_rearch_s2_pending_one_object.py` already use
(`tests/chatbot/_turn_helpers.py::build_policy`/`verdict`).

RIGHT NOW every test is RED: `app/services/chatbot/turn/task.py` does not exist
(`ModuleNotFoundError`), and `Focus(tasks=...)` raises `TypeError: unexpected keyword
argument 'tasks'` until `turn/state.py::Focus` gains the field - both are exactly the
missing-module/missing-field shape the brief calls out, not a fixture bug: every test
below fails at its very first setup line, before `apply()` is ever reached.

Two design choices flagged to the captain rather than silently assumed (also in the
report):

1. **AC-1779's "ideation task open with `pending_media` set"**: `apply()`'s `State`
   dataclass carries no `ideation` field at all (only `focus`, `pending`, `profile`,
   `turn_no`) - `session.ideation`, where `pending_media` actually lives, is read today
   only by `lanes/ideate.py`, outside `apply()`'s inputs entirely. This file drops the
   `pending_media` detail from the tie scenario (an open `ideation` Task on
   `Focus.tasks` is enough to exercise the D24(b) tie rule) and flags that
   `IdeationTask.claims` needing `session.ideation.pending_media` is a real, open
   wiring question - `apply()` may need a new keyword parameter for it, the same shape
   `resolved`/`candidates`/`unplaced` already are.
2. **AC-1786's "closes on the tool's word"**: `apply()` runs BEFORE the fetch, so
   `crm_ideation_turn`'s `status: "complete"` cannot reach it on the SAME call that
   opened the lane - closing on that word is necessarily a decision made from the tool
   REPLY, which today happens in `engine.py`'s separate, older `ideate` branch (see
   `lanes/ideate.py::run`), not inside `turn/apply.py` at all. This file tests the half
   that genuinely is an `apply()` concern (a `topic_reset` aimed at `ideate` closes the
   task, mirroring the stock task's own close-on-reset rule) plus a narrow, unit-level
   classifier on the `TaskKind` itself (`closes_on_tool_status`) rather than inventing an
   unknown `apply()` call shape for the tool-status half.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from tests.chatbot._turn_helpers import build_policy, entity, verdict


def _state(focus, *, pending=None, turn_no=0):
    from app.services.chatbot.turn.state import Profile, State

    return State(focus=focus, pending=pending, profile=Profile(), turn_no=turn_no)


def _stock_task(*, slots, status="open", opened_at_turn=1, touched_at_turn=1):
    from app.services.chatbot.turn.task import Slot, Task

    return Task(
        kind="stock_qty",
        domain="inventory",
        status=status,
        opened_at_turn=opened_at_turn,
        touched_at_turn=touched_at_turn,
        slots=tuple(Slot(key=k, label=l, value=v) for (k, l, v) in slots),
    )


def _ideation_task(*, status="open", opened_at_turn=1, touched_at_turn=1):
    from app.services.chatbot.turn.task import Task

    return Task(
        kind="ideation",
        domain="ideate",
        status=status,
        opened_at_turn=opened_at_turn,
        touched_at_turn=touched_at_turn,
        slots=(),
    )


def _slot_values(task):
    return {s.key: s.value for s in task.slots}


def _task_of_kind(focus, kind):
    for t in focus.tasks:
        if t.kind == kind:
            return t
    raise AssertionError(f"no {kind!r} task on focus.tasks: {focus.tasks}")


# --------------------------------------------------------------------------- #
# AC-1765: the D13 bare-number fallback
# --------------------------------------------------------------------------- #


def test_apply_stock_qty_bare_number_single_missing_assigns_it():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(
        slots=[("uuid-a", "A", 5), ("uuid-b", "B", 60), ("uuid-c", "C", None)]
    )
    focus = Focus(tasks=(task,))
    v = verdict(demand_qty=110, entities=[])

    state2, _plan = apply(_state(focus), v, build_policy())

    stock = _task_of_kind(state2.focus, "stock_qty")
    assert _slot_values(stock) == {"uuid-a": 5, "uuid-b": 60, "uuid-c": 110}


def test_apply_stock_qty_bare_number_two_missing_reasks_both():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(
        slots=[("uuid-a", "A", 5), ("uuid-c", "C", None), ("uuid-d", "D", None)]
    )
    focus = Focus(tasks=(task,))
    v = verdict(demand_qty=110, entities=[])

    state2, _plan = apply(_state(focus), v, build_policy())

    stock = _task_of_kind(state2.focus, "stock_qty")
    assert _slot_values(stock) == {"uuid-a": 5, "uuid-c": None, "uuid-d": None}, (
        "a bare number with two slots still missing must not guess which one it is for"
    )


# --------------------------------------------------------------------------- #
# AC-1766: topic_reset close vs park; D23 continuity
# --------------------------------------------------------------------------- #


def test_apply_stock_qty_topic_reset_aimed_at_its_own_domain_closes_the_task():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(slots=[("uuid-a", "A", 5), ("uuid-c", "C", None)])
    focus = Focus(tasks=(task,))
    v = verdict(topic_reset=True, domain_hint="inventory", entities=[])

    state2, _plan = apply(_state(focus), v, build_policy())

    assert state2.focus.tasks == (), state2.focus.tasks


def test_apply_stock_qty_topic_reset_with_no_domain_hint_also_closes():
    """D23: `topic_reset: true` with `domain_hint` null is aimed at the task's own
    domain (there is nowhere else for it to be aimed while the stock task is the only
    open task) and closes it."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(slots=[("uuid-a", "A", 5), ("uuid-c", "C", None)])
    focus = Focus(tasks=(task,))
    v = verdict(topic_reset=True, domain_hint=None, entities=[])

    state2, _plan = apply(_state(focus), v, build_policy())

    assert state2.focus.tasks == ()


def test_apply_stock_qty_topic_reset_aimed_elsewhere_parks_not_closes():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(slots=[("uuid-a", "A", 5), ("uuid-c", "C", None)])
    focus = Focus(tasks=(task,))
    v = verdict(
        topic_reset=True,
        domain_hint="promotion",
        entities=[entity("MSK11A-QT", hint="product")],
    )

    state2, _plan = apply(_state(focus), v, build_policy())

    stock = _task_of_kind(state2.focus, "stock_qty")
    assert stock.status == "parked"
    assert _slot_values(stock) == {"uuid-a": 5, "uuid-c": None}, "the slots ride unchanged"


# --------------------------------------------------------------------------- #
# AC-1775: no expiry across 12 out-of-scope turns
# --------------------------------------------------------------------------- #


def test_apply_task_survives_twelve_carry_turns_then_fills_on_the_thirteenth_message():
    """D22/D23: no TTL, no turn counter. A parked task rides through twelve casual
    CARRY turns unchanged and fills on the next turn that actually names its slots -
    the UAC's own "turn 15" counting the two turns that opened and detoured it plus the
    twelve CARRY turns that follow (1 open/detour-adjacent + 12 CARRY = 13; the UAC's
    "15" additionally counts the journey's own turns 1-2 before the detour, which this
    focused table test starts already-parked past, per its own docstring scope)."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(
        slots=[("uuid-a", "A", 5), ("uuid-c", "C", None), ("uuid-d", "D", None)],
        status="parked",
    )
    focus = Focus(tasks=(task,))
    state = _state(focus, turn_no=2)
    policy = build_policy()

    for i in range(12):
        carry_verdict = verdict(message_type="casual", entities=[], user_goal="thanks")
        state, _plan = apply(replace(state, turn_no=state.turn_no + 1), carry_verdict, policy)
        stock = _task_of_kind(state.focus, "stock_qty")
        assert stock.status == "parked", f"carry turn {i}: task must stay parked"
        assert _slot_values(stock) == {"uuid-a": 5, "uuid-c": None, "uuid-d": None}, (
            f"carry turn {i}: slots must not move"
        )

    filling_verdict = verdict(
        entities=[entity("C", hint="product", quantity=110), entity("D", hint="product", quantity=20)]
    )
    final_state, _plan = apply(replace(state, turn_no=state.turn_no + 1), filling_verdict, policy)
    stock = _task_of_kind(final_state.focus, "stock_qty")
    assert _slot_values(stock) == {"uuid-a": 5, "uuid-c": 110, "uuid-d": 20}


# --------------------------------------------------------------------------- #
# AC-1777: the TaskKind protocol drives a throwaway third kind with no engine change
# --------------------------------------------------------------------------- #


def test_task_kind_protocol_second_kind_drives_same_seams():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus
    from app.services.chatbot.turn.task import TASK_KINDS, Slot, Task

    assert {"stock_qty", "ideation"} <= set(TASK_KINDS), (
        "AC-1777: TASK_KINDS must register both production kinds"
    )

    class _WidgetTask:
        """A throwaway third kind: two TEXT slots, claimed by a `widget_topic`/
        `widget_detail` pair the test invents on the verdict rather than any real
        parser key - proving the seam is generic, not that these two keys are real."""

        def claims(self, v):
            return bool(v.get("widget_topic") or v.get("widget_detail"))

        def missing(self, task):
            return tuple(s for s in task.slots if s.value is None)

        def fill(self, task, v):
            slots = list(task.slots)
            for i, s in enumerate(slots):
                if s.key == "topic" and v.get("widget_topic") and s.value is None:
                    slots[i] = replace(s, value=v["widget_topic"])
                if s.key == "detail" and v.get("widget_detail") and s.value is None:
                    slots[i] = replace(s, value=v["widget_detail"])
            return replace(task, slots=tuple(slots))

        def to_fetch(self, task):
            from app.services.chatbot.turn.plan import FetchSpec

            return FetchSpec(domain="widget", entities=[], filters={}, date_window=None)

        def question(self, task):
            return "widget question"

    original = dict(TASK_KINDS)
    TASK_KINDS["widget"] = _WidgetTask()
    try:
        policy = build_policy()
        task = Task(
            kind="widget",
            domain="widget",
            status="open",
            opened_at_turn=1,
            touched_at_turn=1,
            slots=(Slot(key="topic", label="Topic", value=None), Slot(key="detail", label="Detail", value=None)),
        )
        focus = Focus(tasks=(task,))

        # opens + fills one slot
        state2, _plan = apply(_state(focus), verdict(widget_topic="colour"), policy)
        widget = _task_of_kind(state2.focus, "widget")
        assert _slot_values(widget) == {"topic": "colour", "detail": None}

        # parks on an unrelated detour
        state3, _plan = apply(
            state2, verdict(domain_hint="promotion", entities=[entity("X", hint="product")]), policy
        )
        widget = _task_of_kind(state3.focus, "widget")
        assert widget.status == "parked"
        assert _slot_values(widget) == {"topic": "colour", "detail": None}

        # fills from a later turn
        state4, _plan = apply(state3, verdict(widget_detail="matte"), policy)
        widget = _task_of_kind(state4.focus, "widget")
        assert _slot_values(widget) == {"topic": "colour", "detail": "matte"}

        # closes on a topic_reset aimed at its own domain
        state5, _plan = apply(
            state4, verdict(topic_reset=True, domain_hint="widget", entities=[]), policy
        )
        assert not any(t.kind == "widget" for t in state5.focus.tasks), state5.focus.tasks
    finally:
        TASK_KINDS.clear()
        TASK_KINDS.update(original)


# --------------------------------------------------------------------------- #
# AC-1779: two tasks at once (D24)
# --------------------------------------------------------------------------- #


def test_apply_two_tasks_a_claimed_value_fills_only_the_claiming_task():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    stock = _stock_task(slots=[("uuid-c", "C", None), ("uuid-d", "D", None)])
    idea = _ideation_task()
    focus = Focus(tasks=(stock, idea))
    v = verdict(entities=[entity("C", hint="product", quantity=110)])

    state2, _plan = apply(_state(focus), v, build_policy())

    assert _slot_values(_task_of_kind(state2.focus, "stock_qty")) == {"uuid-c": 110, "uuid-d": None}
    assert _task_of_kind(state2.focus, "ideation").status == "open"


def test_apply_two_tasks_domain_hint_ideate_runs_only_ideation():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    stock = _stock_task(slots=[("uuid-c", "C", None), ("uuid-d", "D", None)])
    idea = _ideation_task()
    focus = Focus(tasks=(stock, idea))
    v = verdict(domain_hint="ideate", entities=[])

    state2, _plan = apply(_state(focus), v, build_policy())

    assert _slot_values(_task_of_kind(state2.focus, "stock_qty")) == {"uuid-c": None, "uuid-d": None}
    assert "ideate" in state2.focus.domains or state2.focus.domains == ["ideate"]


def test_apply_two_tasks_ambiguous_bare_number_arms_a_task_pick_roster():
    """D24(b): neither task's kind explicitly claims a bare, undirected number while
    both are open - the bot asks which task it is for through `pending.kind ==
    "task_pick"`, options = the two open tasks by label, and NEITHER task changes yet."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    stock = _stock_task(slots=[("uuid-c", "C", None), ("uuid-d", "D", None)])
    idea = _ideation_task()
    focus = Focus(tasks=(stock, idea))
    v = verdict(demand_qty=110, entities=[], reference_positions=[])

    state2, plan = apply(_state(focus), v, build_policy())

    assert _slot_values(_task_of_kind(state2.focus, "stock_qty")) == {"uuid-c": None, "uuid-d": None}
    assert _task_of_kind(state2.focus, "ideation").status == "open"
    pending = state2.pending or (plan.ask if plan else None)
    assert pending is not None, "an ambiguous claim over two open tasks must arm a pending"
    assert pending.kind == "task_pick", pending.kind
    assert len(pending.options) == 2, pending.options


def test_apply_two_tasks_naming_the_stock_domain_reasks_only_the_stock_task():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    stock = _stock_task(slots=[("uuid-c", "C", None), ("uuid-d", "D", None)])
    idea = _ideation_task()
    focus = Focus(tasks=(stock, idea))
    v = verdict(domain_hint="inventory", intent_hint="check_stock", entities=[])

    state2, _plan = apply(_state(focus), v, build_policy())

    reasked = _task_of_kind(state2.focus, "stock_qty")
    assert reasked.status == "open"
    assert _slot_values(reasked) == {"uuid-c": None, "uuid-d": None}
    assert _task_of_kind(state2.focus, "ideation").status == "open", (
        "naming the stock domain must not touch the ideation task"
    )


def test_apply_task_pick_answered_by_position_applies_the_carried_value_to_the_stock_task():
    """The follow-up half of D24(b): a `task_pick` roster already open (its payload
    carries the value that was ambiguous), answered by position 1 ("stock check"),
    applies that value to the stock task's one remaining missing slot."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.pending import ask as pending_ask
    from app.services.chatbot.turn.state import Focus

    stock = _stock_task(slots=[("uuid-c", "C", None)])
    idea = _ideation_task()
    focus = Focus(tasks=(stock, idea))
    tie = pending_ask(
        "task_pick",
        [
            {"position": 1, "label": "stock check", "entity_type": "task", "payload": {"task_kind": "stock_qty"}},
            {"position": 2, "label": "idea", "entity_type": "task", "payload": {"task_kind": "ideation"}},
        ],
        payload={"value": 110},
    )

    state2, _plan = apply(_state(focus, pending=tie), verdict(reference_positions=[1]), build_policy())

    assert state2.pending is None, "the tie is resolved, not left open"
    assert _slot_values(_task_of_kind(state2.focus, "stock_qty")) == {"uuid-c": 110}


# --------------------------------------------------------------------------- #
# AC-1786: ideation task closes on a topic_reset aimed at ideate; the kind's own
# tool-status classifier (see module docstring for why the "tool's own word" half is
# tested at this narrower grain rather than through a guessed apply() call shape)
# --------------------------------------------------------------------------- #


def test_apply_ideation_task_closes_on_topic_reset_aimed_at_ideate():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    idea = _ideation_task()
    focus = Focus(tasks=(idea,))
    v = verdict(topic_reset=True, domain_hint="ideate", entities=[])

    state2, _plan = apply(_state(focus), v, build_policy())

    assert state2.focus.tasks == ()


def test_ideation_task_kind_closes_on_the_tools_complete_status_only():
    from app.services.chatbot.turn.task import TASK_KINDS

    ideation_kind = TASK_KINDS["ideation"]
    assert ideation_kind.closes_on_tool_status("complete") is True
    assert ideation_kind.closes_on_tool_status("in_progress") is False
    assert ideation_kind.closes_on_tool_status("error") is False
