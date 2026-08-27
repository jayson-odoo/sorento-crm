"""S10 - the reorder level as a planning basis beside the forecast one.

Pure-function coverage of the engine change and of how a stored level resolves. The two
things worth pinning hardest are the ones the user asked for by name: a level that is not
set is not a level of zero, and switching the basis must leave the forecast basis producing
exactly what it produced before.

The SUGGESTION arithmetic moved to `test_reorder_level_formula.py` when the level became
`ADU x lead_time + 14 days of safety` (AC-R11, captain 27 Aug); the old
`avg monthly movement x cover months` function it used to pin is gone with it.
"""
from __future__ import annotations

import pytest

from app.services.scm import reorder_engine as eng
from app.services.scm import reorder_level_service as rl


# --- trigger -----------------------------------------------------------------------------

def test_fires_when_net_is_at_or_below_the_level():
    fired, reason = eng.trigger("reorder_level", net=10.0, reorder_level=10.0)
    assert fired is True
    assert "reorder_level" in reason and "10" in reason


def test_does_not_fire_above_the_level_however_large_the_forecast():
    # rop/oup are deliberately huge: under the forecast basis this cell would buy. The whole
    # point of the level basis is that it does not.
    fired, reason = eng.trigger("reorder_level", net=50.0, reorder_level=10.0,
                                rop=900.0, oup=1200.0)
    assert fired is False
    assert reason is None


def test_a_missing_level_is_not_a_level_of_zero():
    fired, reason = eng.trigger("reorder_level", net=-5.0, reorder_level=None)
    assert fired is False, "an unset level must never be planned as 0"
    assert reason is None


def test_forecast_bases_are_untouched_by_the_new_argument():
    # Passing a level through a forecast policy must change nothing: the basis is a toggle,
    # not a replacement.
    with_level = eng.trigger("reorder_point", net=5.0, rop=10.0, reorder_level=999.0)
    without = eng.trigger("reorder_point", net=5.0, rop=10.0)
    assert with_level == without
    assert with_level[0] is True

    pr_with = eng.trigger("periodic_review", net=5.0, rop=10.0, oup=20.0, reorder_level=999.0)
    pr_without = eng.trigger("periodic_review", net=5.0, rop=10.0, oup=20.0)
    assert pr_with == pr_without


# --- quantity ----------------------------------------------------------------------------

def test_quantity_is_the_gap_to_the_level():
    recommended, rounded = eng.order_qty(True, net=4.0, oup=10.0)
    assert recommended == 6.0
    assert rounded == 6.0


def test_quantity_floors_at_moq_then_rounds_up_to_the_multiple():
    recommended, rounded = eng.order_qty(True, net=8.0, oup=10.0, moq=5.0, order_multiple=4.0)
    assert recommended == 2.0          # the honest gap
    assert rounded == 8.0              # max(2, moq 5) -> ceil to the next 4


# --- pooled sizing on levels -------------------------------------------------------------

def test_pool_target_is_the_sum_of_member_levels():
    whs = [{"warehouse_id": "A", "demand_rate": 1.0, "net": 2.0},
           {"warehouse_id": "B", "demand_rate": 1.0, "net": 3.0}]
    agg = eng.aggregate_network(whs, lead_time_days=14,
                                levels={"A": 10.0, "B": 20.0})
    assert agg["reorder_point"] == 30.0
    assert agg["order_up_to"] == 30.0
    assert agg["recommended_qty"] == 25.0          # 30 target - 5 net


def test_a_member_with_no_level_contributes_nothing_and_receives_nothing():
    whs = [{"warehouse_id": "A", "demand_rate": 1.0, "net": 0.0},
           {"warehouse_id": "B", "demand_rate": 5.0, "net": 0.0}]
    agg = eng.aggregate_network(whs, lead_time_days=14, levels={"A": 12.0, "B": None})
    assert agg["reorder_point"] == 12.0
    by_wh = {w["warehouse_id"]: w for w in agg["warehouses"]}
    assert by_wh["B"]["deficit"] == 0.0, "an unset bin must not be given a deficit"
    # B has 5x A's velocity, so a demand-weighted split would have sent it most of the buy.
    assert agg["allocation"]["B"] == 0
    assert agg["allocation"]["A"] == 12


def test_levels_none_leaves_the_forecast_aggregate_identical():
    whs = [{"warehouse_id": "A", "demand_rate": 2.0, "net": 1.0},
           {"warehouse_id": "B", "demand_rate": 3.0, "net": 4.0}]
    a = eng.aggregate_network(whs, lead_time_days=14, safety_days=7, review_days=30)
    b = eng.aggregate_network(whs, lead_time_days=14, safety_days=7, review_days=30,
                              levels=None)
    assert a == b


# --- level resolution --------------------------------------------------------------------

def test_the_per_location_level_beats_the_product_wide_one():
    levels = {("P1", None): {"level": 5}, ("P1", "W1"): {"level": 40}}
    assert rl.resolve_level(levels, "P1", "W1")["level"] == 40


def test_the_product_wide_level_is_the_fallback():
    levels = {("P1", None): {"level": 5}}
    assert rl.resolve_level(levels, "P1", "W1")["level"] == 5


def test_no_level_anywhere_resolves_to_none_not_zero():
    assert rl.resolve_level({}, "P1", "W1") is None


def test_upsert_rejects_an_unknown_source():
    from app.services.error_handler import AppException
    with pytest.raises(AppException):
        rl.upsert_level(None, product_id="P1", warehouse_id=None, level=1,
                        source="whatever")


def test_upsert_rejects_a_negative_level():
    from app.services.error_handler import AppException
    with pytest.raises(AppException):
        rl.upsert_level(None, product_id="P1", warehouse_id=None, level=-1)
