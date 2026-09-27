"""Owner hand test 26 Sep 2026 (PR #1247), slice 6: the did-you-mean reply keeps the
quantity.

T15 "ELP3753 10" missed; the reply offered ELP3754. T16 "ELP3754" resolved correctly as
a fresh ask, but the 10 sat on the miss turn's focus row (`focus.products[{raw ELP3753,
quantity 10}]`, no uuid) and the fetch reads only this message's own quantities, so the
dealer was asked "How many units do you need?" again. The quantity is now copied onto
the one product the retry names.
"""
from __future__ import annotations

from app.services.chatbot import turn_runtime
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.state import Focus

from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict


def _t15_focus():
    return Focus(
        domains=["inventory"],
        products=[
            {
                "raw": "ELP3753",
                "hint": "product",
                "canonical_code": "ELP3753",
                "quantity": 10,
                "current_message": False,
                "confident": True,
            }
        ],
    )


def test_t16_the_retried_code_carries_the_missed_quantity():
    v = verdict(entities=[ht.asked("ELP3754")])
    _state2, plan = apply(ht.state(_t15_focus(), turn_no=16), v, build_policy())

    assert "did_you_mean_keeps_quantity" in plan.trace.rules_fired
    assert v["entities"][0]["quantity"] == 10
    spec = ht.inventory_specs(plan)[0]
    resolved = [{"uuid": ht.uuid_of("ELP3754"), "code": "ELP3754", "canonical_code": "ELP3754"}]
    out = turn_runtime._spec_quantities({"entities": v["entities"]}, spec, resolved)
    assert out["requested_quantities"] == {ht.uuid_of("ELP3754"): 10}


def test_a_quantity_typed_with_the_retry_wins():
    v = verdict(entities=[ht.asked("ELP3754", quantity=30)])
    apply(ht.state(_t15_focus(), turn_no=16), v, build_policy())
    assert v["entities"][0]["quantity"] == 30


def test_two_products_named_carry_nothing():
    v = verdict(entities=[ht.asked("ELP3754"), ht.asked("SRTKT1631SS")])
    _state2, plan = apply(ht.state(_t15_focus(), turn_no=16), v, build_policy())
    assert "did_you_mean_keeps_quantity" not in plan.trace.rules_fired
    assert all(e.get("quantity") is None for e in v["entities"])


def test_a_placed_product_on_the_focus_is_not_a_miss():
    focus = Focus(
        domains=["inventory"],
        products=[{**ht.product_rows("ELP3754")[0], "quantity": 10}],
    )
    v = verdict(entities=[ht.asked("SRTKT1631SS")])
    _state2, plan = apply(ht.state(focus, turn_no=16), v, build_policy())
    assert "did_you_mean_keeps_quantity" not in plan.trace.rules_fired
