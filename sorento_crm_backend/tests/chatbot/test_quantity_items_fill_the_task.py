"""CHAT-PICK-QTY-STATE bug 5: the parser's item quantities answer the quantity question whatever
the answer mode says.

Live shape (v63, old path): the bot asked "How many units of C9109A?" (open stock task, slot
null, no stored pending). The dealer sent `2`; the parser answered open_question_answer
{mode pick, items [{qty 2, code C9109A, position 1}], picked [1]}. `_open_question_answer` only
read fill / all / done / cancel, so the quantity was dropped and the same question came back,
every time. The same items with mode fill filled the slot.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from app.services.chatbot.turn import chat_state
from app.services.chatbot.turn import pending as turn_pending
from app.services.chatbot.turn import question as question_mod
from app.services.chatbot.turn import task as task_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.state import Focus

from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict

CODE = "C9109A"
ASKED = f"How many units of {CODE}?"
DOMAINS = ["inventory", "incoming", "order", "sales", "product_attachment", "promotion"]
KINDS = ["product", "customer", "brand", "promotion", "attachment", "order"]
PATHS = pytest.mark.parametrize(
    "gate, ops",
    [(False, None), (True, []), (True, [{"op": "pick", "axis": None, "position": 1}])],
    ids=["old_path", "state_path_no_ops", "state_path_pick_op"],
)


def _state(gate: bool):
    task = ht.stock_task([(CODE, None)], opened_at_turn=4, touched_at_turn=4)
    focus = Focus(products=ht.product_rows(CODE), domains=["inventory"], tasks=(task,))
    return replace(ht.state(focus, turn_no=5), state_path=gate, state_gate=gate)


def _parse(mode: str, ops):
    v = verdict(
        domain_hint="inventory", intent_hint="check_stock", entity_op="reuse", entities=[],
        reference_positions=[],
        open_question_answer={
            "mode": mode, "picked": [1] if mode == "pick" else [],
            "items": [{"qty": 2, "code": CODE, "position": 1}], "qty_for_all": None,
        },
    )
    if ops is not None:
        v["state_changes"] = ops
    return v


def _turn(state, v):
    if v.get("state_changes") is not None:
        applied = chat_state.apply_changes(
            state, v, open_question=question_mod.open_question(state.pending, state.focus.tasks),
            domains=DOMAINS, kinds=KINDS, brands=[], positions_read_elsewhere=False,
        )
        state, v = applied.state, applied.verdict
    return apply(state, v, build_policy())


def _filled_with_two(new_state, plan):
    assert plan.trace.task_question != ASKED, "the quantity question was asked again"
    (task,) = [t for t in new_state.focus.tasks if t.kind == "stock_qty"]
    assert [(s.label, s.value) for s in task.slots] == [(CODE, 2)]
    (spec,) = ht.inventory_specs(plan)
    assert [row["canonical_code"] for row in spec.entities] == [CODE]
    assert list((spec.filters.get("requested_quantities") or {}).values()) == [2]


@PATHS
def test_pick_mode_items_with_a_quantity_fill_the_slot(gate, ops):
    _filled_with_two(*_turn(_state(gate), _parse("pick", ops if gate else None)))


@PATHS
def test_guard_fill_mode_with_the_same_items_fills(gate, ops):
    _filled_with_two(*_turn(_state(gate), _parse("fill", ops if gate else None)))


@PATHS
def test_guard_cancel_mode_with_items_is_not_a_fill(gate, ops):
    new_state, plan = _turn(_state(gate), _parse("cancel", ops if gate else None))
    assert not any(
        s.value == 2 for t in new_state.focus.tasks for s in t.slots
    ), "a cancel filled the slot"
    assert not [spec for spec in ht.inventory_specs(plan) if spec.filters.get("requested_quantities")]


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_guard_pick_over_a_did_you_mean_with_no_quantity_still_picks_the_option(gate):
    options = [
        {
            "position": i, "label": c, "code": c, "entity_type": "product",
            "uuid": ht.uuid_of(c), "uuids": [ht.uuid_of(c)], "payload": {},
        }
        for i, c in enumerate(["CL8109A", CODE, "CB3109A"], 1)
    ]
    pending = turn_pending.ask(
        "product_pick", options, asked_at_turn=4,
        payload={"domain": "inventory", "domains": ["inventory"], "stock_pick": True,
                 "did_you_mean": True, "typed": "CLB109A", "stock_qty": None},
    )
    state = replace(
        ht.state(Focus(domains=["inventory"]), pending=pending, turn_no=5), state_path=gate, state_gate=gate
    )
    v = verdict(
        domain_hint="inventory", intent_hint="check_stock", entities=[], reference_positions=[2],
        open_question_answer={"mode": "pick", "picked": [2], "items": [], "qty_for_all": None},
    )
    if gate:
        v["state_changes"] = [{"op": "pick", "axis": None, "position": 2}]
    _new_state, plan = _turn(state, v)
    codes = [row["canonical_code"] for spec in ht.inventory_specs(plan) for row in spec.entities]
    assert codes == [CODE], codes
