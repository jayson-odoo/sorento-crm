"""SCM M4 — cash-constraint ranking + greedy funding allocation (PURE maths).

This module is intentionally DB-free so the ranking + allocation logic is
golden-testable in isolation (``tests/scm/test_m4_cash.py``). The DB accessors
(load the active ``scm.cash_ranking_policy`` weights, persist rank_score/rank,
run the allocator over a run's buys) live in ``reorder_run_service`` +
``api/v1/scm/reorder_runs`` — this file only knows numbers.

Two deterministic pieces:

  * **rank_score (M4-D1/D14, graceful-degrade)** —
    ``rank_score = Σ(wᵢ·fᵢ) / Σ(wᵢ present)`` over the factors urgency, margin,
    abc, priority, committed. Each factor is normalized 0–1 and a factor with NO
    data is DROPPED from BOTH the numerator and the denominator (never zeroed), so
    a missing factor (e.g. margin on an uncosted SKU) never dilutes the score. The
    per-rec factor vector is returned for explainability (``rank_factors[]``).

  * **greedy funding allocation (M4-D2/D3/D16)** — over the buys ordered by rank,
    fund a buy only if its WHOLE ``cash_impact`` fits the remaining budget, else
    SKIP it and continue to the next that fits (MoQ = all-or-nothing); Σ funded
    cash ≤ budget. An UNCOSTED buy (``cash_impact`` None) can't be cash-ranked, so
    it is ``needs_cost`` — never funded/deferred, never draws from the budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

FACTOR_KEYS: tuple[str, ...] = ("urgency", "margin", "abc", "priority", "committed")

# Default weights seeded into scm.cash_ranking_policy (M4-D1: urgency + margin
# dominant). Chosen so a stockout-urgent, high-margin SKU floats to the top and
# ABC/priority/committed break ties; sums to 1.00. Documented in the plan.
DEFAULT_WEIGHTS: dict[str, float] = {
    "urgency": 0.40,
    "margin": 0.30,
    "abc": 0.15,
    "priority": 0.10,
    "committed": 0.05,
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
# per-factor normalizers (each returns a 0–1 value or None when unavailable)
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
    """``(list_price - unit_cost) / list_price``, clamped 0–1. PRESENT only when BOTH
    the chosen supplier's ``unit_cost`` AND the product's ``list_price`` exist
    (M4-D14) — otherwise DROPPED (never fabricated)."""
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
    """SO / demand priority normalized 0–1. No per-SKU SO-priority signal is wired in
    M4 Slice A, so this is absent (dropped) unless a caller supplies one."""
    if priority_signal is None:
        return None
    return _clamp(float(priority_signal))


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
) -> list[Factor]:
    """Build the ordered factor vector for one buy recommendation. A factor with no
    data lands as ``present=False`` (dropped by :func:`rank_score`)."""
    values = {
        "urgency": urgency_value(days_of_cover, net_position),
        "margin": margin_value(list_price, unit_cost),
        "abc": abc_value(abc_class),
        "priority": priority_value(priority_signal),
        "committed": committed_value(committed, forecast_daily_demand, lead_time_days),
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
    """Minimal shape the allocator needs — a ranked, (maybe) costed buy."""
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


def allocate_funding(buys: Sequence[Buy], budget: Optional[float]) -> AllocationResult:
    """Greedy-by-rank funding (M4-D2/D3/D16). Uncosted buys (``cash_impact`` None) →
    ``needs_cost`` and never touch the budget. Over the COSTED buys ordered by rank,
    fund a buy only if its whole cash_impact fits the remaining budget, else SKIP it
    and continue to the next that fits. Budget 0/None → all costed deferred; budget
    ≥ Σ costed → all costed funded. Σ funded cash ≤ budget."""
    ordered = sorted(buys, key=lambda b: (b.rank if b.rank is not None else 1 << 30))
    status: dict[str, str] = {}
    funded_count = deferred_count = needs_cost_count = 0
    funded_cash = deferred_cash = 0.0
    remaining = float(budget) if budget else 0.0
    has_budget = bool(budget and budget > 0)

    for b in ordered:
        if b.cash_impact is None:
            status[b.id] = "needs_cost"
            needs_cost_count += 1
            continue
        cost = float(b.cash_impact)
        if has_budget and cost <= remaining + 1e-9:
            remaining -= cost
            funded_cash += cost
            status[b.id] = "funded"
            funded_count += 1
        else:
            deferred_cash += cost
            status[b.id] = "deferred"
            deferred_count += 1

    return AllocationResult(
        status_by_id=status,
        funded_count=funded_count,
        deferred_count=deferred_count,
        needs_cost_count=needs_cost_count,
        funded_cash=round(funded_cash, 2),
        deferred_cash=round(deferred_cash, 2),
    )


def rank_sort_key(rank_score_val: float, cash_impact: Optional[float],
                  product_code: Optional[str]) -> tuple:
    """Deterministic ordering for dense rank assignment: highest rank_score first,
    tiebreak on higher cash_impact, then product_code (stable, reproducible)."""
    return (-(rank_score_val or 0.0), -(float(cash_impact) if cash_impact is not None else 0.0),
            str(product_code or ""))
