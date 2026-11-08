"""Commission per target period (plan 3.3; UAC S4-1 to S4-6; the owner's retest of 27 Sep), the
one engine for agent, team and dealer targets (lane SALES-TARGET-DEALER, owner rulings 16 Oct).

Computed per period from the target's tiers, never stored:

- `marginal`: each tier's rate applies only to the slice of achievement between its threshold
  and the next tier's ("2% up to 100%, 4% above" pays 4% only on the part over target).
- `retroactive`: the highest tier reached sets the rate for the whole achievement; the tiers
  below and above it play no part (Q2).
- Thresholds: `pct` (a tier's `from_pct` of the period's target figure, the original tiers),
  `amount` (a fixed RM, or units on a quantity target) or `points` (points x the RM-per-point
  ratio in force on the period's last day, Q4; no ratio = no tier reachable).
- A main tier's Additional (lane TARGET-TIER-ADDITIONAL, owner 5 Nov): `additional_rate` (a %,
  RM per unit on a quantity target) or a fixed RM (`bonus_amount`). Only the REACHED tier's
  Additional pays, never a lower tier's (this replaces the 16 Oct Q5 stacking). The % is its own
  line, paid on every account the tier pays, each account rounded on its own.
- Legacy "+ Additional" rows (`is_additional`) still pay their own rate when their own threshold
  is reached and stack, until `fold_additionals` moves them onto their tier; a row it cannot place
  keeps paying that way.
- A tier pays its `rate` on every counted account, or with `account_rates` only on the accounts
  it names, each at its own rate (ruling 2). `achieved` maps an account to its achievement; an
  agent or team target passes a single bucket.
- Rounding: every line (the main tier, each additional tier) and each account's amount on a
  line is rounded half up on its own, then added, never one combined rate (ruling 3). The unit
  is the target's: sen (0.01, default) or ringgit (1). The marginal main line is the sum of its
  slices, rounded once, as before.
- Bonus (the RM Additional): the reached main tier's, once per period, per account like the
  rate (owner 8 Nov, Q3): each account's own `account_bonuses` figure, else `bonus_amount` to each
  counted account (once on an agent or team target, which has one bucket).
- Each account's share (`Payout.by_account`, lane TARGET-PER-ACCOUNT-PAYOUT, owner 8 Nov): every
  account of a dealer target is its own payee and earns its own amounts on every line. Marginal:
  the tier boundaries are on the combined total; each slice is shared by the accounts in
  proportion to their sales, each paying its own rate on its part. Shares add up to commission
  + bonus.
- `rate` is a % of the achieved amount on an amount target, RM per unit on a quantity target.
- `none` returns null commission and bonus.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Hashable, List, NamedTuple, Optional, Sequence, Tuple

CENT = Decimal("0.01")
HUNDRED = Decimal("100")
UNITS = {"sen": CENT, "ringgit": Decimal("1")}


class Tier(NamedTuple):
    from_pct: Optional[Decimal]
    rate: Optional[Decimal]
    bonus_amount: Optional[Decimal]
    #: RM, units or points, when the target's threshold unit is not `pct`.
    threshold: Optional[Decimal] = None
    is_additional: bool = False
    #: account -> rate. None: `rate` on every counted account.
    account_rates: Optional[Dict[Hashable, Decimal]] = None
    #: The tier's % Additional, paid on top of `rate` when this is the reached tier.
    additional_rate: Optional[Decimal] = None
    #: account -> its own fixed RM Additional (owner 8 Nov, Q3). None: `bonus_amount` to each
    #: counted account (once on an agent or team target).
    account_bonuses: Optional[Dict[Hashable, Decimal]] = None


class PayLine(NamedTuple):
    kind: str  # `main` or `additional`
    #: The threshold in RM (units on a quantity target) this line reached.
    threshold_rm: Optional[Decimal]
    amount: Decimal


class Payout(NamedTuple):
    commission: Optional[Decimal]
    bonus: Optional[Decimal]
    lines: List[PayLine]
    #: 1-based position of the main tier reached among the main tiers, None below the first.
    tier_reached: Optional[int]
    ratio_missing: bool
    #: Each account's share of commission + bonus (lane TARGET-PER-ACCOUNT-PAYOUT, owner 8 Nov:
    #: every account of a dealer target is its own payee). Adds up to commission + bonus.
    by_account: Optional[Dict[Hashable, Decimal]] = None


def _round(value: Decimal, unit: Decimal = CENT) -> Decimal:
    return value.quantize(unit, rounding=ROUND_HALF_UP)


def threshold_in_rm(
    tier: Tier,
    threshold_unit: str,
    target_value: Decimal,
    rm_per_point: Optional[Decimal],
) -> Optional[Decimal]:
    """The tier's threshold in RM (units on a quantity target); None when it cannot be known."""
    if threshold_unit == "pct":
        if tier.from_pct is None:
            return None
        return Decimal(tier.from_pct) * target_value / HUNDRED
    if tier.threshold is None:
        return None
    if threshold_unit == "points":
        return None if rm_per_point is None else Decimal(tier.threshold) * Decimal(rm_per_point)
    return Decimal(tier.threshold)


