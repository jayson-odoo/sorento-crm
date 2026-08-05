"""SCM M3 reorder engine — PURE-FUNCTION golden set (TDD centrepiece, AC-M3.1..3.12).

Every number here is asserted against ``fixtures/golden_m3.json``, which is blessed
INDEPENDENTLY by ``scripts/scm_m3_golden_derive.py`` (plain-Python arithmetic +
NormalDist — a different code path than the engine, so the test is not circular). No
DB: the maths take plain values. The resolver's M1/M2 reads are covered separately by
``test_m3_resolver.py``.
"""
from __future__ import annotations

import json
import os

import pytest

from app.services.scm import reorder_engine as eng

GOLDEN = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "golden_m3.json")))


# --- AC-M3.1 / M3.3 : ROP / SS / qty per representative trigger type -------

def test_case_A_reorder_point_fixed_days():
    g = GOLDEN["case_A_reorder_point_fixed"]
    ss, method, note = eng.safety_stock("fixed_days", demand_rate=g["demand_rate"],
                                        safety_days=g["safety_days"])
    assert ss == pytest.approx(g["safety_stock"])
    assert method == "fixed_days" and note is None
    rop = eng.reorder_point(g["demand_rate"], g["lead_time"], ss)
    assert rop == pytest.approx(g["reorder_point"])
    oup = eng.order_up_to(rop, g["demand_rate"], g["review_days"])
    assert oup == pytest.approx(g["order_up_to"])
    fired, reason = eng.trigger("reorder_point", net=g["net"], rop=rop, oup=oup)
    assert fired is True and "reorder_point" in reason
    rec, rnd = eng.order_qty(fired, net=g["net"], oup=oup, moq=g["moq"],
                             order_multiple=g["order_multiple"])
    assert rec == pytest.approx(g["recommended_qty"])
    assert rnd == pytest.approx(g["rounded_qty"])


def test_case_B_periodic_review_on_and_off_cadence():
    g = GOLDEN["case_B_periodic_review"]
    ss, _, _ = eng.safety_stock("fixed_days", demand_rate=g["demand_rate"],
                                safety_days=g["safety_days"])
    rop = eng.reorder_point(g["demand_rate"], g["lead_time"], ss)
    oup = eng.order_up_to(rop, g["demand_rate"], g["review_days"])
    assert ss == pytest.approx(g["safety_stock"])
    assert rop == pytest.approx(g["reorder_point"])
    assert oup == pytest.approx(g["order_up_to"])
    on, reason = eng.trigger("periodic_review", net=g["net"], oup=oup, on_cadence=True)
    assert on is True and "periodic_review" in reason
    off, _ = eng.trigger("periodic_review", net=g["net"], oup=oup, on_cadence=False)
    assert off is False   # off-cadence never fires even below order-up-to
    _, rnd = eng.order_qty(on, net=g["net"], oup=oup, moq=g["moq"],
                           order_multiple=g["order_multiple"])
    assert rnd == pytest.approx(g["rounded_qty"])


def test_case_C_min_max():
    g = GOLDEN["case_C_min_max"]
    ss, _, _ = eng.safety_stock("fixed_days", demand_rate=g["demand_rate"],
                                safety_days=g["safety_days"])
    assert ss == pytest.approx(g["safety_stock"])
    rop = eng.reorder_point(g["demand_rate"], g["lead_time"], ss)
    assert rop == pytest.approx(g["reorder_point"])
    fired, reason = eng.trigger("min_max", net=g["net"], min_level=g["min_override"],
                                oup=g["max_override"])
    assert fired is True and "min_max" in reason
    # min_max orders up to max_override
    rec, rnd = eng.order_qty(fired, net=g["net"], oup=g["max_override"], moq=g["moq"],
                             order_multiple=g["order_multiple"])
    assert rec == pytest.approx(g["recommended_qty"])
    assert rnd == pytest.approx(g["rounded_qty"])
    # above min -> no trigger
    assert eng.trigger("min_max", net=200, min_level=g["min_override"])[0] is False


# --- AC-M3.2 / M3.4 : statistical SS, thin fallback, policy-change-alters-output ---

