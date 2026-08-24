"""SCM M3 reorder-engine golden-set derivation (INDEPENDENT reference).

Recomputes every blessed ROP / SS / order-qty / allocation / trigger / confidence
number in ``tests/scm/fixtures/golden_m3.json`` from FIRST PRINCIPLES using plain
Python arithmetic + ``statistics.NormalDist`` - deliberately a DIFFERENT code path
than ``app/services/scm/reorder_engine.py`` so the golden test is NOT circular. The
engine is written to reproduce these frozen numbers; re-run this only to deliberately
re-bless.

    venv/bin/python scripts/scm_m3_golden_derive.py

The synthetic cases use clean round inputs (no DB) so the hand-math is auditable in
the printed working. The Postgres-backed resolver tests (tests/scm/test_m3_resolver.py)
cover reading the real M1/M2 tables; this script owns the pure maths blessing.

LOCKED FORMULAE (see PLAN-scm-m3-reorder-engine.md §1 + UAC M3-D1..D5):
  * SS (fixed_days)   = demand_rate * safety_days
  * SS (statistical)  = Z(service_level) * sqrt(LT * sigma_d^2 + demand^2 * var_LT)
                        where sigma_d = demand_cv * demand_rate, var_LT = lead-time variance
  * ROP               = demand_rate * lead_time + SS
  * order_up_to (S)   = ROP + demand_rate * review_period_days
                        (min_max: S = max_override)
  * recommended_qty   = S - net   (0 when not triggered / non-positive)
  * rounded_qty       = ceil(max(recommended, moq) / order_multiple) * order_multiple
  * trigger           = reorder_point: net <= ROP ; periodic_review: on-cadence & net < S ;
                        min_max: net <= min_override
  * network buy       = aggregate demand+net -> S_agg - net_agg, rounded ; allocate
                        deficit-first then velocity-proportional surplus (sums to buy)
  * confidence        = X & adequate -> high ; Z or thin -> low ; else medium
"""
from __future__ import annotations

import json
import math
import os
from statistics import NormalDist


def z(service_level: float) -> float:
    return NormalDist().inv_cdf(service_level)


def ss_fixed(demand_rate: float, safety_days: float) -> float:
    return demand_rate * safety_days


def ss_stat(demand_rate: float, cv_d: float, var_lt: float, lead_time: float,
            service_level: float) -> float:
    sigma_d = cv_d * demand_rate
    variance = lead_time * sigma_d ** 2 + demand_rate ** 2 * var_lt
    return z(service_level) * math.sqrt(variance)


def rop(demand_rate: float, lead_time: float, ss: float) -> float:
    return demand_rate * lead_time + ss


def order_up_to(rop_val: float, demand_rate: float, review_days: float) -> float:
    return rop_val + demand_rate * review_days


def round_order(recommended: float, moq: float, order_multiple: float) -> float:
    q = recommended
    if moq is not None and q < moq:
        q = moq
    if order_multiple:
        q = math.ceil(q / order_multiple) * order_multiple
    return float(q)


def apportion(total: int, weights: list[float]) -> list[int]:
    """Largest-remainder integer apportionment summing EXACTLY to total."""
    n = len(weights)
    s = sum(weights)
    if s <= 0:
        base, rem = divmod(total, n)
        return [base + (1 if i < rem else 0) for i in range(n)]
    raw = [total * w / s for w in weights]
    floors = [int(math.floor(x)) for x in raw]
    rem = total - sum(floors)
    order = sorted(range(n), key=lambda i: (-(raw[i] - floors[i]), i))
    for k in range(rem):
        floors[order[k]] += 1
    return floors


def allocate(buy: int, deficits: list[float], demands: list[float]) -> list[int]:
    total_def = sum(deficits)
    if buy <= total_def:
        weights = deficits                          # buy < Sum(deficit): proportional to deficit
    else:
        surplus = buy - total_def
        total_dem = sum(demands)
        if total_dem > 0:
            weights = [deficits[i] + surplus * demands[i] / total_dem
                       for i in range(len(deficits))]   # deficit-first + velocity surplus
        else:
            even = surplus / len(deficits)
            weights = [d + even for d in deficits]
    return apportion(buy, weights)


