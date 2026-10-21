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

from app.services.chatbot.turn import pending as turn_pending
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
    new_state, plan = apply(state, _pick_verdict(form), build_policy())

    assert plan.trace.task_question is None, "the older task's question was returned"
    assert "task_resumed_stock_qty" not in plan.trace.rules_fired
    specs = ht.inventory_specs(plan)
    codes = [row["canonical_code"] for spec in specs for row in spec.entities]
    assert codes == ["CL8109A"], f"the pick was not answered: fetch={codes}"
    (older,) = [t for t in new_state.focus.tasks if t.kind == "stock_qty"]
    assert older.status == status
    assert [slot.label for slot in older.slots] == OLDER
    assert [slot.value for slot in older.slots] == [None, None, None]