def test_case_D_statistical_and_thin_fallback():
    g = GOLDEN["case_D_statistical"]
    ss, method, note = eng.safety_stock(
        "statistical", demand_rate=g["demand_rate"], cv_d=g["demand_cv"],
        var_lt=g["var_lt"], lead_time_days=g["lead_time"], service_level=g["service_level"])
    assert ss == pytest.approx(g["safety_stock"])
    assert method == "statistical" and note is None
    rop = eng.reorder_point(g["demand_rate"], g["lead_time"], ss)
    assert rop == pytest.approx(g["reorder_point"])

    # thin sample (var_lt missing) -> deterministic fixed_days fallback, recorded
    ss_fb, method_fb, note_fb = eng.safety_stock(
        "statistical", demand_rate=g["demand_rate"], cv_d=g["demand_cv"], var_lt=None,
        lead_time_days=g["lead_time"], service_level=g["service_level"],
        safety_days=g["safety_days"])
    assert ss_fb == pytest.approx(g["safety_stock_thin_fallback"])
    assert method_fb == g["fallback_method"] and note_fb is not None
    assert eng.reorder_point(g["demand_rate"], g["lead_time"], ss_fb) == pytest.approx(
        g["reorder_point_thin_fallback"])


def test_case_E_service_level_change_alters_output():
    d = GOLDEN["case_D_statistical"]
    e = GOLDEN["case_E_service_level_change"]
    ss_low, _, _ = eng.safety_stock("statistical", demand_rate=d["demand_rate"],
                                    cv_d=d["demand_cv"], var_lt=d["var_lt"],
                                    lead_time_days=d["lead_time"], service_level=0.95)
    ss_high, _, _ = eng.safety_stock("statistical", demand_rate=d["demand_rate"],
                                     cv_d=d["demand_cv"], var_lt=d["var_lt"],
                                     lead_time_days=d["lead_time"], service_level=0.99)
    assert ss_high == pytest.approx(e["safety_stock"])
    assert ss_high > ss_low   # raising service level raises SS with no code change


# --- AC-M3.8 : network aggregation + allocation ----------------------------

def test_case_F_network_surplus_allocation():
    g = GOLDEN["case_F_network_surplus"]
    whs = [{"warehouse_id": wid, "demand_rate": d, "net": n}
           for wid, d, n in zip(g["warehouses"], g["demand_rates"], g["nets"])]
    res = eng.aggregate_network(whs, lead_time_days=g["lead_time"],
                                safety_days=g["safety_days"], review_days=g["review_days"],
                                moq=g["moq"], order_multiple=g["order_multiple"])
    assert res["safety_stock"] == pytest.approx(g["safety_stock"])
    assert res["reorder_point"] == pytest.approx(g["reorder_point"])
    assert res["order_up_to"] == pytest.approx(g["order_up_to"])
    assert res["buy_qty"] == pytest.approx(g["buy_qty"])
    alloc = [res["allocation"][wid] for wid in g["warehouses"]]
    assert alloc == g["allocation"]
    assert sum(res["allocation"].values()) == g["buy_qty"]   # breakdown sums to buy


def test_case_G_network_buy_below_total_deficit():
    g = GOLDEN["case_G_network_deficit_capped"]
    whs = [{"warehouse_id": f"WH{i+1}", "deficit": dfc, "demand_rate": dmd}
           for i, (dfc, dmd) in enumerate(zip(g["deficits"], g["demand_rates"]))]
    alloc = eng.allocate(g["buy_qty"], whs)
    assert [alloc[f"WH{i+1}"] for i in range(3)] == g["allocation"]
    assert sum(alloc.values()) == g["buy_qty"]   # proportional-to-deficit, sums to buy


def test_case_N_network_no_trigger_in_rop_oup_band():
    """#1/#4: a reorder_point network aggregate whose net sits ABOVE ROP but BELOW OUP
    must NOT trigger a buy (sizing OUP-net>0 is not a trigger). The trigger gate is
    net<=ROP on the aggregate — same as per-warehouse."""
    g = GOLDEN["case_N_network_no_trigger_in_band"]
    whs = [{"warehouse_id": wid, "demand_rate": d, "net": n}
           for wid, d, n in zip(g["warehouses"], g["demand_rates"], g["nets"])]
    res = eng.aggregate_network(whs, lead_time_days=g["lead_time"],
                                safety_days=g["safety_days"], review_days=g["review_days"])
    assert res["agg_net"] == pytest.approx(g["agg_net"])
    assert res["reorder_point"] == pytest.approx(g["reorder_point"])
    assert res["order_up_to"] == pytest.approx(g["order_up_to"])
    # net is genuinely in the band …
    assert res["agg_net"] > res["reorder_point"] and res["agg_net"] < res["order_up_to"]
    # … so the reorder_point trigger (net<=ROP) does NOT fire even though OUP-net>0
    fired, reason = eng.trigger("reorder_point", net=res["agg_net"],
                                rop=res["reorder_point"], oup=res["order_up_to"])
    assert fired is False and reason is None
    assert g["triggered_reorder_point"] is False


