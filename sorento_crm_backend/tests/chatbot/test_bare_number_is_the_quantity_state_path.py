"""CHAT-PICK-QTY-STATE bug 2: a bare number answering "How many units of X?" is the
quantity on the state path too, not a pick on an older did-you-mean list.

Live shape (v92 replay): the held stock check is CL8109A, still owed its quantity (`open
question` kind quantities, `pending task: the open question`), and a did-you-mean listing
CL8109A / C9109A / CB3109A was shown four turns earlier (`last list`). The dealer sends `2`.
The parser (v63 and v92) answers open_question_answer {pick, [2]}, reference_positions [2],
entity_op reuse, entities []; v92 adds state_changes [pick 2]. The old path turns it into
CL8109A x 2 (`_bare_position_is_the_quantity`); the state path picked C9109A off the stale
list and dropped the CL8109A task. A dealer who QUOTES the did-you-mean message points at that
list, so the same `2` still picks C9109A (guard).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from app.services.chatbot.turn import chat_state
from app.services.chatbot.turn import question as question_mod
from app.services.chatbot.turn import task as task_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.state import Focus

from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict

LISTED = ["CL8109A", "C9109A", "CB3109A"]
HELD = "CL8109A"
DOMAINS = ["inventory", "incoming", "order", "sales", "product_attachment", "promotion"]
KINDS = ["product", "customer", "brand", "promotion", "attachment", "order"]
GATES = pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])


def _rows(shown_at: int = 1) -> list[dict[str, Any]]:
    return [
        {
            "position": i, "label": code, "code": code, "uuid": ht.uuid_of(code),
            "entity_type": "product", "shown_at_turn": shown_at,
        }
        for i, code in enumerate(LISTED, 1)
    ]


def _state(gate: bool, *, last_list: bool = True, quoted: int | None = None):
    task = ht.stock_task([(HELD, None)], opened_at_turn=4, touched_at_turn=4)
    focus = Focus(
        products=ht.product_rows(HELD), domains=["inventory"], tasks=(task,),
        last_list=_rows() if last_list else None,
    )
    state = ht.state(focus, turn_no=5)
    return replace(state, state_path=gate, state_gate=gate, quoted_turn_no=quoted)


def _turn(state, v: dict[str, Any]):
    if v.get("state_changes") is not None:
        applied = chat_state.apply_changes(
            state, v, open_question=question_mod.open_question(state.pending, state.focus.tasks),
            domains=DOMAINS, kinds=KINDS, brands=[], positions_read_elsewhere=False,
        )
        # A rejected change set still runs the turn on the input state, as the engine does.
        state, v = applied.state, applied.verdict
    return apply(state, v, build_policy())


def _two(gate: bool):
    """The parse of `2` on both versions, with v92's state op on the state path."""
    v = verdict(
        domain_hint="inventory", entity_op="reuse", entities=[], reference_positions=[2],
        open_question_answer={"mode": "pick", "picked": [2], "items": [], "qty_for_all": None},
    )
    if gate:
        v["state_changes"] = [{"op": "pick", "axis": None, "position": 2}]
    return v


def _two_pcs(gate: bool):
    v = verdict(
        domain_hint="inventory", intent_hint="check_stock", entity_op="reuse", entities=[],
        demand_qty=2, open_question_answer={"mode": None, "picked": [], "items": [], "qty_for_all": None},
    )
    if gate:
        v["state_changes"] = [{"op": "set", "axis": "quantity", "position": None}]
    return v


def _is_two_of_the_held_product(new_state, plan):
    codes = [row["canonical_code"] for spec in ht.inventory_specs(plan) for row in spec.entities]
    assert "C9109A" not in codes, f"the stale list row was picked: {codes}"
    assert codes == [HELD], f"fetch is {codes}"
    quantities = [
        q for spec in ht.inventory_specs(plan)
        for q in (spec.filters.get("requested_quantities") or {}).values()
    ]
    tasks = [t for t in new_state.focus.tasks or () if t.kind == "stock_qty"]
    assert tasks, "the CL8109A task was dropped"
    slot_values = [s.value for t in tasks for s in t.slots if s.label == HELD]
    assert quantities == [2] or slot_values == [2], (quantities, slot_values)
    assert plan.trace.task_question is None, "asked the quantity again"


@GATES
def test_a_bare_number_over_the_quantity_question_is_the_quantity(gate):
    new_state, plan = _turn(_state(gate), _two(gate))
    _is_two_of_the_held_product(new_state, plan)


@GATES
def test_the_same_with_no_last_list_in_the_state(gate):
    new_state, plan = _turn(_state(gate, last_list=False), _two(gate))
    _is_two_of_the_held_product(new_state, plan)


@GATES
def test_two_pcs_over_the_quantity_question_is_the_quantity(gate):
    new_state, plan = _turn(_state(gate), _two_pcs(gate))
    _is_two_of_the_held_product(new_state, plan)


def test_guard_quoting_the_did_you_mean_message_picks_its_row():
    state = _state(True, quoted=1)
    new_state, plan = _turn(state, _two(True))
    codes = [row["canonical_code"] for spec in ht.inventory_specs(plan) for row in spec.entities]
    assert codes == ["C9109A"], codes
