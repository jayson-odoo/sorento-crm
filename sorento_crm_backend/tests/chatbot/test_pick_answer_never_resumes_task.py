"""CHAT-PICK-QTY-STATE bug 1: a pick answer to an open did-you-mean answers the picked
product; it never resumes an older stock_qty task of the same domain (open or parked).

Prod shape: the contact has an older stock_qty task with every slot null. The bot asked
"Couldn't find CLB109A. Did you mean: 1. CL8109A 2. C9109A 3. CB3109A"; the dealer sent `1`.
The parser answered correctly (open_question_answer mode pick, picked [1], domain stock),
yet the task's own "How many units for each?" came back with nothing fetched. Both the old
path (`state_path` off) and the state path (on) are covered. Only the parser is stubbed.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.turn import chat_state
from app.services.chatbot.turn import pending as turn_pending
from app.services.chatbot.turn import question as question_mod
from app.services.chatbot.turn import task as task_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.state import Focus

from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict

OLDER = ["SRTBF101", "SRTBF102", "SRTBF103"]
OFFERED = ["CL8109A", "C9109A", "CB3109A"]


def _did_you_mean():
    return turn_pending.ask(
        "product_pick",
        [
            {
                "position": i + 1,
                "label": code,
                "code": code,
                "uuid": ht.uuid_of(code),
                "entity_type": "product",
            }
            for i, code in enumerate(OFFERED)
        ],
        asked_at_turn=4,
        payload={
            "domain": "inventory",
            "domains": ["inventory"],
            "stock_pick": True,
            "did_you_mean": True,
            "typed": "CLB109A",
            "count": len(OFFERED),
            "stock_qty": None,
        },
    )


def _state(status: str, gate: bool):
    from dataclasses import replace

    task = ht.stock_task([(code, None) for code in OLDER], status=status)
    focus = Focus(products=ht.product_rows(*OLDER), domains=["inventory"], tasks=(task,))
    return replace(ht.state(focus, pending=_did_you_mean(), turn_no=5), state_path=gate)


DOMAINS = ["inventory", "incoming", "order", "sales", "product_attachment", "promotion"]
KINDS = ["product", "customer", "brand", "promotion", "attachment", "order"]


def _run(state, v, ops):
    """The engine's order on the state path: the applier reads the parser's `state_changes`
    (and puts the turn under the state gate), then the turn APPLY. Off the path, APPLY alone."""
    if getattr(state, "state_path", False):
        v = {**v, "state_changes": ops}
        applied = chat_state.apply_changes(
            state, v, open_question=question_mod.open_question(state.pending, state.focus.tasks),
            domains=DOMAINS, kinds=KINDS, brands=[], positions_read_elsewhere=False,
        )
        assert applied.state.state_gate, "the state path was not entered"
        state, v = applied.state, applied.verdict
    return apply(state, v, build_policy())


def _pick_verdict(form: str):
    answer = {"mode": "pick", "picked": [], "items": [], "qty_for_all": None}
    entities = []
    if form == "position":
        answer["picked"] = [1]
    else:
        answer["items"] = [{"position": None, "code": "cl8109a", "qty": None}]
        entities = [ht.asked("cl8109a", canonical_code="CL8109A")]
    return verdict(
        domain_hint="inventory",
        intent_hint="check_stock",
        entities=entities,
        open_question_answer=answer,
    )


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
@pytest.mark.parametrize("status", [task_mod.OPEN, task_mod.PARKED])
@pytest.mark.parametrize("form", ["position", "code"])
def test_pick_answer_answers_the_pick_and_leaves_the_older_task(form, status, gate):
    state = _state(status, gate)
    new_state, plan = _run(state, _pick_verdict(form), [{"op": "pick", "axis": None, "position": 1}])

    assert plan.trace.task_question is None, "the older task's question was returned"
    assert "task_resumed_stock_qty" not in plan.trace.rules_fired
    specs = ht.inventory_specs(plan)
    codes = [row["canonical_code"] for spec in specs for row in spec.entities]
    assert codes == ["CL8109A"], f"the pick was not answered: fetch={codes}"
    (older,) = [t for t in new_state.focus.tasks if t.kind == "stock_qty"]
    assert older.status == status
    assert [slot.label for slot in older.slots] == OLDER
    assert [slot.value for slot in older.slots] == [None, None, None]


def _one_option_pending():
    return turn_pending.ask(
        "product_pick",
        [{
            "position": 1, "label": "ELP3754", "code": "ELP3754", "uuid": ht.uuid_of("ELP3754"),
            "entity_type": "product",
        }],
        asked_at_turn=4,
        payload={
            "domain": "inventory", "domains": ["inventory"], "stock_pick": True,
            "did_you_mean": True, "typed": "ELP3753", "count": 1, "stock_qty": None,
        },
    )


def _parked_state(gate: bool):
    from dataclasses import replace

    task = ht.stock_task([(code, None) for code in OLDER], status=task_mod.PARKED)
    focus = Focus(products=ht.product_rows(*OLDER), domains=["inventory"], tasks=(task,))
    return replace(ht.state(focus, pending=_one_option_pending(), turn_no=5), state_path=gate)


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_a_yes_to_a_one_option_did_you_mean_answers_it_and_leaves_the_parked_task(gate):
    v = verdict(
        domain_hint="inventory", intent_hint="check_stock", entities=[], is_affirmative=True,
        open_question_answer={"mode": "yes", "picked": [], "items": [], "qty_for_all": None},
    )
    new_state, plan = _run(_parked_state(gate), v, [{"op": "answer", "axis": None, "position": None}])
    assert plan.trace.task_question is None, "the older task's question was returned"
    assert "task_resumed_stock_qty" not in plan.trace.rules_fired
    codes = [row["canonical_code"] for spec in ht.inventory_specs(plan) for row in spec.entities]
    assert codes == ["ELP3754"], codes
    (older,) = [t for t in new_state.focus.tasks if t.kind == "stock_qty"]
    assert older.status == task_mod.PARKED


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_guard_an_unfit_pick_applies_nothing_and_still_resumes_as_on_main(gate):
    v = verdict(
        domain_hint="inventory", intent_hint="check_stock", entities=[],
        open_question_answer={
            "mode": "pick", "picked": [], "items": [{"position": None, "code": "ZZ9999", "qty": None}],
            "qty_for_all": None,
        },
    )
    _new_state, plan = _run(_parked_state(gate), v, [{"op": "answer", "axis": None, "position": None}])
    assert "task_resumed_stock_qty" in plan.trace.rules_fired


# --- a declined did-you-mean drops its unresolved token ----------------------------------------------


def _miss_row(raw="Clb109a"):
    return {"raw": raw, "hint": "product", "canonical_code": raw.upper(), "current_message": False, "confident": True}


def _declined_state(gate: bool, *, resolved: bool = False):
    from dataclasses import replace

    products = [_miss_row()] + (ht.product_rows("SRTBF101") if resolved else [])
    focus = Focus(products=products, domains=["inventory"])
    return replace(ht.state(focus, pending=_did_you_mean(), turn_no=5), state_path=gate)


def _decline_verdict():
    return verdict(
        domain_hint="inventory", intent_hint="check_stock", entities=[], is_affirmative=False,
        entity_op="clear", broaden_axis="all",
        open_question_answer={"mode": "cancel", "picked": [], "items": [], "qty_for_all": None},
    )


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_a_declined_did_you_mean_drops_its_unresolved_token_and_a_bare_two_does_not_reshow_it(gate):
    state, plan = _run(
        _declined_state(gate), _decline_verdict(), [{"op": "close_question", "axis": None, "position": None}]
    )
    assert "stock_pick_declined" in plan.trace.rules_fired
    assert not [p for p in state.focus.products if not p.get("uuid")], state.focus.products
    # the next turn: a bare `2`, nothing pending
    v = verdict(domain_hint="inventory", intent_hint="check_stock", entities=[], reference_positions=[2],
                entity_op="reuse")
    _state2, plan2 = _run(state, v, [{"op": "pick", "axis": None, "position": 2}])
    codes = [row.get("raw") for spec in plan2.fetch for row in spec.entities]
    assert "Clb109a" not in codes, codes
    assert plan2.trace.task_question != "Please refer to your salesman."


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_guard_a_declined_did_you_mean_keeps_a_resolved_product_the_ask_also_named(gate):
    state, _plan = _run(
        _declined_state(gate, resolved=True), _decline_verdict(),
        [{"op": "close_question", "axis": None, "position": None}],
    )
    assert [p.get("canonical_code") for p in state.focus.products] == ["SRTBF101"], state.focus.products