# --- AC-M3.5 / M3.6 : supplier precedence + alternatives + no-supplier ------

def _mk_suppliers():
    s = GOLDEN["case_I_supplier_selection"]["suppliers"]
    return [{"supplier_id": k, "is_primary": v["is_primary"], "unit_cost": v["unit_cost"],
             "lead_time_days": v["lead"], "composite_score": v["score"]}
            for k, v in s.items()]


@pytest.mark.parametrize("selection", ["primary", "best_score", "lowest_cost"])
def test_case_I_supplier_selection(selection):
    g = GOLDEN["case_I_supplier_selection"][selection]
    res = eng.select_supplier(_mk_suppliers(), selection=selection)
    assert res["exception"] is None
    assert res["chosen"]["supplier_id"] == g["chosen"]
    assert [a["supplier_id"] for a in res["alternatives"]] == g["alternatives"]


def test_no_supplier_flagged_exception():
    res = eng.select_supplier([])
    assert res["chosen"] is None
    assert res["exception"] == "no_supplier"
    assert res["alternatives"] == []


def test_single_supplier_used():
    res = eng.select_supplier([{"supplier_id": "solo", "is_primary": False,
                                "unit_cost": 5, "lead_time_days": 10, "composite_score": None}])
    assert res["exception"] is None and res["chosen"]["supplier_id"] == "solo"


@pytest.mark.parametrize("selection", ["primary", "best_score", "lowest_cost"])
def test_supplier_tie_break_is_deterministic(selection):
    """#2: two suppliers tied on EVERY ranking factor (primary flag + composite score +
    unit cost) resolve to the SAME winner every call — supplier_id is the final stable
    tiebreak, never DB row order."""
    a = {"supplier_id": "aaaa1111", "is_primary": True, "unit_cost": 100,
         "lead_time_days": 30, "composite_score": 0.8}
    b = {"supplier_id": "bbbb2222", "is_primary": True, "unit_cost": 100,
         "lead_time_days": 30, "composite_score": 0.8}
    forward = eng.select_supplier([a, b], selection=selection)["chosen"]["supplier_id"]
    reverse = eng.select_supplier([b, a], selection=selection)["chosen"]["supplier_id"]
    assert forward == reverse == "aaaa1111"   # lowest supplier_id wins regardless of order


# --- AC-M3.4 : lead-time precedence ----------------------------------------

@pytest.mark.parametrize("key", ["measured", "declared", "default"])
def test_case_J_lead_time_precedence(key):
    g = GOLDEN["case_J_lead_time"][key]
    val, src = eng.lead_time(g["measured"], g["declared"])
    assert val == pytest.approx(g["value"])
    assert src == g["source"]


# --- AC-M3.12 : confidence map ---------------------------------------------

def test_case_K_confidence_map():
    g = GOLDEN["case_K_confidence"]
    assert eng.confidence("X", demand_adequate=True, supplier_adequate=True) == g["X_adequate"]
    assert eng.confidence("X", demand_adequate=False, supplier_adequate=True) == g["X_thin"]
    assert eng.confidence("Y", demand_adequate=True, supplier_adequate=True) == g["Y_adequate"]
    assert eng.confidence("Y", demand_adequate=True, supplier_adequate=False) == g["Y_thin"]
    assert eng.confidence("Z", demand_adequate=True, supplier_adequate=True) == g["Z_adequate"]
    assert eng.confidence("Z", demand_adequate=False, supplier_adequate=True) == g["Z_thin"]
    assert eng.confidence(None, demand_adequate=True, supplier_adequate=True) == g["unknown_adequate"]


# --- AC-M3.3 : rounding / MoQ (dedicated) ----------------------------------

def test_case_L_rounding_and_moq():
    g = GOLDEN["case_L_rounding"]
    assert eng.round_order_qty(470, 50, 12) == pytest.approx(g["rec470_moq50_mult12"])
    assert eng.round_order_qty(30, 100, 25) == pytest.approx(g["rec30_moq100_mult25"])
    assert eng.round_order_qty(100, 50, 1) == pytest.approx(g["rec100_moq50_mult1"])
    assert eng.round_order_qty(121, 0, 20) == pytest.approx(g["rec121_moq0_mult20"])
    # not triggered -> zero qty regardless of oup
    assert eng.order_qty(False, net=10, oup=1000, moq=50, order_multiple=12) == (0.0, 0.0)


# --- AC-M3.9 : disposition + transfer flag ---------------------------------

