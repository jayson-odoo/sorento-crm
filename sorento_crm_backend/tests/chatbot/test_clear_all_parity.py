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
