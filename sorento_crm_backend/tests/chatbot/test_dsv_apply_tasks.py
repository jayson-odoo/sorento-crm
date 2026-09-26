"""Dealer stock verdict - S3, the apply-level task lifecycle: open/fill/park/resume/
close (stock_qty only). Ported from PR #1118 (feat/chatbot-dealer-stock-verdict, not
merged, owner ruling 24 Sep 2026), branch head 86d88b3a, for chatbot-stock-ask-v2 S3
(PLAN-chatbot-stock-ask-v2-24sep.md, ruling R1: "keep #1118's per-product quantity
collection (Focus.tasks, StockQtyTask)").

UAC "The open task on the focus (D21 to D23)" + rulings D13, D15, D16, D21 to D23. PLAN
"The engine (S3)" seam 3 (`turn/task.py`) and its lifecycle bullet list.

Style: hand-built `State`/verdict/`policy` through `apply()`, the same shape
`test_rearch_s2_focus_rules.py` and `test_rearch_s2_pending_one_object.py` already use
(`tests/chatbot/_turn_helpers.py::build_policy`/`verdict`).

SCOPE CUT from #1118 (R1, PRINCIPLES.md "simplest thing that works"): #1118's own file
also carried an `IdeationTask` kind and a `task_pick` tie between two open task kinds
(D24(b)) - every test case that exercised either (`test_apply_two_tasks_*`, the
`task_pick_answered` test, the two `ideation`-closing tests) is dropped here, not
ported: ideation already has its own independent mechanism on main
(`app/services/chatbot/lanes/ideate.py`, `session_state.py`) that does not need this
generic Task wrapper, and a tie between two kinds is machinery for a problem that
cannot occur while `TASK_KINDS` has one entry. The kept tests below are exactly the
ones that exercise the stock_qty lifecycle alone: claim a quantity, fill, park on an
unrelated topic switch, resume, close. `test_task_kind_protocol_second_kind_drives_
same_seams` is kept (adapted) to prove the seam stays generic for a THIRD kind with no
engine change, without depending on the retired `ideation` entry.
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


def test_apply_stock_qty_bare_number_two_missing_applies_to_each():
    """Owner ruling 26 Sep 2026 (hand test F2, "okay"), superseding #1118's "belongs to
    neither": one bare number after a question about several products applies to each
    product still owed. A (already 5) keeps its own quantity."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(
        slots=[("uuid-a", "A", 5), ("uuid-c", "C", None), ("uuid-d", "D", None)]
    )
    focus = Focus(tasks=(task,))
    v = verdict(demand_qty=110, entities=[])

    state2, _plan = apply(_state(focus), v, build_policy())

    stock = _task_of_kind(state2.focus, "stock_qty")
    assert _slot_values(stock) == {"uuid-a": 5, "uuid-c": 110, "uuid-d": 110}


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


def test_task_kind_protocol_third_kind_drives_same_seams():
    """Adapted from #1118's own `test_task_kind_protocol_second_kind_drives_same_
    seams`: proves the seam is generic (no per-kind arm anywhere else) without
    depending on the retired `ideation` registry entry - `TASK_KINDS` carries only
    `stock_qty` after the R1 scope cut, and a throwaway `widget` kind is registered
    and torn down around the assertions."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus
    from app.services.chatbot.turn.task import TASK_KINDS, Slot, Task

    assert set(TASK_KINDS) == {"stock_qty"}, (
        "R1 scope cut: TASK_KINDS carries only stock_qty, no IdeationTask"
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
