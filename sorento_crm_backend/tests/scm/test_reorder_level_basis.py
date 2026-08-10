"""S10 - the reorder level as a planning basis beside the forecast one.

Pure-function coverage of the engine change plus the suggestion arithmetic. The two things
worth pinning hardest are the ones the user asked for by name: a level that is not set is not
a level of zero, and switching the basis must leave the forecast basis producing exactly what
it produced before.
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


# --- the suggestion ----------------------------------------------------------------------

def _months(*qtys):
    return [{"month": f"2026-{i + 1:02d}", "qty": float(q)} for i, q in enumerate(qtys)]


def test_suggestion_is_average_monthly_movement_times_cover():
    out = rl.suggest_level(_months(30, 60, 30), cover_months=2)
    assert out["level"] == 80.0                     # avg 40 x 2
    assert out["basis"]["avg_monthly"] == 40.0
    assert out["basis"]["cover_months"] == 2
    assert out["basis"]["months_studied"] == 3
    assert out["basis"]["no_movement"] is False


def test_suggestion_carries_the_arithmetic_so_it_can_be_argued_with():
    out = rl.suggest_level(_months(10, 20, 0), cover_months=1.5)
    basis = out["basis"]
    assert basis["months"] == _months(10, 20, 0)
    assert basis["total_qty"] == 30.0
    assert basis["raw_level"] == 15.0
    assert out["level"] == 15.0


def test_no_movement_suggests_zero_and_says_so():
    out = rl.suggest_level(_months(0, 0, 0), cover_months=2)
    assert out["level"] == 0.0
    assert out["basis"]["no_movement"] is True


def test_zero_suggestion_is_not_pushed_up_to_the_moq():
    # An item that has not moved should suggest 0, not "buy a pallet because that is the
    # smallest a pallet comes in". MOQ shapes an order, it does not create demand.
    out = rl.suggest_level(_months(0, 0, 0), cover_months=2, moq=50.0, order_multiple=10.0)
    assert out["level"] == 0.0


def test_suggestion_respects_moq_and_multiple_when_there_is_movement():
    out = rl.suggest_level(_months(1, 1, 1), cover_months=2, moq=5.0, order_multiple=4.0)
    # avg 1 x 2 = 2 -> floored at moq 5 -> rounded up to the next 4
    assert out["level"] == 8.0


def test_no_months_studied_does_not_divide_by_zero():
    out = rl.suggest_level([], cover_months=2)
    assert out["level"] == 0.0
    assert out["basis"]["months_studied"] == 0


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


# --- S13f: the trajectory shapes the rounding, never the arithmetic ----------------------

def test_rising_demand_rounds_the_suggestion_up_to_a_whole_unit():
    out = rl.suggest_level(_months(10, 11, 10), cover_months=1.5, trend="rising")
    # avg 10.3333 x 1.5 = 15.5 -> a rising book gets 16, not 15.5
    assert out["level"] == 16.0
    assert out["basis"]["trend"] == "rising"
    assert out["basis"]["raw_level"] == 15.5


def test_dying_demand_rounds_the_suggestion_down():
    out = rl.suggest_level(_months(10, 11, 10), cover_months=1.5, trend="falling")
    assert out["level"] == 15.0
    assert out["basis"]["trend"] == "falling"


def test_quiet_demand_also_rounds_down_because_orders_stopped():
    out = rl.suggest_level(_months(1, 0, 0), cover_months=2, trend="quiet")
    # avg 0.3333 x 2 = 0.6667 -> floors to 0, and honestly so
    assert out["level"] == 0.0


def test_no_trend_leaves_the_arithmetic_exactly_as_before():
    out = rl.suggest_level(_months(30, 60, 30), cover_months=2)
    assert out["level"] == 80.0
    assert out["basis"]["trend"] is None


def test_the_trend_rounds_before_the_supplier_constraints_apply():
    # avg 1 x 2.2 = 2.2 -> rising ceils to 3 -> multiple of 4 lifts to 4.
    out = rl.suggest_level(_months(1, 1, 1), cover_months=2.2, trend="rising",
                           order_multiple=4.0)
    assert out["level"] == 4.0
