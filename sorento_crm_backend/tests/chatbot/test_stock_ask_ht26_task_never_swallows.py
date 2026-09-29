"""Owner hand test 26 Sep 2026 (PR #1247), slice 4: an open task never swallows the
products a message names that the task does not hold.

T14 "ELP3754 10 and SRTKT1631SS 20" arrived over the one-slot ELP3754 task T13 left
open (the orchestrator's trace check: the state fed into T14 held an open stock_qty task
with one ELP3754 slot, value null, and T14 fired `task_filled_stock_qty` and
`task_drives_the_fetch`). The task's own fetch replaced the turn's, and SRTKT1631SS was
dropped. Now the task does not claim that turn: the ordinary fetch runs for both
products, each carrying its own quantity, and the reply's two R14 lines rebuild the task.
"""
from __future__ import annotations

from app.services.chatbot import turn_runtime
from app.services.chatbot.turn import task as task_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.state import Focus

from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict


def _t13_state():
    task = ht.stock_task([("ELP3754", None)], opened_at_turn=2206, touched_at_turn=2206)
    return ht.state(
        Focus(tasks=(task,), domains=["inventory"], products=ht.product_rows("ELP3754")),
        turn_no=2207,
    )


def _t14_verdict():
    return verdict(
        domain_hint="inventory",
        entities=[ht.asked("ELP3754", quantity=10), ht.asked("SRTKT1631SS", quantity=20)],
    )


def test_t14_fetches_both_products_and_the_task_does_not_drive_the_fetch():
    v = _t14_verdict()
    _state2, plan = apply(_t13_state(), v, build_policy())

    assert "task_drives_the_fetch" not in plan.trace.rules_fired
    assert "task_filled_stock_qty" not in plan.trace.rules_fired
    specs = ht.inventory_specs(plan)
    assert len(specs) == 1
    spec = specs[0]
    assert not spec.filters.get("task")
    codes = {str(e.get("canonical_code") or e.get("raw")).upper() for e in spec.entities}
    assert codes == {"ELP3754", "SRTKT1631SS"}


def test_t14_each_product_binds_its_own_quantity_at_the_fetch():
    v = _t14_verdict()
    _state2, plan = apply(_t13_state(), v, build_policy())
    spec = ht.inventory_specs(plan)[0]
    resolved = [
        {"uuid": ht.uuid_of("ELP3754"), "code": "ELP3754", "canonical_code": "ELP3754"},
        {"uuid": ht.uuid_of("SRTKT1631SS"), "code": "SRTKT1631SS", "canonical_code": "SRTKT1631SS"},
    ]
    out = turn_runtime._spec_quantities({"entities": v["entities"]}, spec, resolved)
    assert out["requested_quantities"] == {
        ht.uuid_of("ELP3754"): 10,
        ht.uuid_of("SRTKT1631SS"): 20,
    }


def test_t14_reply_with_two_answers_leaves_no_open_task():
    tasks = task_mod.tasks_after_reply(
        _t13_state().focus.tasks,
        ht.envelopes(
            ht.row("ELP3754", needs_quantity=False, requested_qty=10, branch="in_stock"),
            ht.row("SRTKT1631SS", needs_quantity=False, requested_qty=20, branch="no_incoming"),
        ),
        turn_no=2207,
    )
    assert not any(t.status == "open" for t in tasks)


def test_a_quantity_for_the_task_own_product_is_still_a_fill():
    state2, plan = apply(
        _t13_state(),
        verdict(entities=[ht.asked("ELP3754", quantity=10)]),
        build_policy(),
    )
    assert "task_filled_stock_qty" in plan.trace.rules_fired
    assert "task_drives_the_fetch" in plan.trace.rules_fired
    spec = ht.inventory_specs(plan)[0]
    assert spec.filters.get("requested_quantities") == {ht.uuid_of("ELP3754"): 10}
