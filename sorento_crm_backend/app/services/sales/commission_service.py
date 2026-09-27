"""Commission per target period (plan 3.3; UAC S4-1 to S4-6; the owner's retest of 27 Sep).

Computed per period from the target's tiers, never stored:

- `marginal`: each tier's rate applies only to the slice of achievement between its threshold
  and the next tier's ("2% up to 100%, 4% above" pays 4% only on the part over target).
- `retroactive`: the highest tier reached sets the rate for the whole achievement.
- Bonuses: every tier whose `from_pct` is reached pays its `bonus_amount` once per period.
- `rate` is a % of the achieved amount on an amount target, RM per unit on a quantity target.
- Money is rounded half up to 2 dp once per period, after summing tiers.
- `none` returns null commission and bonus.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import List, NamedTuple, Optional, Sequence, Tuple

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


class Tier(NamedTuple):
    from_pct: Decimal
    rate: Decimal
    bonus_amount: Optional[Decimal]


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def commission_for(
    method: str,
    tiers: Sequence[Tier],
    target_value: Decimal,
    achieved: Decimal,
    *,
    metric: str = "amount",
) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """`(commission, bonus)` for one period, or `(None, None)` when the method is `none`."""
    if method == "none" or not tiers:
        return None, None
    ordered: List[Tier] = sorted(tiers, key=lambda t: t.from_pct)
    target_value = Decimal(target_value or 0)
    achieved = max(Decimal(achieved or 0), Decimal("0"))
    # A target of 0 is reached by any achievement.
    pct = HUNDRED if target_value <= 0 else achieved * HUNDRED / target_value

    def pay(rate: Decimal, base: Decimal) -> Decimal:
        return base * rate if metric == "quantity" else base * rate / HUNDRED

    reached = [t for t in ordered if pct >= t.from_pct]
    commission = Decimal("0")
    if method == "retroactive":
        if reached:
            commission = pay(reached[-1].rate, achieved)
    else:
        for index, tier in enumerate(ordered):
            low = tier.from_pct * target_value / HUNDRED
            high = (
                ordered[index + 1].from_pct * target_value / HUNDRED
                if index + 1 < len(ordered)
                else None
            )
            top = achieved if high is None else min(achieved, high)
            if top > low:
                commission += pay(tier.rate, top - low)
    bonus = sum((t.bonus_amount or Decimal("0") for t in reached), Decimal("0"))
    return _round(commission), _round(bonus)
