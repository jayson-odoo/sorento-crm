"""SCM S5 - the exception classifier and the action ranking (UAC Group D).

Pure. No database, no session, no clock of its own: positions and the supply already placed
go in, an exception or nothing comes out. Everything that reads a real table lives in
`plan_exception_service`.

**There is no verb in this module, deliberately.** AC-D8 requires the eight source change
cases to produce the right exception type "with no branch in the engine keyed on the verb",
and the way to guarantee that is to keep the verb out of scope entirely rather than to
promise not to look at it. A line added and a quantity increased arrive here as the same
input, which is the claim itself: what matters is that the restated plan now disagrees with
an order that is already out with a supplier, never which edit made it disagree.

Two decisions worth stating, because both are arguable and neither is obvious:

  * **A shortfall outranks a surplus** when a restatement produces both. Only one of the two
    can miss a customer date.
  * **A gap the placed order still covers is not an exception.** The whole value of the
    screen is the reduction from deltas to exceptions (AC-D2b), and a row somebody opens to
    find nothing to decide spends the reader's attention for nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Sequence

# Types (AC-D3). Four is the stated minimum and each names a DIFFERENT remedy, which is why
# the type is carried rather than derived downstream from the sign of a number.
SHORTFALL_EARLIER = "shortfall_earlier"
SUPPLY_EARLY = "supply_early"
SUPPLY_SURPLUS = "supply_surplus"
SUPPLY_WRONG_LOCATION = "supply_wrong_location"

# How far a placed order has to sit ahead of the need before "early" is worth anybody's
# attention. Below this it is ordinary slack, and flagging it would bury the rows that matter.
EARLY_TOLERANCE_DAYS = 30

# Quantities below this are rounding, not a disagreement.
QTY_EPSILON = 0.0005


@dataclass(frozen=True)
class Position:
    """One product's dated position over its fulfilment pool, from one side of the diff.

    `shortfall_at` is the PEAK deficit date, not the first gap, matching the figure the buy
    plan is built from - the two disagree whenever demand arrives in waves, and a screen that
    used the first gap would propose a different quantity from the plan beside it.

    `first_need_at` is when the earliest committed demand falls due, which is what decides
    whether a placed order is early. It is None when nothing is committed at all.
    """

    shortfall_at: Optional[date] = None
    shortfall_qty: float = 0.0
    surplus_qty: float = 0.0
    first_need_at: Optional[date] = None
    # Which locations the committed demand now ships from. Used only to notice that supply is
    # heading somewhere the demand no longer is.
    demand_warehouse_ids: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class PlacedSupply:
    """One purchase order line already out with a supplier.

    `pool_warehouse_ids` is the fulfilment pool its destination belongs to, because netting
    is pooled: stock landing at a sibling warehouse in the same pool is NOT in the wrong
    place, and treating it as such would generate an exception per site on every pooled
    product.
    """

    purchase_order_id: Optional[str]
    expected_date: Optional[date]
    qty: float
    warehouse_id: Optional[str] = None
    pool_warehouse_ids: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExceptionFinding:
    """What the classifier decided. `quantity` is always positive; the TYPE carries direction."""

    exception_type: str
    quantity: float


def classify(
    before: Position,
    after: Position,
    placed: PlacedSupply,
    *,
    today: Optional[date] = None,
) -> Optional[ExceptionFinding]:
    """The exception this placed order is now in, or None if it still agrees with the plan.

    Order of the checks is precedence, not convenience. A shortfall is first because it is
    the only one of the four that can make a customer date be missed.
    """
    del today  # accepted so callers need not care which checks are dated; none is, today.

    shortfall = _shortfall_earlier(before, after, placed)
    if shortfall is not None:
        return shortfall

    wrong_place = _wrong_location(after, placed)
    if wrong_place is not None:
        return wrong_place

    surplus = _surplus(after, placed)
    if surplus is not None:
        return surplus

    return _early(before, after, placed)


def _shortfall_earlier(
    before: Position, after: Position, placed: PlacedSupply
) -> Optional[ExceptionFinding]:
    """Short before the placed order lands, and sooner than it used to be.

    Both halves are load-bearing. Without "sooner than it used to be" every product that was
    already short would be reported on every upload, and the batch would be a copy of the buy
    plan. Without "before the placed order lands" a gap the order already covers would be
    flagged, and there would be nothing to decide.
    """
    if after.shortfall_at is None or after.shortfall_qty <= QTY_EPSILON:
        return None
    # The placed order does not help a gap that opens before it arrives.
    if placed.expected_date is not None and placed.expected_date <= after.shortfall_at:
        return None
    moved_earlier = before.shortfall_at is None or after.shortfall_at < before.shortfall_at
    if not moved_earlier:
        return None
    return ExceptionFinding(SHORTFALL_EARLIER, float(after.shortfall_qty))


def _wrong_location(after: Position, placed: PlacedSupply) -> Optional[ExceptionFinding]:
    """Supply heading somewhere the demand no longer is.

    Judged against the POOL, not the warehouse: stock landing at a sibling site in the same
    pool is available to the demand, and calling that wrong would raise an exception per
    location for every pooled product on every upload.
    """
    if not after.demand_warehouse_ids or placed.warehouse_id is None:
        return None
    reachable = set(placed.pool_warehouse_ids) | {placed.warehouse_id}
    if any(w in reachable for w in after.demand_warehouse_ids):
        return None
    return ExceptionFinding(SUPPLY_WRONG_LOCATION, float(placed.qty))


def _surplus(after: Position, placed: PlacedSupply) -> Optional[ExceptionFinding]:
    """Stock that nothing committed will consume.

    Capped at the size of THIS order: the exception is about one placed order, so it cannot
    claim more than that order holds. Two orders against the same cancelled demand produce
    two exceptions of their own sizes rather than one that double-counts.
    """
    if after.surplus_qty <= QTY_EPSILON:
        return None
    return ExceptionFinding(SUPPLY_SURPLUS, float(min(after.surplus_qty, placed.qty)))


def _early(
    before: Position, after: Position, placed: PlacedSupply
) -> Optional[ExceptionFinding]:
    """The order still lands, but the demand it was for has moved a long way out.

    Not an error, and not free either: it is holding cost and warehouse space committed
    against a date nobody needs any more. The tolerance keeps ordinary slack off the screen.
    """
    if placed.expected_date is None or after.first_need_at is None:
        return None
    if before.first_need_at is not None and after.first_need_at <= before.first_need_at:
        return None
    slack_days = (after.first_need_at - placed.expected_date).days
    if slack_days <= EARLY_TOLERANCE_DAYS:
        return None
    return ExceptionFinding(SUPPLY_EARLY, float(placed.qty))


# --------------------------------------------------------------------------- #
# The reading, and the actions it orders
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ItemReading:
    """The four signals that order the proposed actions (AC-D9).

    All four are read from data that already exists - `products.is_discontinued`,
    `scm.item_classification`, the market segment's demand class, and the last purchase
    order's date. Nothing here is newly computed, and a signal that is genuinely absent stays
    None rather than being defaulted: a default would silently change the order below.
    """

    is_discontinued: bool = False
    abc_class: Optional[str] = None
    xyz_class: Optional[str] = None
    demand_class: Optional[str] = None
    last_po_date: Optional[date] = None

    @property
    def is_fast(self) -> bool:
        """A or B by value, X or Y by steadiness. Unknown is NOT fast - an unclassified item
        has not earned the benefit of the doubt about turning over."""
        return (self.abc_class in ("A", "B")) and (self.xyz_class in ("X", "Y"))

    @property
    def is_project(self) -> bool:
        return (self.demand_class or "").lower() == "project"


@dataclass(frozen=True)
class RankedAction:
    code: str
    rank: int
    rationale: str


def rank_actions(
    exception_type: str, item: ItemReading, *, has_candidate_order: bool
) -> list[RankedAction]:
    """The proposed actions, best first FOR THIS ITEM (AC-D10).

    Ordered by the reading, never by quantity. Identical arithmetic on a discontinued C/Z
    retail item and on an active A/X project item produces different first actions, and that
    inversion is the feature: the first is the last stock of that product obtainable, and the
    second turns over fast enough that somebody else is waiting for it.

    `has_candidate_order` gates relinking. A proposal that names no order to move to is an
    instruction to go and find one, and AC-D5 requires the candidate and its need-by date to
    travel with the action.
    """
    codes = _ordered_codes(exception_type, item, has_candidate_order)
    return [
        RankedAction(code=code, rank=i, rationale=_RATIONALE[code])
        for i, code in enumerate(codes, start=1)
    ]


def _ordered_codes(
    exception_type: str, item: ItemReading, has_candidate_order: bool
) -> list[str]:
    if exception_type == SUPPLY_SURPLUS:
        return _surplus_codes(item, has_candidate_order)
    if exception_type == SHORTFALL_EARLIER:
        # Moving stock that already exists beats waiting for an order to be re-dated, and
        # both beat accepting a missed date.
        codes = ["relink_so", "change_location", "accept"]
        return [c for c in codes if c != "relink_so" or has_candidate_order]
    if exception_type == SUPPLY_EARLY:
        # Nothing needs it yet, so the cheapest answer is for it to arrive later. Releasing
        # it to the pool is next: somebody else may draw on it in the meantime.
        return ["push_eta", "release_to_pool", "accept"]
    if exception_type == SUPPLY_WRONG_LOCATION:
        codes = ["change_location", "release_to_pool", "split", "accept"]
        return codes
    return ["accept"]


def _surplus_codes(item: ItemReading, has_candidate_order: bool) -> list[str]:
    """Where the inversion lives.

    Three readings, three different first answers to the same arithmetic:

      * **Discontinued** - keep it and pool it. This is the last stock of the product
        obtainable; cancelling or deferring risks the supplier closing the line while we
        decide (AC-D11), so neither is offered first.
      * **Fast-moving project item** - relink it. Something else is waiting on the same
        stock, and moving it is worth more than the holding cost saved by deferring.
      * **Anything else** (slow, retail, unclassified) - push the ETA out. Later costs
        nothing on an item nobody is waiting for, and it frees the cash.
    """
    if item.is_discontinued:
        codes = ["keep_and_pool", "relink_so", "push_eta", "accept"]
    elif item.is_fast and item.is_project:
        codes = ["relink_so", "change_location", "split", "push_eta"]
    else:
        codes = ["push_eta", "release_to_pool", "split", "accept"]
    return [c for c in codes if c != "relink_so" or has_candidate_order]


_RATIONALE = {
    "keep_and_pool": (
        "Discontinued, so this is the last stock obtainable. Cancelling or deferring risks "
        "the supplier closing the line."
    ),
    "relink_so": "Another committed order is waiting on the same stock.",
    "change_location": "The order that needs it ships from a different warehouse.",
    "release_to_pool": "Release it so any location in the pool may draw on it.",
    "split": "Move only the part another order needs; the rest stays where it is.",
    "push_eta": "Nothing committed needs it yet, so a later arrival costs nothing and frees the cash.",
    "accept": "Take it as it stands, on the record.",
}
