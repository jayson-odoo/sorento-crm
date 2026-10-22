"""CHAT-PICK-QTY-STATE release gate (#1829), G1 (contacts 28 and 30): a bare number over the open
quantities question fills the EMPTY line and never re-fills a filled one.

Stored: an open stock check, line 1 filled (10), line 2 owed, nothing else stored. The open
question the parser reads: {"kind": "quantities", "items": [{"position": 1, ..., "qty": 10},
{"position": 2, ..., "qty": null}], "owed": [2]}. The dealer sends "1"; v63 read it (live, 6 runs)
as a pick of position 1 (5 of 6) or as a fill of line 2 (1 of 6).

Crew rule: with one owed line the number is that line's quantity (main 552858f168's result);
with several owed lines it is what main does (each owed line takes it, the D13 / F2 ruling).
An explicit revision of a filled line ("make line 1 5": a fill naming position 1) still
re-fills it. Both paths (the state path with the pick op, or `answer` for a fill). Synthetic
codes only; the second code is a prefix of the first, as in the contact's own pair.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.services.chatbot.turn import chat_state
from app.services.chatbot.turn import question as question_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.state import Focus

from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict

DOMAINS = ["inventory", "incoming", "order", "sales", "product_attachment", "promotion"]
KINDS = ["product", "customer", "brand", "promotion", "attachment", "order"]
GATES = pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])

TWO_LINES = [("ZZTX605-RL-SOFT", 10), ("ZZTX605-RL", None)]
FOUR_LINES = [("ZZTA201", 10), ("ZZTA202", None), ("ZZTA203", None), ("ZZTA204", None)]


def _session(lines, gate: bool):
    task = ht.stock_task(lines, status="open", opened_at_turn=3, touched_at_turn=4)
    rows = [
        {"position": i, "label": c, "code": c, "uuid": ht.uuid_of(c), "entity_type": "product", "shown_at_turn": 4}
        for i, (c, _q) in enumerate(lines, 1)
    ]
    focus = Focus(products=ht.product_rows(*[c for c, _q in lines]), domains=["inventory"], tasks=(task,),
                  last_list=rows if gate else None)
    return replace(ht.state(focus, turn_no=5), state_path=gate)


def _answer(mode, *, picked=(), items=()):
    return {"mode": mode, "picked": list(picked), "items": list(items), "qty_for_all": None}


def _pick_one(gate: bool):
    """v63's read of "1", 5 runs of 6."""
    v = verdict(domain_hint="inventory", intent_hint="check_stock", demand_qty=None, reference_positions=[1],
                entities=[], topic_reset=False, open_question_answer=_answer("pick", picked=[1]))
    if gate:
        v["state_changes"] = [{"op": "pick", "axis": None, "position": 1}]
    return v


def _fill(gate: bool, position: int, code, qty: int, demand_qty=None):
    v = verdict(domain_hint="inventory", intent_hint="check_stock", demand_qty=demand_qty, reference_positions=[],
                entities=[], topic_reset=False,
                open_question_answer=_answer("fill", items=[{"position": position, "code": code, "qty": qty}]))
    if gate:
        v["state_changes"] = [{"op": "answer", "axis": None, "position": None}]
    return v


def _turn(state, v):
    if v.get("state_changes") is not None:
        applied = chat_state.apply_changes(
            state, v, open_question=question_mod.open_question(state.pending, state.focus.tasks),
            domains=DOMAINS, kinds=KINDS, brands=[], positions_read_elsewhere=False,
        )
        state, v = applied.state, applied.verdict
    return apply(state, v, build_policy())


def _slots(state):
    (task,) = [t for t in state.focus.tasks if t.kind == "stock_qty"]
    return [(slot.label, slot.value) for slot in task.slots]


def _asked(plan):
    """What the stock fetch asks about: {code: requested quantity}."""
    out = {}
    for spec in plan.fetch:
        wanted = spec.filters.get("requested_quantities") or {}
        for e in spec.entities:
            out[e.get("canonical_code")] = wanted.get(str(e.get("uuid")))
    return out


@GATES
def test_a_bare_one_read_as_a_pick_fills_the_one_owed_line(gate):
    new_state, plan = _turn(_session(TWO_LINES, gate), _pick_one(gate))
    assert _slots(new_state) == [("ZZTX605-RL-SOFT", 10), ("ZZTX605-RL", 1)], _slots(new_state)
    assert _asked(plan) == {"ZZTX605-RL": 1}, (_asked(plan), plan.trace.rules_fired)


@GATES
def test_a_bare_one_read_as_a_fill_of_line_two_fills_the_one_owed_line(gate):
    new_state, plan = _turn(_session(TWO_LINES, gate), _fill(gate, 2, "ZZTX605-RL", 1, demand_qty=1))
    assert _slots(new_state) == [("ZZTX605-RL-SOFT", 10), ("ZZTX605-RL", 1)], _slots(new_state)
    assert _asked(plan) == {"ZZTX605-RL": 1}, (_asked(plan), plan.trace.rules_fired)


@GATES
def test_a_bare_one_over_several_owed_lines_fills_each_owed_line_as_main_does(gate):
    """Main 552858f168 (measured): every owed line takes the number; the filled line stays."""
    new_state, plan = _turn(_session(FOUR_LINES, gate), _pick_one(gate))
    assert _slots(new_state) == [("ZZTA201", 10), ("ZZTA202", 1), ("ZZTA203", 1), ("ZZTA204", 1)], _slots(new_state)
    assert _asked(plan) == {"ZZTA202": 1, "ZZTA203": 1, "ZZTA204": 1}, (_asked(plan), plan.trace.rules_fired)


@GATES
def test_guard_an_explicit_revision_of_a_filled_line_still_re_fills_it(gate):
    """"make line 1 5": a fill naming position 1 revises it; the owed line stays owed."""
    new_state, plan = _turn(_session(TWO_LINES, gate), _fill(gate, 1, None, 5))
    assert _slots(new_state) == [("ZZTX605-RL-SOFT", 5), ("ZZTX605-RL", None)], _slots(new_state)
    assert _asked(plan) == {"ZZTX605-RL-SOFT": 5}, (_asked(plan), plan.trace.rules_fired)