def test_case_M_disposition_and_transfer():
    g = GOLDEN["case_M_disposition"]
    dead = g["dead"]
    d = eng.disposition(on_hand=dead["on_hand"], last_movement_days=dead["last_movement_days"],
                        dead_stock_days=dead["dead_stock_days"], days_of_cover_val=None,
                        overstock_days=120)
    # A SUBSET check, not equality: the golden set pins the type and the action, which are
    # what the plan acts on. The engine also reports which evidence fired (`basis`, L5), and
    # pinning the whole dict here would make every future signal a golden-set change.
    assert (d["type"], d["action"]) == (dead["type"], dead["action"])

    over = g["overstock"]
    doc = eng.days_of_cover(over["on_hand"], over["demand_rate"])
    assert doc == pytest.approx(over["days_of_cover"])
    o = eng.disposition(on_hand=over["on_hand"], last_movement_days=1,
                        dead_stock_days=180, days_of_cover_val=doc,
                        overstock_days=over["overstock_days"])
    assert (o["type"], o["action"]) == (over["type"], over["action"])

    # never-moved with stock and NO purchase date is NOT dead (no consumption history != a
    # stale movement). A stocked-but-idle SKU must not be auto-flagged for discontinuation
    # on no evidence. L5 narrows this to "no evidence": once the purchase history says the
    # stock was bought before the window, the same case IS dead - see test_ageing_signal.py.
    assert eng.disposition(on_hand=10, last_movement_days=None, dead_stock_days=180,
                           days_of_cover_val=None, overstock_days=120) is None
    # never-moved BUT overstocked (high cover) -> overstock still applies independently
    assert eng.disposition(on_hand=10, last_movement_days=None, dead_stock_days=180,
                           days_of_cover_val=400, overstock_days=120)["type"] == "overstock"
    # an ACTUAL stale movement beyond the window -> dead
    assert eng.disposition(on_hand=10, last_movement_days=365, dead_stock_days=180,
                           days_of_cover_val=None, overstock_days=120)["type"] == "dead"
    # healthy: moved recently, cover under ceiling -> no disposition
    assert eng.disposition(on_hand=10, last_movement_days=5, dead_stock_days=180,
                           days_of_cover_val=30, overstock_days=120) is None

    t = g["transfer"]
    flags = eng.transfer_flags(t["sku"], [
        {"warehouse_id": "a", "warehouse_code": t["overstock_wh"], "overstock": True, "short": False},
        {"warehouse_id": "b", "warehouse_code": t["short_wh"], "overstock": False, "short": True},
    ])
    assert len(flags) == 1
    assert flags[0]["message"] == t["message"]
    assert flags[0]["from_warehouse"] == t["overstock_wh"]
    assert flags[0]["to_warehouse"] == t["short_wh"]


# --- AC-M3.2 : policy resolution precedence + tiebreak ---------------------

def test_resolve_policy_precedence_and_tiebreak():
    policies = [
        {"scope_type": "global", "scope_ref": None, "priority": 0, "is_active": True, "id": "g"},
        {"scope_type": "product_class", "scope_ref": "CB-FT", "priority": 10, "is_active": True, "id": "c"},
        {"scope_type": "abc_xyz_cell", "scope_ref": "A-X", "priority": 15, "is_active": True, "id": "cell"},
        {"scope_type": "sku", "scope_ref": "P1", "priority": 20, "is_active": True, "id": "s"},
    ]
    # most specific (sku) wins
    assert eng.resolve_policy(policies, product_id="P1", abc_xyz_cell="A-X",
                              product_class="CB-FT")["id"] == "s"
    # no sku match -> abc/xyz cell
    assert eng.resolve_policy(policies, product_id="PX", abc_xyz_cell="A-X",
                              product_class="CB-FT")["id"] == "cell"
    # no cell -> product_class
    assert eng.resolve_policy(policies, product_id="PX", abc_xyz_cell="C-Z",
                              product_class="CB-FT")["id"] == "c"
    # nothing specific -> global
    assert eng.resolve_policy(policies, product_id="PX", abc_xyz_cell="C-Z",
                              product_class="OTHER")["id"] == "g"
    # inactive most-specific is skipped
    policies[3]["is_active"] = False
    assert eng.resolve_policy(policies, product_id="P1", abc_xyz_cell="A-X",
                              product_class="CB-FT")["id"] == "cell"


def test_resolve_policy_priority_tiebreak_within_scope():
    policies = [
        {"scope_type": "sku", "scope_ref": "P1", "priority": 5, "is_active": True, "id": "low"},
        {"scope_type": "sku", "scope_ref": "P1", "priority": 50, "is_active": True, "id": "high"},
    ]
    assert eng.resolve_policy(policies, product_id="P1")["id"] == "high"