def main() -> None:
    out: dict = {}

    # -- Case A: reorder_point, fixed_days, X band, rounding ------------------
    dA, sdA, ltA, revA = 10.0, 7.0, 30.0, 30.0
    ssA = ss_fixed(dA, sdA)                 # 70
    ropA = rop(dA, ltA, ssA)               # 370
    oupA = order_up_to(ropA, dA, revA)     # 670
    recA = oupA - 200                      # 470
    rndA = round_order(recA, 50, 12)       # 480
    out["case_A_reorder_point_fixed"] = {
        "demand_rate": dA, "safety_days": sdA, "lead_time": ltA, "review_days": revA,
        "net": 200, "moq": 50, "order_multiple": 12,
        "safety_stock": ssA, "reorder_point": ropA, "order_up_to": oupA,
        "recommended_qty": recA, "rounded_qty": rndA,
        "triggered": 200 <= ropA, "confidence": "high"}

    # -- Case B: periodic_review, Y band -------------------------------------
    dB, sdB, ltB, revB = 5.0, 7.0, 20.0, 30.0
    ssB = ss_fixed(dB, sdB)                 # 35
    ropB = rop(dB, ltB, ssB)               # 135
    oupB = order_up_to(ropB, dB, revB)     # 285
    recB = oupB - 150                      # 135
    rndB = round_order(recB, 100, 25)      # 150
    out["case_B_periodic_review"] = {
        "demand_rate": dB, "safety_days": sdB, "lead_time": ltB, "review_days": revB,
        "net": 150, "moq": 100, "order_multiple": 25,
        "safety_stock": ssB, "reorder_point": ropB, "order_up_to": oupB,
        "recommended_qty": recB, "rounded_qty": rndB,
        "triggered_on_cadence": 150 < oupB, "triggered_off_cadence": False,
        "confidence": "medium"}

    # -- Case C: min_max, Z band ---------------------------------------------
    dC, sdC, ltC = 8.0, 7.0, 15.0
    minC, maxC = 100.0, 500.0
    ssC = ss_fixed(dC, sdC)                 # 56
    ropC = rop(dC, ltC, ssC)               # 176 (informational; min_max triggers on min)
    recC = maxC - 80                        # 420 (order up to max)
    rndC = round_order(recC, 50, 10)        # 420
    out["case_C_min_max"] = {
        "demand_rate": dC, "safety_days": sdC, "lead_time": ltC,
        "min_override": minC, "max_override": maxC, "net": 80,
        "moq": 50, "order_multiple": 10,
        "safety_stock": ssC, "reorder_point": ropC, "order_up_to": maxC,
        "recommended_qty": recC, "rounded_qty": rndC,
        "triggered": 80 <= minC, "confidence": "low"}

    # -- Case D: statistical SS (full) vs thin-sample fallback ---------------
    dD, cvD, varD, ltD, slD, sdD = 10.0, 0.3, 4.0, 25.0, 0.95, 7.0
    ssD = ss_stat(dD, cvD, varD, ltD, slD)  # 1.644853...*25 = 41.12134...
    ropD = rop(dD, ltD, ssD)
    ssD_fb = ss_fixed(dD, sdD)              # thin -> 70
    ropD_fb = rop(dD, ltD, ssD_fb)          # 320
    out["case_D_statistical"] = {
        "demand_rate": dD, "demand_cv": cvD, "var_lt": varD, "lead_time": ltD,
        "service_level": slD, "safety_days": sdD,
        "safety_stock": ssD, "reorder_point": ropD,
        "safety_stock_thin_fallback": ssD_fb, "reorder_point_thin_fallback": ropD_fb,
        "fallback_method": "fixed_days"}

    # -- Case E: policy change (service_level 0.95 -> 0.99) alters output -----
    ssE = ss_stat(dD, cvD, varD, ltD, 0.99)   # 2.326347...*25
    out["case_E_service_level_change"] = {
        "service_level": 0.99, "safety_stock": ssE,
        "note": "same inputs as case D but service_level 0.99 -> larger SS, no code change"}

    # -- Case F: network aggregation + allocation, surplus > 0 ---------------
    ltN, sdN, revN = 30.0, 7.0, 30.0
    whF = [
        {"warehouse_id": "WH1", "demand_rate": 10.0, "net": 50.0},
        {"warehouse_id": "WH2", "demand_rate": 5.0, "net": 200.0},
        {"warehouse_id": "WH3", "demand_rate": 8.0, "net": 20.0},
    ]
    agg_demand = sum(w["demand_rate"] for w in whF)     # 23
    agg_net = sum(w["net"] for w in whF)                # 270
    ssN = ss_fixed(agg_demand, sdN)                     # 161
    ropN = rop(agg_demand, ltN, ssN)                    # 851
    oupN = order_up_to(ropN, agg_demand, revN)          # 1541
    recN = oupN - agg_net                               # 1271
    buyN = int(round_order(recN, 50, 12))               # 1272
    deficits = [max(rop(w["demand_rate"], ltN, ss_fixed(w["demand_rate"], sdN)) - w["net"], 0.0)
                for w in whF]                            # [320, 0, 276]
    demands = [w["demand_rate"] for w in whF]
    allocF = allocate(buyN, deficits, demands)
    out["case_F_network_surplus"] = {
        "warehouses": [w["warehouse_id"] for w in whF],
        "demand_rates": demands, "nets": [w["net"] for w in whF],
        "lead_time": ltN, "safety_days": sdN, "review_days": revN,
        "moq": 50, "order_multiple": 12,
        "agg_demand": agg_demand, "agg_net": agg_net, "safety_stock": ssN,
        "reorder_point": ropN, "order_up_to": oupN, "recommended_qty": recN,
        "buy_qty": buyN, "deficits": deficits, "allocation": allocF,
        "allocation_sum": sum(allocF)}

    # -- Case G: network allocation, buy_qty < Sum(deficit) ------------------
    buyG = 400
    deficitsG = [320.0, 0.0, 276.0]
    demandsG = [10.0, 5.0, 8.0]
    allocG = allocate(buyG, deficitsG, demandsG)
    out["case_G_network_deficit_capped"] = {
        "buy_qty": buyG, "deficits": deficitsG, "demand_rates": demandsG,
        "allocation": allocG, "allocation_sum": sum(allocG)}

    # -- Case N: network buy is TRIGGER-GATED (ROP < net < OUP → no buy) ------
    #   A reorder_point network cell whose aggregate net sits ABOVE ROP but BELOW the
    #   order-up-to level must NOT trigger a buy (matches per-warehouse). Sizing a buy
    #   (OUP - net > 0) is not a trigger - the trigger is net <= ROP.
    ltNb, sdNb, revNb = 30.0, 7.0, 30.0
    whNb = [
        {"warehouse_id": "WH1", "demand_rate": 6.0, "net": 300.0},
        {"warehouse_id": "WH2", "demand_rate": 4.0, "net": 200.0},
    ]
    agg_demand_b = sum(w["demand_rate"] for w in whNb)   # 10
    agg_net_b = sum(w["net"] for w in whNb)              # 500
    ssNb = ss_fixed(agg_demand_b, sdNb)                  # 70
    ropNb = rop(agg_demand_b, ltNb, ssNb)                # 370
    oupNb = order_up_to(ropNb, agg_demand_b, revNb)      # 670
    out["case_N_network_no_trigger_in_band"] = {
        "warehouses": [w["warehouse_id"] for w in whNb],
        "demand_rates": [w["demand_rate"] for w in whNb], "nets": [w["net"] for w in whNb],
        "lead_time": ltNb, "safety_days": sdNb, "review_days": revNb,
        "agg_demand": agg_demand_b, "agg_net": agg_net_b, "safety_stock": ssNb,
        "reorder_point": ropNb, "order_up_to": oupNb,
        "net_above_rop": agg_net_b > ropNb, "net_below_oup": agg_net_b < oupNb,
        "triggered_reorder_point": agg_net_b <= ropNb,   # False - no buy in the band
        "buy_qty": 0}

    # -- Case I: supplier precedence + alternatives --------------------------
    #   S1 primary cost100 lead30 score0.7 ; S2 cost80 lead40 score0.9 ; S3 cost90 lead20 score0.6
    out["case_I_supplier_selection"] = {
        "suppliers": {
            "S1": {"is_primary": True, "unit_cost": 100, "lead": 30, "score": 0.7},
            "S2": {"is_primary": False, "unit_cost": 80, "lead": 40, "score": 0.9},
            "S3": {"is_primary": False, "unit_cost": 90, "lead": 20, "score": 0.6}},
        "primary": {"chosen": "S1", "alternatives": ["S2", "S3"]},
        "best_score": {"chosen": "S2", "alternatives": ["S1", "S3"]},
        "lowest_cost": {"chosen": "S2", "alternatives": ["S3", "S1"]}}

    # -- Case J: lead-time precedence ----------------------------------------
    out["case_J_lead_time"] = {
        "measured": {"measured": 12.5, "declared": 30, "value": 12.5, "source": "measured"},
        "declared": {"measured": None, "declared": 30, "value": 30, "source": "declared"},
        "default": {"measured": None, "declared": None, "value": 30, "source": "default"}}

    # -- Case K: confidence map ----------------------------------------------
    out["case_K_confidence"] = {
        "X_adequate": "high", "X_thin": "low", "Y_adequate": "medium",
        "Y_thin": "low", "Z_adequate": "low", "Z_thin": "low",
        "unknown_adequate": "medium"}

    # -- Case L: rounding / MoQ ----------------------------------------------
    out["case_L_rounding"] = {
        "rec470_moq50_mult12": round_order(470, 50, 12),      # 480
        "rec30_moq100_mult25": round_order(30, 100, 25),      # 100 (moq floor dominates)
        "rec100_moq50_mult1": round_order(100, 50, 1),        # 100
        "rec121_moq0_mult20": round_order(121, 0, 20),        # 140
        "not_triggered": 0}

    # -- Case M: disposition + transfer flag ---------------------------------
    out["case_M_disposition"] = {
        "dead": {"on_hand": 500, "last_movement_days": 200, "dead_stock_days": 180,
                 "type": "dead", "action": "discontinue_or_promo"},
        "overstock": {"on_hand": 3650, "demand_rate": 10.0, "days_of_cover": 365.0,
                      "overstock_days": 120, "type": "overstock", "action": "hold_or_promo"},
        "transfer": {"sku": "X", "overstock_wh": "WH-A", "short_wh": "WH-B",
                     "message": "consider transfer X WH-A→WH-B", "buy_qty_unchanged": True}}

    dst = os.path.join(os.path.dirname(__file__), "..", "tests", "scm", "fixtures", "golden_m3.json")
    payload = {
        "_note": ("M3 reorder-engine blessed golden set. Derived INDEPENDENTLY of the engine "
                  "by scripts/scm_m3_golden_derive.py (plain-Python arithmetic + NormalDist). "
                  "Pure-function maths only; the resolver's DB reads are covered by "
                  "tests/scm/test_m3_resolver.py against the live M1/M2 tables."),
        "z_scores": {"0.90": z(0.90), "0.95": z(0.95), "0.98": z(0.98), "0.99": z(0.99)},
        **out,
    }
    with open(dst, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(json.dumps(payload, indent=2))
    print(f"\nwrote {os.path.abspath(dst)}")


if __name__ == "__main__":
    main()