def payout_for(
    method: str,
    tiers: Sequence[Tier],
    target_value: Decimal,
    achieved: Dict[Hashable, Decimal],
    *,
    metric: str = "amount",
    threshold_unit: str = "pct",
    rm_per_point: Optional[Decimal] = None,
    rounding: str = "sen",
) -> Payout:
    """The period's payout from its tiers and its achievement per account."""
    ratio_missing = threshold_unit == "points" and rm_per_point is None
    if method == "none" or not tiers:
        return Payout(None, None, [], None, ratio_missing, {})
    unit = UNITS.get(rounding, CENT)
    target_value = Decimal(target_value or 0)
    by_account = {key: max(Decimal(v or 0), Decimal("0")) for key, v in achieved.items()}
    total = sum(by_account.values(), Decimal("0"))

    def pay(rate: Decimal, base: Decimal) -> Decimal:
        return base * rate if metric == "quantity" else base * rate / HUNDRED

    shares: Dict[Hashable, Decimal] = {key: Decimal("0") for key in by_account}

    def line_amount(tier: Tier, extra: Optional[Decimal] = None) -> Decimal:
        # Each account's amount rounded on its own, then added (ruling 3); each account keeps
        # its own amount as its share (owner 8 Nov). `extra`: pay this rate instead, on the
        # same accounts the tier pays (its Additional).
        if extra is not None:
            keys = by_account.keys() if tier.account_rates is None else tier.account_rates.keys()
            rates = {key: Decimal(extra) for key in keys}
        elif tier.account_rates is not None:
            rates = {key: Decimal(rate) for key, rate in tier.account_rates.items()}
        else:
            rates = {key: Decimal(tier.rate or 0) for key in by_account}
        amount = Decimal("0")
        for key, rate in rates.items():
            each = _round(pay(rate, by_account.get(key, Decimal("0"))), unit)
            shares[key] = shares.get(key, Decimal("0")) + each
            amount += each
        return amount

    def at(tier: Tier) -> Optional[Decimal]:
        return threshold_in_rm(tier, threshold_unit, target_value, rm_per_point)

    def reached(tier: Tier) -> bool:
        low = at(tier)
        if low is None:
            return False
        # A target of 0 counts as 100% achieved (pct tiers, as before).
        if threshold_unit == "pct" and target_value <= 0:
            return Decimal(tier.from_pct) <= HUNDRED
        return total >= low

    main = sorted(
        (t for t in tiers if not t.is_additional),
        key=lambda t: (at(t) is None, at(t) or Decimal("0")),
    )
    lines: List[PayLine] = []
    hit = [i for i, t in enumerate(main) if reached(t)]
    tier_reached = hit[-1] + 1 if hit else None
    if method == "retroactive":
        if hit:
            top = main[hit[-1]]
            lines.append(PayLine("main", _rm(at(top)), line_amount(top)))
    else:
        # Marginal: one line. The boundaries are on the combined total; each slice of it is
        # shared by the accounts in proportion to their sales, each account paying its own rate
        # for the tier on its part, its slices added then rounded once (owner 8 Nov, Q3). One
        # bucket (agent, team): the slices themselves, rounded once, as before.
        own: Dict[Hashable, Decimal] = {}
        for index, tier in enumerate(main):
            low = at(tier)
            if low is None:
                continue
            high = at(main[index + 1]) if index + 1 < len(main) else None
            top = total if high is None else min(total, high)
            if top <= low:
                continue
            for key, sales in by_account.items():
                if tier.account_rates is None:
                    rate = Decimal(tier.rate or 0)
                else:
                    rate = Decimal(tier.account_rates.get(key, 0))
                own[key] = own.get(key, Decimal("0")) + pay(rate, sales * (top - low) / total)
        rounded = {key: _round(value, unit) for key, value in own.items()}
        amount = sum(rounded.values(), Decimal("0"))
        if hit or amount:
            lines.append(PayLine("main", _rm(at(main[hit[-1]])) if hit else None, amount))
            for key, each in rounded.items():
                shares[key] = shares.get(key, Decimal("0")) + each
    if hit and main[hit[-1]].additional_rate:
        top = main[hit[-1]]
        lines.append(PayLine("additional", _rm(at(top)), line_amount(top, top.additional_rate)))
    additional = sorted(
        (t for t in tiers if t.is_additional and reached(t)), key=lambda t: at(t) or Decimal("0")
    )
    for tier in additional:
        lines.append(PayLine("additional", _rm(at(tier)), line_amount(tier)))

    commission = sum((line.amount for line in lines), Decimal("0"))
    # The RM Additional of the reached tier, per account like the rate (owner 8 Nov, Q3).
    bonus = Decimal("0")
    if hit:
        top = main[hit[-1]]
        if top.account_bonuses is not None:
            bonuses = {key: Decimal(value or 0) for key, value in top.account_bonuses.items()}
        else:
            bonuses = {key: Decimal(top.bonus_amount or 0) for key in by_account}
        for key, each in bonuses.items():
            each = _round(each, unit)
            shares[key] = shares.get(key, Decimal("0")) + each
            bonus += each
    return Payout(_round(commission, unit), bonus, lines, tier_reached, ratio_missing, shares)


