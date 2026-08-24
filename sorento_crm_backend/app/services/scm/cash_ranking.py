"""SCM M4 - cash-constraint ranking + greedy funding allocation (PURE maths).

This module is intentionally DB-free so the ranking + allocation logic is
golden-testable in isolation (``tests/scm/test_m4_cash.py``). The DB accessors
(load the active ``scm.cash_ranking_policy`` weights, persist rank_score/rank,
run the allocator over a run's buys) live in ``reorder_run_service`` +
``api/v1/scm/reorder_runs`` - this file only knows numbers.

Two deterministic pieces:

  * **rank_score (M4-D1/D14, graceful-degrade)**  - 
    ``rank_score = Σ(wᵢ·fᵢ) / Σ(wᵢ present)`` over the factors urgency, margin,
    abc, priority, committed. Each factor is normalized 0 - 1 and a factor with NO
    data is DROPPED from BOTH the numerator and the denominator (never zeroed), so
    a missing factor (e.g. margin on an uncosted SKU) never dilutes the score. The
    per-rec factor vector is returned for explainability (``rank_factors[]``).

  * **greedy funding allocation (M4-D2/D3/D16)** - over the buys ordered by rank,
    fund a buy only if its WHOLE ``cash_impact`` fits the remaining budget, else
    SKIP it and continue to the next that fits (MoQ = all-or-nothing); Σ funded
    cash ≤ budget. An UNCOSTED buy (``cash_impact`` None) can't be cash-ranked, so
    it is ``needs_cost`` - never funded/deferred, never draws from the budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Collection, Optional, Sequence

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

FACTOR_KEYS: tuple[str, ...] = (
    "urgency", "margin", "abc", "priority", "committed", "market",
)

# Default weights seeded into scm.cash_ranking_policy (M4-D1: urgency + margin
# dominant). Chosen so a stockout-urgent, high-margin SKU floats to the top and
# ABC/priority/committed break ties. `market` (M7) is a modest, CONFIGURABLE
# tie-breaker and is DROPPED entirely unless a run opts in AND a signal matches, so
# its presence never dilutes a run without market signals. (Weights need not sum to
# 1 - rank_score normalizes by the present weights.)
DEFAULT_WEIGHTS: dict[str, float] = {
    "urgency": 0.40,
    "margin": 0.30,
    "abc": 0.15,
    "priority": 0.10,
    "committed": 0.05,
    "market": 0.10,
}

# Days-of-cover horizon for the urgency map: a SKU with >= this cover is 0 urgency,
# a stockout is 1.0, linear in between. 60d ≈ a typical replenishment horizon.
URGENCY_HORIZON = 60.0

_ABC_VALUE = {"A": 1.0, "B": 0.66, "C": 0.33}


# ---------------------------------------------------------------------------
# factor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Factor:
    """One weighted, normalized ranking factor. ``present=False`` ⇒ dropped from
    both sums (graceful degrade); ``value`` is then None."""
    key: str
    weight: float
    value: Optional[float]
    present: bool

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "weight": self.weight, "value": self.value,
                "present": self.present}


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


# ---------------------------------------------------------------------------
# per-factor normalizers (each returns a 0 - 1 value or None when unavailable)
# ---------------------------------------------------------------------------

def urgency_value(days_of_cover: Optional[float],
                  net_position: Optional[float]) -> Optional[float]:
    """Lower days-of-cover ⇒ higher urgency; a stockout (net ≤ 0 or DoC ≤ 0) = 1.0.
    ``urgency = clamp(1 - days_of_cover / URGENCY_HORIZON, 0, 1)``. None only when
    neither DoC nor net is derivable (in practice always present on a planning rec)."""
    if (net_position is not None and net_position <= 0) or \
       (days_of_cover is not None and days_of_cover <= 0):
        return 1.0
    if days_of_cover is None:
        return None
    return _clamp(1.0 - float(days_of_cover) / URGENCY_HORIZON)


def margin_value(list_price: Optional[float],
                 unit_cost: Optional[float]) -> Optional[float]:
    """``(list_price - unit_cost) / list_price``, clamped 0 - 1. PRESENT only when BOTH
    the chosen supplier's ``unit_cost`` AND the product's ``list_price`` exist
    (M4-D14) - otherwise DROPPED (never fabricated)."""
    if list_price is None or unit_cost is None:
        return None
    lp = float(list_price)
    if lp <= 0:
        return None
    return _clamp((lp - float(unit_cost)) / lp)


def abc_value(abc_class: Optional[str]) -> Optional[float]:
    """A → 1.0, B → 0.66, C → 0.33, unclassified → absent."""
    if not abc_class:
        return None
    return _ABC_VALUE.get(str(abc_class).upper())


def priority_value(priority_signal: Optional[float]) -> Optional[float]:
    """SO / demand priority normalized 0 - 1. No per-SKU SO-priority signal is wired in
    M4 Slice A, so this is absent (dropped) unless a caller supplies one."""
    if priority_signal is None:
        return None
    return _clamp(float(priority_signal))


_MARKET_TREND_BASE = {"up": 1.0, "flat": 0.5, "down": 0.0}


def market_value(trend: Optional[str],
                 strength: Optional[float] = None) -> Optional[float]:
    """Market-trend priority signal (M7), SYMMETRIC: ``up`` raises priority, ``down``
    lowers it, ``flat`` is neutral. ``None``/unknown trend ⇒ absent (DROPPED - never
    fabricated). An optional ``strength`` (0 - 1, e.g. a normalized % move) scales the
    signal toward its extreme so a strong trend counts more than a faint one:
    up = 0.5 + 0.5·s, down = 0.5 − 0.5·s, flat stays 0.5."""
    if trend is None:
        return None
    base = _MARKET_TREND_BASE.get(str(trend).lower())
    if base is None:
        return None
    if strength is None:
        return base
    s = _clamp(float(strength))
    if base >= 1.0:
        return _clamp(0.5 + 0.5 * s)
    if base <= 0.0:
        return _clamp(0.5 - 0.5 * s)
    return 0.5


def committed_value(committed: Optional[float],
                    forecast_daily_demand: Optional[float],
                    lead_time_days: Optional[float]) -> Optional[float]:
    """Committed-vs-forecast pressure: committed units relative to lead-time demand,
    ``clamp(committed / (forecast_daily_demand · lead_time_days), 0, 1)``. Absent
    when committed, forecast, or lead time is not derivable."""
    if committed is None or not forecast_daily_demand or forecast_daily_demand <= 0 \
            or not lead_time_days or lead_time_days <= 0:
        return None
    lead_demand = float(forecast_daily_demand) * float(lead_time_days)
    if lead_demand <= 0:
        return None
    return _clamp(float(committed) / lead_demand)


# ---------------------------------------------------------------------------
# factor vector + score
# ---------------------------------------------------------------------------

def build_factors(
    weights: dict[str, float],
    *,
    days_of_cover: Optional[float] = None,
    net_position: Optional[float] = None,
    list_price: Optional[float] = None,
    unit_cost: Optional[float] = None,
    abc_class: Optional[str] = None,
    committed: Optional[float] = None,
    forecast_daily_demand: Optional[float] = None,
    lead_time_days: Optional[float] = None,
    priority_signal: Optional[float] = None,
    market_signal_value: Optional[float] = None,
) -> list[Factor]:
    """Build the ordered factor vector for one buy recommendation. A factor with no
    data lands as ``present=False`` (dropped by :func:`rank_score`).

    ``market_signal_value`` (M7) is the already-normalized market-trend priority
    (from :func:`market_value`); ``None`` ⇒ the market factor is dropped, so a run
    without market signals scores exactly as pre-M7."""
    values = {
        "urgency": urgency_value(days_of_cover, net_position),
        "margin": margin_value(list_price, unit_cost),
        "abc": abc_value(abc_class),
        "priority": priority_value(priority_signal),
        "committed": committed_value(committed, forecast_daily_demand, lead_time_days),
        "market": market_signal_value,
    }
    out: list[Factor] = []
    for key in FACTOR_KEYS:
        v = values[key]
        w = float(weights.get(key, 0.0) or 0.0)
        out.append(Factor(key=key, weight=w, value=v, present=v is not None))
    return out


def rank_score(factors: Sequence[Factor]) -> float:
    """``Σ(wᵢ·vᵢ) / Σ(wᵢ present)`` over the PRESENT factors only (graceful degrade).
    Returns 0.0 when no factor is present."""
    num = 0.0
    den = 0.0
    for f in factors:
        if not f.present or f.value is None:
            continue
        num += f.weight * f.value
        den += f.weight
    return num / den if den > 0 else 0.0


def days_to_stockout(net_position: Optional[float],
                     forecast_daily_demand: Optional[float],
                     days_of_cover: Optional[float]) -> Optional[float]:
    """Days until this SKU stocks out at forecast demand (M4-D4). Prefers the frozen
    days-of-cover; falls back to ``max(net, 0) / forecast``. None when not derivable."""
    if days_of_cover is not None:
        return round(float(days_of_cover), 2)
    if forecast_daily_demand and forecast_daily_demand > 0 and net_position is not None:
        return round(max(float(net_position), 0.0) / float(forecast_daily_demand), 2)
    return None


# ---------------------------------------------------------------------------
# greedy funding allocation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Buy:
    """Minimal shape the allocator needs - a ranked, (maybe) costed buy."""
    id: str
    rank: Optional[int]
    cash_impact: Optional[float]


@dataclass(frozen=True)
class AllocationResult:
    status_by_id: dict[str, str]        # rec_id → funded | deferred | needs_cost
    funded_count: int
    deferred_count: int
    needs_cost_count: int
    funded_cash: float
    deferred_cash: float


# ---------------------------------------------------------------------------
# generic scarce-capacity allocation
#
# Cash is not the only scarce thing a plan is cut by. A container runs out of VOLUME,
# and an arriving shipment runs out of QUANTITY, and both want the same decision:
# rank the candidates, fill until the capacity is gone, and say why each loser lost.
# So the greedy core lives here once and `allocate_funding` is a thin adapter over it.
#
# The one real difference is divisibility. A buy is all-or-nothing because of MOQ, so a
# buy that does not fit is SKIPPED and the allocator moves on. A container line can be
# part-loaded, so it takes the remainder instead. That is the `divisible` flag and it is
# the only behavioural fork; everything else (rank order, pins, rejects, the unmeasured
# bucket, the epsilon, the rounding) is shared.
#
# Guarded by tests/scm/test_capacity_allocator_parity.py: 1,152 snapshotted scenarios
# must stay byte-identical for the cash path. A failure there means this refactor is
# wrong, not that the snapshot is stale.
# ---------------------------------------------------------------------------

ALLOCATED = "allocated"
PARTIAL = "partial"
DEFERRED = "deferred"
UNMEASURED = "unmeasured"


@dataclass(frozen=True)
class CapacityItem:
    """A ranked candidate competing for a scarce capacity.

    ``demand`` is how much of the capacity it wants, in whatever unit the capacity is
    measured in - ringgit, cubic metres, units. ``None`` means unmeasured: we cannot
    rank it against a capacity we cannot compare it to, so it is parked rather than
    guessed at (an uncosted buy, a shipment line with no volume on file).
    """

    id: str
    rank: Optional[int]
    demand: Optional[float]
    divisible: bool = False


@dataclass(frozen=True)
class CapacityResult:
    status_by_id: dict[str, str]
    granted_by_id: dict[str, float]
    granted_total: float
    deferred_total: float
    granted_count: int
    partial_count: int
    deferred_count: int
    unmeasured_count: int


def allocate_capacity(
    items: Sequence[CapacityItem],
    capacity: Optional[float],
    *,
    pinned_ids: Optional[Collection[str]] = None,
    excluded_ids: Optional[Collection[str]] = None,
    uncapped: bool = False,
    precision: int = 2,
) -> CapacityResult:
    """Greedy-by-rank allocation of one scarce capacity, with a manual-override layer.

    Buckets, in order:

    * **excluded** - out of every bucket, absent from the result, never draws capacity.
    * **unmeasured** (``demand`` None) - parked as ``unmeasured``; never granted, never
      deferred, never draws capacity, EVEN when pinned. A pin cannot fund an unknown.
    * **pinned** (measured) - force-granted and consume capacity FIRST, staying granted
      even past the cap, so a pin never loses on a cut and the caller's free figure can
      legitimately go negative.
    * **un-pinned** (measured) - fill the leftover by rank. An indivisible item is granted
      only if it fits whole, else skipped and the next is tried. A divisible item takes the
      remainder and is marked ``partial``.

    ``uncapped`` (or ``capacity is None``) grants everything measured: the daily-cron path.
    """
    pinned = set(pinned_ids or ())
    excluded = set(excluded_ids or ())
    no_cap = uncapped or capacity is None
    ordered = sorted(items, key=lambda i: (i.rank if i.rank is not None else 1 << 30))

    status: dict[str, str] = {}
    granted: dict[str, float] = {}
    granted_total = deferred_total = 0.0

    measured: list[CapacityItem] = []
    for it in ordered:
        if it.id in excluded:
            continue
        if it.demand is None:
            status[it.id] = UNMEASURED
            continue
        measured.append(it)

    if no_cap:
        for it in measured:
            want = float(it.demand)  # type: ignore[arg-type]
            status[it.id] = ALLOCATED
            granted[it.id] = want
            granted_total += want
    else:
        has_capacity = bool(capacity and capacity > 0)
        remaining = float(capacity) if capacity else 0.0

        for it in measured:
            if it.id not in pinned:
                continue
            want = float(it.demand)  # type: ignore[arg-type]
            remaining -= want
            granted_total += want
            granted[it.id] = want
            status[it.id] = ALLOCATED

        for it in measured:
            if it.id in pinned:
                continue
            want = float(it.demand)  # type: ignore[arg-type]
            if has_capacity and want <= remaining + 1e-9:
                remaining -= want
                granted_total += want
                granted[it.id] = want
                status[it.id] = ALLOCATED
            elif it.divisible and has_capacity and remaining > 1e-9:
                # Take what is left. This is the container case: a part-loaded line is a
                # real outcome, not a failure, and the shortfall is what gets deferred.
                part = remaining
                remaining = 0.0
                granted_total += part
                granted[it.id] = part
                deferred_total += want - part
                status[it.id] = PARTIAL
            else:
                deferred_total += want
                granted[it.id] = 0.0
                status[it.id] = DEFERRED

    return CapacityResult(
        status_by_id=status,
        granted_by_id={k: round(v, precision) for k, v in granted.items()},
        granted_total=round(granted_total, precision),
        deferred_total=round(deferred_total, precision),
        granted_count=sum(1 for s in status.values() if s == ALLOCATED),
        partial_count=sum(1 for s in status.values() if s == PARTIAL),
        deferred_count=sum(1 for s in status.values() if s == DEFERRED),
        unmeasured_count=sum(1 for s in status.values() if s == UNMEASURED),
    )


def allocate_funding(
    buys: Sequence[Buy],
    budget: Optional[float],
    *,
    pinned_ids: Optional[Collection[str]] = None,
    rejected_ids: Optional[Collection[str]] = None,
    full: bool = False,
) -> AllocationResult:
    """Greedy-by-rank funding with a manual-override layer (M4-D2/D3/D16 + M8-C2/C3/C7).

    Buckets, in the exact order the FE ``computeFundingM8`` applies them so the persisted
    split matches the live client split for the same pins/rejects/budget. (The FE also has a
    live-view-only ``forcedOver`` - manual drag-to-defer - staging concept that has NO
    counterpart here: it is not persisted on confirm, so it never affects this split. A row
    dragged-to-defer that is not rejected reverts to funded on reload - known limitation.)

    * **rejected** (``rejected_ids``) - excluded from EVERY bucket; they never appear in
      ``status_by_id`` and never draw from the budget (as if they were not in the plan).
    * **uncosted** (``cash_impact`` None) - always ``needs_cost``; never funded/deferred,
      never touches the budget - EVEN when pinned (a pin can't fund an unknown cost).
    * **pinned** (``pinned_ids``, costed) - force-funded and consume the budget FIRST; they
      stay funded even when their total exceeds the budget (so ``funded_cash`` can exceed
      ``budget`` and the caller's free figure goes negative - a pin never defers on a cut).
    * **un-pinned** (costed) - greedily fill the LEFTOVER budget by rank: fund a buy only if
      its whole ``cash_impact`` fits the remaining budget, else SKIP and continue; the rest
      defer. Budget 0/None-with-no-full → un-pinned all defer.

    **Full budget** (``full=True`` or ``budget is None``) - the daily-cron path: every costed,
    non-rejected buy funds (uncosted still ``needs_cost``); nothing defers. NOTE this INVERTS
    the pre-M8 ``budget=None`` meaning ('fund nothing'); the only caller that passed None
    (the live-view route) guards ``budget is not None`` before calling, so nothing breaks.
    """
    # Cash is the INDIVISIBLE case of `allocate_capacity`: MOQ means a buy either fits
    # whole or is skipped, so `divisible` stays False and no buy is ever part-funded.
    # This function keeps its own vocabulary (funded / deferred / needs_cost) because three
    # callers and the FE contract depend on those exact strings; only the maths is shared.
    res = allocate_capacity(
        [CapacityItem(id=b.id, rank=b.rank, demand=b.cash_impact, divisible=False) for b in buys],
        budget,
        pinned_ids=pinned_ids,
        excluded_ids=rejected_ids,
        uncapped=full,
        precision=2,
    )

    _CASH_STATUS = {ALLOCATED: "funded", DEFERRED: "deferred", UNMEASURED: "needs_cost"}
    status = {k: _CASH_STATUS[v] for k, v in res.status_by_id.items()}

    return AllocationResult(
        status_by_id=status,
        funded_count=res.granted_count,
        deferred_count=res.deferred_count,
        needs_cost_count=res.unmeasured_count,
        funded_cash=res.granted_total,
        deferred_cash=res.deferred_total,
    )


def rank_sort_key(rank_score_val: float, cash_impact: Optional[float],
                  product_code: Optional[str]) -> tuple:
    """Deterministic ordering for dense rank assignment: highest rank_score first,
    tiebreak on higher cash_impact, then product_code (stable, reproducible)."""
    return (-(rank_score_val or 0.0), -(float(cash_impact) if cash_impact is not None else 0.0),
            str(product_code or ""))
