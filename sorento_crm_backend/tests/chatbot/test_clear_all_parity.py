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
    return replace(ht.state(focus, turn_no=5), state_path=gate, state_gate=gate)


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
