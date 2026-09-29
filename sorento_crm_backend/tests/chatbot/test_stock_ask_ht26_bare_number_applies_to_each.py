"""Owner hand test 26 Sep 2026 (PR #1247), F2: one bare number after a question about
several products applies to each of them.

Owner ruling 26 Sep (F2): "okay" to the scout's question - over an open task with
several products still owed, in a real multi-product ask (not a family), should a bare
number mean the same quantity for all? Orchestrator reading: yes, and the reply names
each product with that quantity (the backend's R14 line per product, "<P> x <Q>: ...").
A family opens a task only when the dealer picks "all" of it, and one number then
applies to every line too (round 6).
"""
from __future__ import annotations

from app.services.chatbot.turn import task as task_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.state import Focus

from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict


def _open(*codes):
    return ht.stock_task([(code, None) for code in codes])


def test_one_number_over_two_products_fetches_both_at_that_quantity():
    task = _open("ELP3754", "SRTKT1631SS")
    state2, plan = apply(
        ht.state(Focus(tasks=(task,), domains=["inventory"])),
        verdict(demand_qty=50, entities=[]),
        build_policy(),
    )
    spec = ht.inventory_specs(plan)[0]
    assert spec.filters.get("requested_quantities") == {
        ht.uuid_of("ELP3754"): 50,
        ht.uuid_of("SRTKT1631SS"): 50,
    }
    assert [e["canonical_code"] for e in spec.entities] == ["ELP3754", "SRTKT1631SS"]


def test_the_reply_names_each_product_with_that_quantity():
    """The presenter's R14 line per entry: each names its product and the quantity."""
    from sorento_crm_mcp.presenters import _availability_line

    lines = [
        _availability_line({**ht.row(code, needs_quantity=False, requested_qty=50), "branch": branch})
        for code, branch in (("ELP3754", "in_stock"), ("SRTKT1631SS", "no_incoming"))
    ]
    assert lines[0].startswith("ELP3754 x 50: ")
    assert lines[1].startswith("SRTKT1631SS x 50: ")


def test_similar_codes_are_two_products_not_a_family():
    task = _open("ELP3754", "ELP3756")
    state2, plan = apply(
        ht.state(Focus(tasks=(task,), domains=["inventory"])),
        verdict(demand_qty=10, entities=[]),
        build_policy(),
    )
    spec = ht.inventory_specs(plan)[0]
    assert spec.filters.get("requested_quantities") == {
        ht.uuid_of("ELP3754"): 10,
        ht.uuid_of("ELP3756"): 10,
    }


def test_a_family_task_takes_one_number_for_all_too():
    """T2's own state: the ten-slot SRTWC286-SH* task and "88". Round 6 (owner console
    test of round 4, "they can just say one number like 10 to apply to all"): a family
    task is what "all" over a which-one list opens, and one number fills every line.
    Before round 6 this state re-asked."""
    task = _open(*ht.SRTWC286_FAMILY)
    state2, plan = apply(
        ht.state(Focus(tasks=(task,), domains=["inventory"])),
        verdict(demand_qty=88, entities=[]),
        build_policy(),
    )
    spec = ht.inventory_specs(plan)[0]
    assert spec.filters.get("requested_quantities") == {
        ht.uuid_of(code): 88 for code in ht.SRTWC286_FAMILY
    }
