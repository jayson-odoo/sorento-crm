"""SCM M3 reorder engine — the deterministic core (no LLM, pure maths).

Turns M2's stored inputs (``scm.demand_stat``, ``scm.item_classification``,
``scm.supplier_performance``, ``product_suppliers``) + M1's net position
(``scm.net_position_v``) into reorder decisions — *when* (trigger) and *how much*
(qty) — driven by the resolved ``scm.reorder_policy`` ruleset. Produces buy +
disposition recommendation dicts (frozen inputs) reproducible without stat versioning.

Two layers:
  1. **Pure maths** (top of file) — take plain values, no I/O, golden-testable in
     isolation (``tests/scm/test_m3_engine.py`` asserts them against the blessed
     ``fixtures/golden_m3.json`` derived independently by
     ``scripts/scm_m3_golden_derive.py``). This is the TDD centrepiece.
  2. **Resolver** (bottom) — reads the M1/M2 tables the same way the dashboard does
     and feeds the pure maths (``tests/scm/test_m3_resolver.py``, Postgres savepoints).

The background run job that loops all planning SKUs and PERSISTS ``reorder_run`` +
``reorder_recommendation`` rows is a SEPARATE slice — this module only computes.

LOCKED formulae (UAC M3-D1..D5):
  SS(fixed_days)  = demand_rate * safety_days
  SS(statistical) = Z(service_level) * sqrt(LT * sigma_d^2 + demand^2 * var_LT),
                    sigma_d = demand_cv * demand_rate  (thin sample -> fixed_days fallback)
  ROP             = demand_rate * LT + SS
  order_up_to (S) = ROP + demand_rate * review_period_days ; min_max: S = max_override
  recommended_qty = S - net (0 when not triggered / non-positive)
  rounded_qty     = ceil(max(recommended, moq) / order_multiple) * order_multiple
  trigger         = reorder_point: net<=ROP ; periodic_review: on-cadence & net<S ;
                    min_max: net<=min_override ; reorder_level: net<=stored level
  network buy     = aggregate demand+net -> S_agg - net_agg (rounded) ; allocate
                    deficit-first then velocity-proportional surplus (sums to buy)
  confidence      = X & adequate -> high ; Z or thin sample -> low ; else medium
"""
from __future__ import annotations

import math
import uuid
from statistics import NormalDist
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.scm.cover_service import DEFAULT_COVER_SCOPE
from app.services.scm.money import BASE_CURRENCY, Rate, load_rates, to_base
from app.services.scm.reorder_policy import (
    DEFAULT_DEAD_STOCK_DAYS,
    DEFAULT_OVERSTOCK_DAYS,
    global_policy_row,
)

# --- locked engine defaults (seeded into the global policy; editable thereafter) ---
DEFAULT_SAFETY_DAYS = 7
DEFAULT_LEAD_TIME_DAYS = 30
DEFAULT_SERVICE_LEVEL = 0.95
DEFAULT_REVIEW_PERIOD_DAYS = 30
DEFAULT_FORECAST_WINDOW_DAYS = 90
# Cost leads. The business buys the same item from more than one supplier on 5,995 of its
# products, and the instruction is plain: "we should pick the cheapest one if got multiple
# suppliers". `is_primary` stays in the key as the tiebreak, so a nominated supplier still
# wins a tie on price - it just no longer wins on nomination alone. Overridable per policy
# via the `supplier_selection` toggle (`primary` / `best_score` / `lowest_cost`).
DEFAULT_SUPPLIER_SELECTION = "lowest_cost"

# Most-specific-wins ordering for policy resolution (SKU beats cell beats class beats global).
_SCOPE_RANK = {"sku": 3, "abc_xyz_cell": 2, "product_class": 1, "global": 0}

_SEED = "engine"


# ===========================================================================
# Pure maths — no I/O, golden-testable in isolation
# ===========================================================================

def z_score(service_level: Optional[float]) -> float:
    """Inverse-normal Z for a service level (0<sl<1). Deterministic via NormalDist."""
    sl = float(service_level) if service_level is not None else DEFAULT_SERVICE_LEVEL
    sl = min(max(sl, 1e-6), 1 - 1e-6)
    return NormalDist().inv_cdf(sl)