class FoldRow(NamedTuple):
    """One stored tier, as `fold_additionals` reads it. `threshold`: the value in the target's
    own unit (`from_pct` or `threshold`), so rows of one target compare like for like."""

    period_start: Optional[object]
    threshold: Decimal
    is_additional: bool
    rate: Optional[Decimal]
    account_rates: Optional[Dict[Hashable, Decimal]]
    additional_rate: Optional[Decimal] = None
    bonus_amount: Optional[Decimal] = None


class Fold(NamedTuple):
    #: legacy additional row index -> the main tier index it folds onto.
    moves: Dict[int, int]
    #: main tier index -> its new `additional_rate`.
    rates: Dict[int, Decimal]
    #: legacy additional row index -> why it stays a row of its own.
    skipped: Dict[int, str]
    #: main tier indexes whose Additional now also pays accounts the old row did not name.
    broadened: set
    #: main tier indexes whose Additional now pays only the tier's named accounts, where the old
    #: row paid every counted account.
    narrowed: set = set()


def fold_additionals(rows: Sequence[FoldRow]) -> Fold:
    """Where each legacy "+ Additional from X" row goes (lane TARGET-TIER-ADDITIONAL, owner Q5):
    onto the main tier of the same period and threshold, as that tier's % Additional. Left as
    it is, with the reason, when there is no such tier, two additionals share it, the tier
    already has an Additional or an RM Additional (Bonus), or the row pays different rates per
    account. Pure: the import and `scripts/fold_tier_additionals.py` both call it."""
    mains: Dict[tuple, int] = {}
    for i, r in enumerate(rows):
        if not r.is_additional:
            mains.setdefault((r.period_start, Decimal(r.threshold)), i)
    by_main: Dict[int, List[int]] = {}
    skipped: Dict[int, str] = {}
    for i, r in enumerate(rows):
        if not r.is_additional:
            continue
        m = mains.get((r.period_start, Decimal(r.threshold)))
        if m is None:
            skipped[i] = f"no tier starts at {Decimal(r.threshold):,.2f} in its period"
            continue
        by_main.setdefault(m, []).append(i)
    moves: Dict[int, int] = {}
    rates: Dict[int, Decimal] = {}
    broadened: set = set()
    narrowed: set = set()
    for m, adds in by_main.items():
        main = rows[m]
        if len(adds) > 1:
            for i in adds:
                skipped[i] = "two additionals on one tier"
            continue
        i = adds[0]
        r = rows[i]
        if main.additional_rate:
            skipped[i] = "the tier already has an Additional"
            continue
        if main.bonus_amount:
            skipped[i] = "the tier already has an RM Additional (Bonus)"
            continue
        if r.account_rates:
            values = {Decimal(v) for v in r.account_rates.values()}
            if len(values) != 1:
                skipped[i] = "different additional rates per account"
                continue
            rate = values.pop()
            paid = None if main.account_rates is None else set(main.account_rates)
            named = set(r.account_rates)
            if paid is not None and named - paid:
                skipped[i] = "names an account the tier does not pay"
                continue
            if paid is None or paid != named:
                broadened.add(m)
        else:
            rate = Decimal(r.rate or 0)
            if main.account_rates is not None:
                # "A/C I- 6% + Additional 1%": the old row paid every counted account, the tier
                # pays only its named ones; reported, so a target counting more accounts shows.
                narrowed.add(m)
        moves[i] = m
        rates[m] = rate
    return Fold(moves, rates, skipped, broadened, narrowed)


def _rm(value: Optional[Decimal]) -> Optional[Decimal]:
    return None if value is None else _round(value)


def commission_for(
    method: str,
    tiers: Sequence[Tier],
    target_value: Decimal,
    achieved: Decimal,
    *,
    metric: str = "amount",
) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """`(commission, bonus)` for one period of a `%`-of-target target (the original tiers)."""
    out = payout_for(method, tiers, target_value, {None: achieved}, metric=metric)
    return out.commission, out.bonus
