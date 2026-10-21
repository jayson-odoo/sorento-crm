"""CHAT-PICK-QTY-STATE bug 3: "clear all" on the state path resets what the old path resets.

Live shape (v63 and v92 replay): the contact holds an older three-line stock_qty task (every
slot null), three held products and a did-you-mean list shown earlier. The dealer sends "clear
all". Old path parse (v63): open_question_answer cancel, entity_op clear, broaden_axis all,
topic_reset true, no state_changes; the topic reset wipes tasks and the list. State path parse C
(v92): state_changes [clear product, close_question] with the same topic_reset / entity_op /
broaden_axis; tasks went but the stored last list stayed, so a later bare number picked off it.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from app.services.chatbot.turn import chat_state
from app.services.chatbot.turn import question as question_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.state import Focus

from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict

OLDER = ["SRTBF101", "SRTBF102", "SRTBF103"]
LISTED = ["CL8109A", "C9109A", "CB3109A"]
DOMAINS = ["inventory", "incoming", "order", "sales", "product_attachment", "promotion"]
KINDS = ["product", "customer", "brand", "promotion", "attachment", "order"]
GATES = pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])


def _state(gate: bool):
    task = ht.stock_task([(code, None) for code in OLDER], opened_at_turn=2, touched_at_turn=2)
    rows = [
        {"position": i, "label": c, "code": c, "uuid": ht.uuid_of(c), "entity_type": "product", "shown_at_turn": 1}
        for i, c in enumerate(LISTED, 1)
    ]
    focus = Focus(
        products=ht.product_rows(*OLDER), domains=["inventory"], tasks=(task,),
        last_list=rows if gate else None,
    )
    return replace(ht.state(focus, turn_no=5), state_path=gate)


def _clear_all(gate: bool, *, topic_reset: bool = True):
    v = verdict(
        domain_hint="inventory", entity_op="clear", broaden_axis="all", topic_reset=topic_reset, entities=[],
        open_question_answer={
            "mode": None if gate else "cancel", "picked": [], "items": [], "qty_for_all": None,
        },
    )
    if gate:
        v["state_changes"] = [
            {"op": "clear", "axis": "product", "position": None},
            {"op": "close_question", "axis": None, "position": None},
        ]
    return v


def _turn(state, v):
    if v.get("state_changes") is not None:
        applied = chat_state.apply_changes(
            state, v, open_question=question_mod.open_question(state.pending, state.focus.tasks),
            domains=DOMAINS, kinds=KINDS, brands=[], positions_read_elsewhere=False,
        )
        assert applied.state.state_gate, "the state path was not entered"
        state, v = applied.state, applied.verdict
    return apply(state, v, build_policy())


@GATES
def test_clear_all_leaves_no_task_no_list_no_question(gate):
    new_state, plan = _turn(_state(gate), _clear_all(gate))
    assert plan.trace.task_question is None, "the older task's question was returned"
    assert not new_state.focus.tasks, new_state.focus.tasks
    assert not new_state.focus.last_list, "the stored list survived the clear"
    assert new_state.pending is None
    assert question_mod.open_question(new_state.pending, new_state.focus.tasks) is None
    assert not ht.inventory_specs(plan)


def test_the_focus_diff_of_a_reset_that_drops_the_list_is_whole():
    """`turn_runtime.focus_diff` runs on every turn's before/after focus. The wire form leaves
    an empty `last_list` out, so a reset that drops a stored list must still diff (it raised
    KeyError: 'last_list' live) and the diff names the list as cleared."""
    from app.services.chatbot.turn_runtime import focus_diff

    state = _state(True)
    new_state, _plan = _turn(state, _clear_all(True))
    diff = focus_diff(state.focus, new_state.focus)
    assert "last_list" in diff
    assert diff["last_list"]["before"] and not diff["last_list"]["after"]


# --- a cancel answer resets on the state path as on the old path ----------------------------------
# Live v92 ("mula semula", "全部清除", "Restart"): state_changes [close_question], open_question_answer
# mode cancel, topic_reset false. The old path's cancel rule (`_open_question_answer` writes
# topic_reset true) is the reset; the state path must reach the same result.


def _did_you_mean_pending():
    from app.services.chatbot.turn import pending as turn_pending

    return turn_pending.ask(
        "product_pick",
        [
            {"position": i, "label": c, "code": c, "uuid": ht.uuid_of(c), "entity_type": "product",
             "uuids": [ht.uuid_of(c)], "payload": {}}
            for i, c in enumerate(LISTED, 1)
        ],
        asked_at_turn=4,
        payload={"domain": "inventory", "domains": ["inventory"], "stock_pick": True,
                 "did_you_mean": True, "typed": "CLB109A", "count": 3, "stock_qty": None},
    )


def _cancel_state(gate: bool, context: str):
    from app.services.chatbot.turn import task as task_mod

    status = task_mod.PARKED if context == "did_you_mean" else task_mod.OPEN
    task = ht.stock_task([(code, None) for code in OLDER], status=status, opened_at_turn=2, touched_at_turn=2)
    rows = [
        {"position": i, "label": c, "code": c, "uuid": ht.uuid_of(c), "entity_type": "product", "shown_at_turn": 4}
        for i, c in enumerate(LISTED, 1)
    ]
    focus = Focus(
        products=ht.product_rows(*OLDER), domains=["inventory"], tasks=(task,),
        last_list=rows if gate and context == "did_you_mean" else None,
    )
    pending = _did_you_mean_pending() if context == "did_you_mean" else None
    return replace(ht.state(focus, pending=pending, turn_no=5), state_path=gate)


def _cancel_parse(gate: bool):
    v = verdict(
        domain_hint="inventory", intent_hint="check_stock", entities=[], topic_reset=False,
        open_question_answer={"mode": "cancel", "picked": [], "items": [], "qty_for_all": None},
    )
    if gate:
        v["state_changes"] = [{"op": "close_question", "axis": None, "position": None}]
    return v


@GATES
@pytest.mark.parametrize("context", ["did_you_mean", "quantities"])
def test_a_cancel_answer_over_a_did_you_mean_or_quantities_resets_on_both_paths(gate, context):
    new_state, plan = _turn(_cancel_state(gate, context), _cancel_parse(gate))
    # A cancel over a did-you-mean is the decline of that question ("none of them"): the dealer is
    # referred to the salesman on BOTH paths. Over the quantities question it asks nothing.
    expected = "Please refer to your salesman." if context == "did_you_mean" else None
    assert plan.trace.task_question == expected, plan.trace.task_question
    assert not [t for t in new_state.focus.tasks if t.status == "open"], new_state.focus.tasks
    assert new_state.pending is None, new_state.pending
    assert not new_state.focus.last_list
    assert not ht.inventory_specs(plan)


# --- a topic reset wins over whatever the pending-answer branch returned -----------------------------
# Live v63: (a) a reset the pending branch calls "not an answer" left the old did-you-mean stored;
# (b) a reset read as a decline of an escalate-offer did-you-mean returned before the reset wipe.


def _miss_focus(tasks=()):
    miss = {"raw": "Clb109a", "hint": "product", "canonical_code": "CLB109A", "current_message": False,
            "confident": True}
    return Focus(products=[miss], domains=["inventory"], tasks=tasks)


def _reset_state(gate: bool, case: str):
    from app.services.chatbot.turn import pending as turn_pending

    pending = _did_you_mean_pending()
    if case == "offer_decline":
        pending = turn_pending.ask(
            "product_pick", list(pending.options), team="warehouse", asked_at_turn=4,
            payload={**pending.payload, "escalate_offered": True},
        )
    tasks = () if case == "offer_decline" else (
        ht.stock_task([(c, None) for c in OLDER], opened_at_turn=2, touched_at_turn=2),
    )
    return replace(ht.state(_miss_focus(tasks), pending=pending, turn_no=5), state_path=gate)


def _reset_parse(gate: bool, case: str, *, topic_reset: bool = True):
    declined = case == "offer_decline"
    v = verdict(
        domain_hint="inventory", intent_hint="check_stock", entities=[], topic_reset=topic_reset,
        is_affirmative=False if declined else None,
        open_question_answer={"mode": "cancel" if declined else None, "picked": [], "items": [], "qty_for_all": None},
    )
    if gate:
        v["state_changes"] = [{"op": "close_question", "axis": None, "position": None}]
    return v


@GATES
@pytest.mark.parametrize("case", ["not_an_answer", "offer_decline"])
def test_a_topic_reset_drops_the_stored_question_and_wipes_the_focus(gate, case):
    state, plan = _turn(_reset_state(gate, case), _reset_parse(gate, case))
    assert state.pending is None, state.pending
    assert not state.focus.products, state.focus.products
    # the next bare number picks nothing from the old did-you-mean
    v = verdict(domain_hint="inventory", intent_hint="check_stock", entities=[], reference_positions=[2],
                entity_op="reuse")
    if gate:
        v["state_changes"] = [{"op": "pick", "axis": None, "position": 2}]
    _state2, plan2 = _turn(state, v)
    codes = [row.get("canonical_code") for spec in plan2.fetch for row in spec.entities]
    assert "C9109A" not in codes and "CLB109A" not in codes, codes


@GATES
def test_guard_a_decline_without_a_topic_reset_keeps_todays_behaviour(gate):
    from app.services.chatbot.turn import pending as turn_pending

    state = replace(
        ht.state(_miss_focus(), pending=_did_you_mean_pending(), turn_no=5), state_path=gate
    )
    v = verdict(
        domain_hint="inventory", intent_hint="check_stock", entities=[], topic_reset=False, is_affirmative=False,
        open_question_answer={"mode": "no", "picked": [], "items": [], "qty_for_all": None},
    )
    if gate:
        v["state_changes"] = [{"op": "answer", "axis": None, "position": None}]
    new_state, plan = _turn(state, v)
    assert "stock_pick_declined" in plan.trace.rules_fired
    assert plan.trace.task_question == "Please refer to your salesman."
    assert not [p for p in new_state.focus.products if not p.get("uuid")]


# --- a new_subject that carries nothing is a reset (state path) --------------------------------------
# Live v92 ("mula semula"): state_changes [new_subject], topic_reset false, nothing else. The prompt's
# own mirror rule makes that a reset; the applier writes it, and the existing machinery runs.


def _one_slot_state(status: str = "open"):
    from app.services.chatbot.turn import task as task_mod

    task = ht.stock_task([("CL8109A", None)], status=status, opened_at_turn=3, touched_at_turn=3)
    rows = [
        {"position": i, "label": c, "code": c, "uuid": ht.uuid_of(c), "entity_type": "product", "shown_at_turn": 2}
        for i, c in enumerate(LISTED, 1)
    ]
    focus = Focus(products=ht.product_rows("CL8109A"), domains=["inventory"], tasks=(task,), last_list=rows)
    return replace(ht.state(focus, turn_no=5), state_path=True)


def _new_subject_parse(**over):
    base = dict(
        domain_hint=None, intent_hint=None, entities=[], entity_op="reuse", topic_reset=False,
        open_question_answer={"mode": None, "picked": [], "items": [], "qty_for_all": None},
        state_changes=[{"op": "new_subject", "axis": None, "position": None}],
    )
    base.update(over)
    return verdict(**base)


def test_a_new_subject_that_carries_nothing_resets_and_a_next_bare_number_resumes_nothing():
    state, plan = _turn(_one_slot_state(), _new_subject_parse())
    assert not [t for t in state.focus.tasks if t.status in ("open", "parked")], state.focus.tasks
    assert state.pending is None and not state.focus.last_list
    v = verdict(domain_hint="inventory", intent_hint="check_stock", entities=[], reference_positions=[2],
                entity_op="reuse")
    _state2, plan2 = _turn(state, v)
    assert plan2.trace.task_question is None, plan2.trace.task_question


def test_guard_a_new_subject_that_names_a_domain_is_not_a_reset_and_parks_the_task():
    state, _plan = _turn(_one_slot_state(), _new_subject_parse(domain_hint="promotion"))
    assert [t.status for t in state.focus.tasks] == ["parked"], state.focus.tasks


def test_guard_a_new_subject_with_a_product_of_its_own_is_not_a_reset():
    typed = {"raw": "ELP3754", "hint": "product", "canonical_code": "ELP3754", "current_message": True,
             "confident": True, "hint_confident": True}
    state, plan = _turn(
        _one_slot_state("parked"), _new_subject_parse(domain_hint="inventory", intent_hint="check_stock", entities=[typed])
    )
    assert "reset_on_topic" not in plan.trace.rules_fired
    codes = [row["canonical_code"] for spec in ht.inventory_specs(plan) for row in spec.entities]
    assert codes == ["ELP3754"], codes


# --- the reset wipe on an early-returning answer path -------------------------------------------------


def test_a_reset_on_an_early_returning_answer_path_wipes_the_focus():
    """Only the wipe decides: a did-you-mean cancelled with topic_reset true and a domain of its own
    returns from `_answer_pending` before `_focus_rules`; the held codes must still go."""
    task = ht.stock_task([(c, None) for c in ("SRTBF101", "SRTBF102")], opened_at_turn=2, touched_at_turn=2)
    focus = Focus(products=ht.product_rows("SRTBF101", "SRTBF102"), domains=["inventory"], tasks=(task,))
    state = replace(ht.state(focus, pending=_did_you_mean_pending(), turn_no=5), state_path=False)
    v = verdict(
        domain_hint="promotion", entities=[], topic_reset=True, is_affirmative=False,
        open_question_answer={"mode": "cancel", "picked": [], "items": [], "qty_for_all": None},
    )
    new_state, plan = apply(state, v, build_policy())
    assert "stock_pick_declined" in plan.trace.rules_fired
    assert new_state.focus.products == [], new_state.focus.products


def test_a_state_path_reset_on_an_early_return_drops_a_list_that_is_not_the_questions_options():
    rows = [
        {"position": i, "label": f"SRTWT{i}", "code": f"SRTWT{i}", "uuid": ht.uuid_of(f"SRTWT{i}"),
         "entity_type": "product", "shown_at_turn": 4}
        for i in range(1, 12)
    ]
    focus = Focus(products=[_miss_row()], domains=["inventory"], last_list=rows)
    state = replace(ht.state(focus, pending=_did_you_mean_pending(), turn_no=5), state_path=True)
    v = verdict(
        domain_hint="inventory", intent_hint="check_stock", entities=[], topic_reset=True, is_affirmative=False,
        open_question_answer={"mode": "cancel", "picked": [], "items": [], "qty_for_all": None},
        state_changes=[{"op": "close_question", "axis": None, "position": None}],
    )
    new_state, plan = _turn(state, v)
    assert "stock_pick_declined" in plan.trace.rules_fired
    assert not new_state.focus.last_list, new_state.focus.last_list