def resolve_policy(policies: list[dict[str, Any]], *, product_id: str,
                   abc_xyz_cell: Optional[str] = None,
                   product_class: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Most-specific ACTIVE policy for a SKU: sku > abc_xyz_cell > product_class > global.

    Ties within the same scope break on ``priority`` (higher wins), then ``scope_ref``
    for determinism. Returns ``None`` only when nothing matches (a seeded global always
    matches, so callers that ran ``ensure_reorder_policy_defaults`` get a policy).
    """
    active = [p for p in policies if p.get("is_active", True)]
    matches = [p for p in active
               if _policy_matches(p, product_id, abc_xyz_cell, product_class)]
    if not matches:
        return None
    matches.sort(
        key=lambda p: (_SCOPE_RANK.get(str(p.get("scope_type")), -1),
                       p.get("priority") or 0,
                       str(p.get("scope_ref") or "")),
        reverse=True,
    )
    return matches[0]


def _policy_matches(p: dict[str, Any], product_id: str, abc_xyz_cell: Optional[str],
                    product_class: Optional[str]) -> bool:
    st = p.get("scope_type")
    if st == "global":
        return True
    if st == "sku":
        return str(p.get("scope_ref")) == str(product_id)
    if st == "abc_xyz_cell":
        return abc_xyz_cell is not None and str(p.get("scope_ref")) == str(abc_xyz_cell)
    if st == "product_class":
        return product_class is not None and str(p.get("scope_ref")) == str(product_class)
    return False


def price_in_base(supplier: dict, rates: dict[str, Rate]) -> dict:
    """Stamp a candidate with its price expressed in the base currency.

    Two prices cannot be ranked until they are in the same money, and the book prices in
    four currencies. This adds the comparable figure WITHOUT touching `unit_cost` /
    `currency`, which stay as what the supplier charges and what the PO will say.

    A price we cannot convert gets `unit_cost_base = None` and `missing_rate_currency` set,
    so the ranking can hold it back from winning on a small number and the buyer is told
    which rate to enter. Mutates and returns the dict, because callers build these rows in
    a list comprehension and a copy here would silently drop later edits.
    """
    conv = to_base(_num(supplier.get("unit_cost")), supplier.get("currency"), rates)
    supplier["unit_cost_base"] = conv.amount
    supplier["base_currency"] = BASE_CURRENCY
    supplier["rate_to_base"] = conv.rate
    supplier["rate_as_of"] = conv.as_of
    supplier["missing_rate_currency"] = conv.missing_currency
    return supplier


def select_supplier(suppliers: list[dict], *,
                    selection: str = DEFAULT_SUPPLIER_SELECTION) -> dict:
    """Pick the sourcing supplier + attach ranked alternatives (AC-M3.5/3.6).

    Each supplier dict carries: ``supplier_id``, ``unit_cost``, ``lead_time_days``
    (measured-or-declared), ``composite_score``, ``is_primary`` (+ any extras the
    resolver freezes). Precedence by ``selection`` toggle:
      * ``primary``     (default): is_primary -> best composite_score -> lowest cost
      * ``best_score``: best composite_score -> is_primary -> lowest cost
      * ``lowest_cost``: lowest cost -> is_primary -> best composite_score
    Single supplier -> used. Empty -> flagged ``exception='no_supplier'`` (never a
    silent skip). ``alternatives`` = the ranked losers as {supplier_id, unit_cost,
    lead_time_days, composite_score}.
    """
    if not suppliers:
        return {"chosen": None, "alternatives": [], "exception": "no_supplier",
                "reason": {"basis": "no_supplier"}}
    # Ranking happens on the base-currency price, so a candidate nobody has priced yet gets
    # priced here with no rates: one carrying no currency is already in base money and is
    # unaffected (the pure-maths callers, whose figures are all one currency), while a
    # foreign price a caller supplied no rate for correctly becomes unrankable rather than
    # being compared at face value.
    for s in suppliers:
        if "unit_cost_base" not in s:
            price_in_base(s, {})
    ranked = sorted(suppliers, key=lambda s: _supplier_sort_key(s, selection))
    chosen = ranked[0]
    alternatives = [{
        "supplier_id": s.get("supplier_id"),
        "supplier_name": s.get("supplier_name"),
        "unit_cost": _num(s.get("unit_cost")),
        "currency": s.get("currency"),
        # The converted figure travels with the original so the popup can show both, and
        # so a reader can see WHICH number the ranking actually used.
        "unit_cost_base": _num(s.get("unit_cost_base")),
        "base_currency": s.get("base_currency") or BASE_CURRENCY,
        "missing_rate_currency": s.get("missing_rate_currency"),
        "unit_cost_source": s.get("unit_cost_source"),
        "lead_time_days": _num(s.get("lead_time_days")),
        "composite_score": _num(s.get("composite_score")),
    } for s in ranked[1:]]
    return {"chosen": chosen, "alternatives": alternatives, "exception": None,
            "reason": _selection_reason(chosen, ranked[1:], selection, ranked)}


def _selection_reason(chosen: dict, losers: list[dict], selection: str,
                      all_candidates: Optional[list[dict]] = None) -> dict:
    """Why this supplier, in a shape the decision popup can render without re-deriving it.

    Stated rather than implied, and never over-stated:

    * With nothing to compare against, "chosen because cheaper" is a fabrication, so a lone
      supplier says `only_supplier`.
    * A saving is quoted only when BOTH prices converted to the base currency. The gap to an
      unpriced runner-up is unknowable, and the gap to an unconvertible one is worse than
      unknowable - subtracting 10 CNY from 190 MYR produces a number that looks like money.
    * When NOTHING could be converted, `lowest_cost` is a claim we cannot support, so the
      basis reads `no_comparable_cost` and the missing currencies are named.
    """
    pool = all_candidates if all_candidates is not None else ([chosen] + list(losers))
    missing = sorted({s.get("missing_rate_currency") for s in pool
                      if s.get("missing_rate_currency")})

    if not losers:
        return {"basis": "only_supplier", "runner_up": None, "saving_per_unit": None,
                "compared_in": BASE_CURRENCY, "missing_rates": missing}

    comparable = [s for s in pool if _num(s.get("unit_cost_base")) is not None]
    basis = selection
    if selection == "lowest_cost" and not comparable:
        basis = "no_comparable_cost"

    runner_up = losers[0]
    ours, theirs = _num(chosen.get("unit_cost_base")), _num(runner_up.get("unit_cost_base"))
    return {
        "basis": basis,
        "runner_up": runner_up.get("supplier_name"),
        "runner_up_cost": _num(runner_up.get("unit_cost")),
        "runner_up_currency": runner_up.get("currency"),
        "runner_up_cost_base": theirs,
        "compared_in": BASE_CURRENCY,
        "missing_rates": missing,
        "saving_per_unit": (round(theirs - ours, 4)
                            if ours is not None and theirs is not None else None),
    }


def _supplier_sort_key(s: dict, selection: str):
    prim = 1 if s.get("is_primary") else 0
    sc = _num(s.get("composite_score"))
    # present-first (0), then higher score first (negate)
    sc_key = (0, -sc) if sc is not None else (1, 0.0)
    # Rank on the BASE-currency price, never the supplier's own figure: 45 USD is not
    # cheaper than 190 MYR, and a price in a currency we hold no rate for is not a bargain
    # at 10 - it is unknown, so it sorts with the unpriced rather than ahead of everything.
    uc = _num(s.get("unit_cost_base"))
    uc_key = (0, uc) if uc is not None else (1, 0.0)   # present-first, lower cost first
    # Final deterministic tiebreak: two suppliers tied on every ranking factor must
    # resolve to the SAME winner every call (never DB row order). supplier_id is stable.
    sid = str(s.get("supplier_id") or "")
    if selection == "best_score":
        return (sc_key, -prim, uc_key, sid)
    if selection == "lowest_cost":
        return (uc_key, -prim, sc_key, sid)
    return (-prim, sc_key, uc_key, sid)                # primary (default)


def lead_time(measured: Optional[float], declared: Optional[float], *,
              default: float = DEFAULT_LEAD_TIME_DAYS) -> tuple[float, str]:
    """measured (M2 supplier_performance) -> declared (product_suppliers) -> policy
    default; returns (days, source) so the fallback used is recorded (AC-M3.4)."""
    if measured is not None:
        return float(measured), "measured"
    if declared is not None:
        return float(declared), "declared"
    return float(default), "default"


def safety_stock(method: Optional[str], *, demand_rate: float,
                 safety_days: float = DEFAULT_SAFETY_DAYS,
                 service_level: float = DEFAULT_SERVICE_LEVEL,
                 cv_d: Optional[float] = None, var_lt: Optional[float] = None,
                 lead_time_days: float = DEFAULT_LEAD_TIME_DAYS,
                 manual_value: Optional[float] = None) -> tuple[float, str, Optional[str]]:
    """Safety stock by method. Returns (ss, method_used, fallback_note).

    ``statistical`` needs both demand variability (cv_d) and lead-time variance
    (var_lt) from M2; a thin sample (either None) FALLS BACK to fixed_days and records
    it (never emits a bogus statistical SS). ``manual`` uses the policy value, falling
    back to fixed_days when unset.
    """
    d = float(demand_rate or 0.0)
    if method == "statistical":
        if cv_d is None or var_lt is None:
            return d * float(safety_days), "fixed_days", (
                "statistical requested but demand/lead-time variance sample thin "
                "-> fixed_days fallback")
        sigma_d = float(cv_d) * d
        variance = float(lead_time_days) * sigma_d ** 2 + d ** 2 * float(var_lt)
        return z_score(service_level) * math.sqrt(max(variance, 0.0)), "statistical", None
    if method == "manual":
        if manual_value is None:
            return d * float(safety_days), "fixed_days", (
                "manual requested but no manual value -> fixed_days fallback")
        return float(manual_value), "manual", None
    return d * float(safety_days), "fixed_days", None


def reorder_point(demand_rate: float, lead_time_days: float, ss: float) -> float:
    return float(demand_rate) * float(lead_time_days) + float(ss)


def order_up_to(rop: float, demand_rate: float,
                review_days: float = DEFAULT_REVIEW_PERIOD_DAYS) -> float:
    return float(rop) + float(demand_rate) * float(review_days)


def trigger(policy_type: Optional[str], *, net: float, rop: Optional[float] = None,
            min_level: Optional[float] = None, oup: Optional[float] = None,
            on_cadence: bool = True,
            reorder_level: Optional[float] = None) -> tuple[bool, Optional[str]]:
    """Whether a buy fires + the human ``triggered_reason`` (AC-M3.7)."""
    n = float(net)
    if policy_type == "reorder_level":
        # The buyer's own number. No forecast term participates, by design: this basis exists
        # because forecast cover turned a 2-unit order into a 15.933 buy. A missing level is
        # NOT a level of zero - the caller emits the row as `needs_level` instead of planning
        # it, so an item nobody has set up is neither bought nor silently dropped.
        if reorder_level is None:
            return False, None
        if n <= float(reorder_level):
            return True, f"reorder_level: net {_g(n)} <= level {_g(reorder_level)}"
        return False, None
    if policy_type == "periodic_review":
        if on_cadence and oup is not None and n < float(oup):
            return True, f"periodic_review: net {_g(n)} < order-up-to {_g(oup)} on review cadence"
        return False, None
    if policy_type == "min_max":
        if min_level is not None and n <= float(min_level):
            return True, f"min_max: net {_g(n)} <= min {_g(min_level)}"
        return False, None
    if rop is not None and n <= float(rop):   # reorder_point (default)
        return True, f"reorder_point: net {_g(n)} <= ROP {_g(rop)}"
    return False, None


def order_qty(triggered: bool, *, net: float, oup: Optional[float],
              moq: Optional[float] = None,
              order_multiple: Optional[float] = None) -> tuple[float, float]:
    """(recommended_qty, rounded_qty). recommended = S - net (0 when not triggered or
    non-positive); rounded floors at moq then rounds UP to order_multiple (AC-M3.3)."""
    if not triggered or oup is None:
        return 0.0, 0.0
    recommended = float(oup) - float(net)
    if recommended <= 0:
        return 0.0, 0.0
    return recommended, round_order_qty(recommended, moq, order_multiple)


def round_order_qty(qty: float, moq: Optional[float],
                    order_multiple: Optional[float]) -> float:
    """Floor at moq, then round UP to the nearest order_multiple."""
    q = float(qty)
    if moq is not None and q < float(moq):
        q = float(moq)
    if order_multiple and float(order_multiple) > 0:
        m = float(order_multiple)
        q = math.ceil(q / m) * m
    return float(q)


def confidence(xyz_class: Optional[str], *, demand_adequate: bool = True,
               supplier_adequate: bool = True) -> str:
    """Deterministic (xyz x data-sufficiency) -> high|medium|low (AC-M3.12)."""
    adequate = bool(demand_adequate) and bool(supplier_adequate)
    if xyz_class == "X" and adequate:
        return "high"
    if xyz_class == "Z" or not adequate:
        return "low"
    return "medium"


def days_of_cover(net: float, demand_rate: Optional[float]) -> Optional[float]:
    """Forward cover = net / demand_rate; None when no demand or a deficit."""
    if not demand_rate or float(demand_rate) <= 0:
        return None
    if float(net) < 0:
        return None
    return float(net) / float(demand_rate)


# --- network aggregation + auto-allocation (AC-M3.8) -----------------------

def _apportion(total: int, weights: list[float]) -> list[int]:
    """Largest-remainder integer apportionment summing EXACTLY to ``total``."""
    n = len(weights)
    if n == 0:
        return []
    s = sum(weights)
    if s <= 0:
        base, rem = divmod(total, n)
        return [base + (1 if i < rem else 0) for i in range(n)]
    raw = [total * w / s for w in weights]
    floors = [int(math.floor(x)) for x in raw]
    rem = total - sum(floors)
    order = sorted(range(n), key=lambda i: (-(raw[i] - floors[i]), i))
    for k in range(rem):
        floors[order[k % n]] += 1
    return floors


def allocate(buy_qty: float, warehouses: list[dict]) -> dict[str, int]:
    """Split a network buy across warehouses: each warehouse's deficit first, then the
    rounding surplus velocity-proportional (by demand). When buy < Σdeficit the whole
    buy is apportioned proportional to deficit. Result sums EXACTLY to round(buy_qty).

    ``warehouses``: [{warehouse_id, deficit, demand_rate}].
    """
    total = int(round(float(buy_qty)))
    if total <= 0 or not warehouses:
        return {w["warehouse_id"]: 0 for w in warehouses}
    deficits = [max(float(w.get("deficit") or 0.0), 0.0) for w in warehouses]
    demands = [float(w.get("demand_rate") or 0.0) for w in warehouses]
    total_deficit = sum(deficits)
    if total <= total_deficit:
        weights = deficits                              # buy <= Σdeficit -> proportional to deficit
    else:
        # The rounding surplus (MOQ / pack multiple) goes ONLY to locations that were short.
        #
        # > "it won't go to brw-bb, only ordered for brw-bb will go into brw-bb"
        #
        # Spreading it velocity-proportionally across every member sent stock to bins sitting
        # in surplus that had ordered nothing. A pool lets a short bin BORROW from a sibling;
        # it never entitles the sibling to a share of the purchase.
        surplus = total - total_deficit
        short = [i for i in range(len(warehouses)) if deficits[i] > 0]
        if not short:
            # Nothing was short anywhere, so the buy exists purely as a minimum order. There
            # is no bin that asked for it; spread by demand so it lands where it will move.
            short = list(range(len(warehouses)))
        short_demand = sum(demands[i] for i in short)
        if short_demand > 0:
            extra = {i: surplus * demands[i] / short_demand for i in short}
        else:
            even = surplus / len(short)                 # no demand signal -> even among short
            extra = {i: even for i in short}
        weights = [deficits[i] + extra.get(i, 0.0) for i in range(len(warehouses))]
    parts = _apportion(total, weights)
    return {warehouses[i]["warehouse_id"]: parts[i] for i in range(len(warehouses))}


def aggregate_network(warehouses: list[dict], *, lead_time_days: float,
                      safety_days: float = DEFAULT_SAFETY_DAYS,
                      review_days: float = DEFAULT_REVIEW_PERIOD_DAYS,
                      moq: Optional[float] = None,
                      order_multiple: Optional[float] = None,
                      levels: Optional[dict[str, Optional[float]]] = None) -> dict:
    """Aggregate demand+net across warehouses, size one buy on the aggregate, and
    auto-allocate it (AC-M3.8). ``warehouses``: [{warehouse_id, demand_rate, net}].
    Uses fixed_days SS on the aggregate (network golden path).

    ``levels`` switches the target from the forecast order-up-to to the levels the buyer
    owns: the pool's target is the SUM of its members' levels, and each member's deficit is
    measured against its OWN level. A member with no level contributes nothing and can
    therefore receive nothing, which is what keeps a bin nobody has set up out of a purchase
    instead of guessing a number for it.
    """
    agg_demand = sum(float(w["demand_rate"]) for w in warehouses)
    agg_net = sum(float(w["net"]) for w in warehouses)
    ss = agg_demand * float(safety_days)
    if levels is not None:
        rop = sum(float(levels.get(w["warehouse_id"]) or 0.0) for w in warehouses)
        oup = rop
    else:
        rop = reorder_point(agg_demand, lead_time_days, ss)
        oup = order_up_to(rop, agg_demand, review_days)
    recommended = oup - agg_net
    buy = round_order_qty(recommended, moq, order_multiple) if recommended > 0 else 0.0
    per_wh = []
    for w in warehouses:
        d = float(w["demand_rate"])
        if levels is not None:
            rop_i = float(levels.get(w["warehouse_id"]) or 0.0)
        else:
            rop_i = reorder_point(d, lead_time_days, d * float(safety_days))
        per_wh.append({"warehouse_id": w["warehouse_id"],
                       "deficit": max(rop_i - float(w["net"]), 0.0),
                       "demand_rate": d, "reorder_point": rop_i})
    alloc = allocate(buy, per_wh)
    return {"agg_demand": agg_demand, "agg_net": agg_net, "safety_stock": ss,
            "reorder_point": rop, "order_up_to": oup, "recommended_qty": recommended,
            "buy_qty": buy, "warehouses": per_wh, "allocation": alloc}


# --- disposition + transfer flag (AC-M3.9) ---------------------------------

def disposition(*, on_hand: float, last_movement_days: Optional[float],
                dead_stock_days: float, days_of_cover_val: Optional[float],
                overstock_days: float,
                last_purchase_days: Optional[float] = None) -> Optional[dict]:
    """Dead (stale movement, or stock older than the window that has never moved) OR
    overstock (DoC > overstock_days) → a disposition rec. Dead takes precedence.
    ``None`` when neither applies.

    Two ways to be dead, and the rec says WHICH, because they are different evidence and
    a buyer acts differently on each:

    * ``movement`` - it moved, and the last time was longer ago than the window.
    * ``ageing`` - it has NEVER moved, and the stock sitting there was bought longer ago
      than the window. *"If I order from 5 years ago and now still got stock, this is not
      very hot selling"* - which is a fact about THIS stock rather than a statistic about
      demand, and is why it is stronger evidence than variance alone.

    The ageing branch is deliberately confined to the never-moved case. Without a purchase
    date there was no evidence either way there, so the rule abstained ("no consumption
    history is not the same as a stale movement") and a stocked-but-idle SKU was never
    flagged. The purchase-history feed supplies exactly that missing evidence, so the
    abstention is now only correct while the purchase date is ALSO unknown. A SKU that
    moved recently is not dead however old its last purchase is - that is a slow seller,
    and slow-but-selling is what the overstock check below is for.
    """
    if not on_hand or float(on_hand) <= 0:
        return None
    if last_movement_days is not None:
        if float(last_movement_days) > float(dead_stock_days):
            return {"type": "dead", "action": "discontinue_or_promo", "basis": "movement"}
    elif last_purchase_days is not None and float(last_purchase_days) > float(dead_stock_days):
        return {"type": "dead", "action": "discontinue_or_promo", "basis": "ageing"}
    if days_of_cover_val is not None and float(days_of_cover_val) > float(overstock_days):
        return {"type": "overstock", "action": "hold_or_promo", "basis": "cover"}
    return None


def transfer_flags(sku: str, warehouses: list[dict]) -> list[dict]:
    """Advisory transfer flags: same SKU overstock in one warehouse + short (net<ROP)
    in another → "consider transfer". Buy qty is UNCHANGED (netting deferred).

    ``warehouses``: [{warehouse_id, warehouse_code, overstock: bool, short: bool}].
    """
    over = [w for w in warehouses if w.get("overstock")]
    short = [w for w in warehouses if w.get("short")]
    flags: list[dict] = []
    for a in over:
        for b in short:
            if a["warehouse_id"] == b["warehouse_id"]:
                continue
            frm = a.get("warehouse_code") or a["warehouse_id"]
            to = b.get("warehouse_code") or b["warehouse_id"]
            flags.append({"sku": sku, "from_warehouse": frm, "to_warehouse": to,
                          "message": f"consider transfer {sku} {frm}→{to}"})
    return flags


def _num(v) -> Optional[float]:
    return float(v) if v is not None else None


def _g(v) -> str:
    return f"{float(v):g}"


# ===========================================================================
# Policy defaults (idempotent ensure — never rely on an empty policy table)
# ===========================================================================

def ensure_reorder_policy_defaults(db: Session) -> None:
    """Guarantee one GLOBAL ``scm.reorder_policy`` carrying the LOCKED M3 defaults.

    Idempotent: only inserts when no global row exists at all, so re-runs and
    hand-edited values are never clobbered. The two engine toggles that have no
    dedicated column — ``supplier_selection`` and ``lead_time_default_days`` — ride in
    the existing ``factor_toggles`` JSONB (no migration).
    """
    if global_policy_row(db) is not None:
        return
    toggles = ('{"supplier_selection": "%s", "lead_time_default_days": %d}'
               % (DEFAULT_SUPPLIER_SELECTION, DEFAULT_LEAD_TIME_DAYS))
    db.execute(text(
        "INSERT INTO scm.reorder_policy "
        "(id, scope_type, scope_ref, policy_type, service_level, safety_stock_method, "
        " safety_days, review_period_days, forecast_window_days, baseline_source, "
        " spike_handling, buy_scope, dead_stock_days, overstock_days, factor_toggles, "
        " cover_scope, is_active, priority, source_system, source_ref, created_at, updated_at) "
        "VALUES (:id, 'global', NULL, 'reorder_point', :sl, 'fixed_days', :sd, :rp, :fw, "
        " 'continuous_only', 'committed_only', 'network', :dsd, :osd, "
        " CAST(:toggles AS jsonb), :cover, true, 0, :src, 'defaults', now(), now())"
    ), {"id": str(uuid.uuid4()), "sl": DEFAULT_SERVICE_LEVEL, "sd": DEFAULT_SAFETY_DAYS,
        "rp": DEFAULT_REVIEW_PERIOD_DAYS, "fw": DEFAULT_FORECAST_WINDOW_DAYS,
        "dsd": DEFAULT_DEAD_STOCK_DAYS, "osd": DEFAULT_OVERSTOCK_DAYS,
        "toggles": toggles, "cover": DEFAULT_COVER_SCOPE, "src": _SEED})


# ===========================================================================
# Resolver — reads M1/M2 tables and feeds the pure maths
# ===========================================================================

def load_policies(db: Session) -> list[dict]:
    """All active reorder policies as plain dicts (for ``resolve_policy``)."""
    rows = db.execute(text(
        "SELECT id, scope_type, scope_ref, policy_type, service_level, safety_stock_method, "
        "safety_days, review_period_days, forecast_window_days, spike_handling, buy_scope, "
        "dead_stock_days, overstock_days, min_override, max_override, factor_toggles, "
        "pool_netting, cover_scope, level_study_months, level_cover_months, "
        "is_active, priority FROM scm.reorder_policy WHERE is_active = true"
    )).mappings().all()
    return [dict(r) for r in rows]


def policy_toggles(policy: Optional[dict]) -> dict:
    """Read the engine toggles that live in ``factor_toggles`` with locked defaults."""
    toggles = (policy or {}).get("factor_toggles") or {}
    if not isinstance(toggles, dict):
        toggles = {}
    return {
        "supplier_selection": toggles.get("supplier_selection", DEFAULT_SUPPLIER_SELECTION),
        "lead_time_default_days": toggles.get("lead_time_default_days", DEFAULT_LEAD_TIME_DAYS),
        "safety_stock_manual": toggles.get("safety_stock_manual"),
    }


def load_classification(db: Session, product_id: str,
                        warehouse_id: Optional[str]) -> Optional[dict]:
    row = db.execute(text(
        "SELECT abc_class, xyz_class, demand_cv FROM scm.item_classification "
        "WHERE product_id = :pid AND warehouse_id IS NOT DISTINCT FROM :wid"
    ), {"pid": product_id, "wid": warehouse_id}).mappings().first()
    return dict(row) if row else None


def load_demand(db: Session, product_id: str,
                warehouse_id: Optional[str]) -> Optional[dict]:
    row = db.execute(text(
        "SELECT avg_daily_demand, baseline_rate, spike_rate, demand_cv, sample_days, method "
        "FROM scm.demand_stat WHERE product_id = :pid AND warehouse_id IS NOT DISTINCT FROM :wid"
    ), {"pid": product_id, "wid": warehouse_id}).mappings().first()
    return dict(row) if row else None


def load_category_code(db: Session, product_id: str) -> Optional[str]:
    return db.execute(text(
        "SELECT pc.category_code FROM products p "
        "LEFT JOIN product_categories pc ON pc.id = p.category_id WHERE p.id = :pid"
    ), {"pid": product_id}).scalar()


def load_net_position(db: Session, product_id: str,
                      warehouse_id: Optional[str] = None) -> list[dict]:
    sql = ("SELECT product_id, warehouse_id, quantity_on_hand, on_order, committed, "
           "net_position FROM scm.net_position_v WHERE product_id = :pid")
    params: dict[str, Any] = {"pid": product_id}
    if warehouse_id is not None:
        sql += " AND warehouse_id = :wid"
        params["wid"] = warehouse_id
    return [dict(r) for r in db.execute(text(sql), params).mappings().all()]


def last_purchase_costs(db: Session, product_id: str) -> dict[str, dict]:
    """What we last PAID for this SKU, per supplier: {supplier_id: {cost, currency, ref, at}}.

    Evidence beats a typed figure. `product_suppliers.unit_cost` is a contract or a quote
    somebody entered; a purchase-order line is money that actually moved, so where both exist
    the order wins.

    Per SUPPLIER, never pooled. A price we paid supplier A does not price a buy from
    supplier B - putting it there would read as a quote from B, and it is not one.

    A line recording 0 is a price OF zero, and is kept: 637 lines in the customer's own order
    book are exactly that. Only the ABSENCE of a line means unknown, and unknown is `None`.
    Ordered by issue date with the row's own creation time as the tiebreak, because a book
    imported in one go shares an issue date and the order among those would otherwise be up
    to the planner.
    """
    rows = db.execute(text(
        "SELECT DISTINCT ON (po.supplier_id) po.supplier_id, pol.unit_cost, "
        "       COALESCE(pol.currency, po.currency) AS currency, "
        "       po.po_number, po.issue_date "
        "FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        # A price we cannot attribute to anybody is not a quote from anybody. 15 lines in
        # the customer's book sit on an order with no supplier; keyed by the missing id
        # they became the literal string "None", which then aborted the candidate query
        # for all 11 affected products - so the plan CRASHED on those SKUs rather than
        # merely knowing less about them.
        "WHERE pol.product_id = :pid AND pol.unit_cost IS NOT NULL "
        "  AND po.supplier_id IS NOT NULL "
        "ORDER BY po.supplier_id, po.issue_date DESC NULLS LAST, pol.created_at DESC"
    ), {"pid": product_id}).mappings().all()
    return {
        str(r["supplier_id"]): {
            "cost": _num(r["unit_cost"]),
            "currency": r["currency"],
            "ref": r["po_number"],
            "at": r["issue_date"],
        }
        for r in rows
    }


def load_supplier_candidates(db: Session, product_id: str,
                             *, default_lead: float = DEFAULT_LEAD_TIME_DAYS,
                             rates: Optional[dict[str, Rate]] = None) -> list[dict]:
    """Assemble the SKU's suppliers for ``select_supplier``, folding in the M2 measured
    lead-time / composite / variance (supplier×product row preferred, supplier-level
    fallback). Each dict carries declared + measured lead so ``lead_time`` precedence
    can be applied downstream, plus the price restated in the base currency so the
    candidates are actually comparable.

    ``rates`` is threaded in by the run (one read for thousands of SKUs) and read from the
    DB when a caller resolves a single SKU on its own.
    """
    rows = db.execute(text(
        "SELECT ps.supplier_id, su.supplier_code, su.supplier_name, "
        "ps.standard_lead_time_days, ps.moq, ps.order_multiple, ps.unit_cost, ps.currency, "
        "ps.is_primary_supplier, ps.lead_time_variability_days "
        "FROM product_suppliers ps JOIN suppliers su ON su.id = ps.supplier_id "
        "WHERE ps.product_id = :pid "
        "ORDER BY ps.supplier_id"          # deterministic load order (stable tie input)
    ), {"pid": product_id}).mappings().all()
    paid = last_purchase_costs(db, product_id)
    rates = load_rates(db) if rates is None else rates
    # A supplier we have BOUGHT this item from is a supplier for it, whether or not anybody
    # kept the `product_suppliers` row up to date. 3,070 such pairs exist in the customer's
    # book, each with a price we paid, and every one of them was invisible to the plan. They
    # join as candidates carrying no contract terms - no MOQ, no declared lead - so the lead
    # time falls back to measured-then-default exactly as it does for a contract row with a
    # blank lead.
    known = {str(r["supplier_id"]) for r in rows}
    # `sid` is cast to uuid[] below, so anything that is not one aborts the query for the
    # whole SKU rather than being skipped.
    extra = [sid for sid in paid if sid and sid != "None" and sid not in known]
    if extra:
        rows = list(rows) + [
            dict(er) for er in db.execute(text(
                "SELECT su.id AS supplier_id, su.supplier_code, su.supplier_name, "
                "       NULL::numeric AS standard_lead_time_days, NULL::numeric AS moq, "
                "       NULL::numeric AS order_multiple, NULL::numeric AS unit_cost, "
                "       NULL::varchar AS currency, FALSE AS is_primary_supplier, "
                "       NULL::numeric AS lead_time_variability_days "
                "FROM suppliers su WHERE su.id = ANY(CAST(:ids AS uuid[])) ORDER BY su.id"
            ), {"ids": extra}).mappings().all()
        ]
    out: list[dict] = []
    for r in rows:
        perf = _supplier_perf(db, r["supplier_id"], product_id)
        # The cascade, in one place: what we last paid this supplier, else the contract
        # figure, else nothing. `unit_cost_source` travels with it so a buyer can tell a
        # quote from a receipt, and `None` stays None rather than becoming a free item.
        last = paid.get(str(r["supplier_id"]))
        if last is not None and last["cost"] is not None:
            unit_cost = last["cost"]
            cost_source = "last_po"
            cost_currency = last["currency"] or r["currency"]
            cost_ref, cost_at = last["ref"], last["at"]
        elif _num(r["unit_cost"]) is not None:
            unit_cost = _num(r["unit_cost"])
            cost_source = "contract"
            cost_currency = r["currency"]
            cost_ref = cost_at = None
        else:
            unit_cost = None
            cost_source = None
            cost_currency = r["currency"]
            cost_ref = cost_at = None
        measured_lead = perf.get("avg_lead_time_days") if perf else None
        declared_lead = r["standard_lead_time_days"]
        lt_val, lt_src = lead_time(_num(measured_lead), _num(declared_lead),
                                   default=default_lead)
        out.append(price_in_base({
            "supplier_id": r["supplier_id"],
            "supplier_code": r["supplier_code"],
            "supplier_name": r["supplier_name"],
            "is_primary": bool(r["is_primary_supplier"]),
            "unit_cost": unit_cost,
            "unit_cost_source": cost_source,
            "unit_cost_ref": cost_ref,
            "unit_cost_at": cost_at,
            "currency": cost_currency,
            "moq": _num(r["moq"]),
            "order_multiple": _num(r["order_multiple"]),
            "declared_lead_time_days": _num(declared_lead),
            "measured_lead_time_days": _num(measured_lead),
            "lead_time_days": lt_val,
            "lead_time_source": lt_src,
            "lead_time_variance": _num(perf.get("lead_time_variance")) if perf else None,
            "declared_lead_variability": _num(r["lead_time_variability_days"]),
            "composite_score": _num(perf.get("composite_score")) if perf else None,
            "supplier_sample_size": (perf.get("sample_size") if perf else None),
            "supplier_confidence": (perf.get("confidence") if perf else None),
        }, rates))
    return out


def _supplier_perf(db: Session, supplier_id: str, product_id: str) -> Optional[dict]:
    """supplier×product scorecard, falling back to the supplier-level (product NULL) row."""
    row = db.execute(text(
        "SELECT avg_lead_time_days, lead_time_variance, composite_score, sample_size, confidence "
        "FROM scm.supplier_performance WHERE supplier_id = :sid AND product_id = :pid"
    ), {"sid": supplier_id, "pid": product_id}).mappings().first()
    if row:
        return dict(row)
    row = db.execute(text(
        "SELECT avg_lead_time_days, lead_time_variance, composite_score, sample_size, confidence "
        "FROM scm.supplier_performance WHERE supplier_id = :sid AND product_id IS NULL"
    ), {"sid": supplier_id}).mappings().first()
    return dict(row) if row else None


def resolve_supplier_for_sku(db: Session, product_id: str, *,
                             selection: str = DEFAULT_SUPPLIER_SELECTION,
                             default_lead: float = DEFAULT_LEAD_TIME_DAYS,
                             rates: Optional[dict[str, Rate]] = None) -> dict:
    """DB-backed ``select_supplier``: read the SKU's product_suppliers + M2 scores and
    pick the sourcing supplier (or flag the no-supplier exception)."""
    return select_supplier(
        load_supplier_candidates(db, product_id, default_lead=default_lead, rates=rates),
        selection=selection)


def resolve_policy_for_sku(db: Session, product_id: str,
                           warehouse_id: Optional[str] = None,
                           policies: Optional[list[dict]] = None) -> Optional[dict]:
    """DB-backed ``resolve_policy``: read the SKU's classification cell + product class
    and pick the most-specific active policy."""
    policies = policies if policies is not None else load_policies(db)
    cls = load_classification(db, product_id, warehouse_id)
    cell = None
    if cls and cls.get("abc_class") and cls.get("xyz_class"):
        cell = f"{cls['abc_class']}-{cls['xyz_class']}"
    category = load_category_code(db, product_id)
    return resolve_policy(policies, product_id=product_id, abc_xyz_cell=cell,
                          product_class=category)
