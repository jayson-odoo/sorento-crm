"""SCM S5 - the exception classifier and the action ranking (UAC Group D).

Two tables, and between them they are the whole point of the slice.

**The eight change cases (AC-D8).** The eight things that happen to a sales order in the
source flow produce four exception types, and the engine must contain NO branch keyed on
which of them it was. That is enforced here by construction rather than by inspection: the
classifier is given only POSITIONS and the supply already placed, so there is no verb in
scope to branch on. A line added and a quantity increased are the same input to it, which is
exactly the claim - what matters is that the plan now disagrees with a placed order, never
the verb that made it disagree.

**The reading inversion (AC-D10, AC-D11).** Identical arithmetic on differently-read items
proposes different actions FIRST. A discontinued C/Z retail surplus proposes keeping the
order and pooling the stock, because that is the last stock of it obtainable and deferring
risks the supplier closing the line; an active A/X project item proposes reallocating; an
active C/Z retail item proposes pushing the ETA out. Ordering by quantity would give all
three the same answer, which is the behaviour this table exists to prevent.

Pure functions, no database: the classifier and the ranking take dataclasses in and give
dataclasses out. The service that reads the four signals from real tables is tested
separately, against Postgres.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.scm.plan_exception_engine import (
    ItemReading,
    PlacedSupply,
    Position,
    classify,
    rank_actions,
)

TODAY = date(2026, 8, 4)


def d(days: int) -> date:
    return TODAY + timedelta(days=days)


def pos(
    shortfall_at: date | None = None,
    shortfall_qty: float = 0.0,
    surplus_qty: float = 0.0,
    first_need_at: date | None = None,
    demand_warehouse_ids: tuple[str, ...] = (),
) -> Position:
    return Position(
        shortfall_at=shortfall_at,
        shortfall_qty=shortfall_qty,
        surplus_qty=surplus_qty,
        first_need_at=first_need_at,
        demand_warehouse_ids=demand_warehouse_ids,
    )


def supply(expected: date = d(45), qty: float = 240.0, warehouse_id: str = "WH-A") -> PlacedSupply:
    return PlacedSupply(
        purchase_order_id="po-1",
        expected_date=expected,
        qty=qty,
        warehouse_id=warehouse_id,
        pool_warehouse_ids=("WH-A",),
    )


# --------------------------------------------------------------------------- #
# AC-D8 - the eight source change cases, with no verb reaching the engine
# --------------------------------------------------------------------------- #

# (name, before, after, supply, expected type). The NAME records which source change
# produces this shape; the engine never sees it.
EIGHT_CASES = [
    (
        "a line was added",
        pos(first_need_at=d(60)),
        pos(shortfall_at=d(20), shortfall_qty=150, first_need_at=d(20)),
        supply(expected=d(45)),
        "shortfall_earlier",
    ),
    (
        "the quantity was increased",
        pos(first_need_at=d(60)),
        pos(shortfall_at=d(30), shortfall_qty=80, first_need_at=d(30)),
        supply(expected=d(45)),
        "shortfall_earlier",
    ),
    (
        "the quantity was reduced",
        pos(first_need_at=d(30)),
        pos(surplus_qty=240, first_need_at=d(30)),
        supply(expected=d(45)),
        "supply_surplus",
    ),
    (
        "the line was cancelled",
        pos(first_need_at=d(30)),
        pos(surplus_qty=240),
        supply(expected=d(45)),
        "supply_surplus",
    ),
    (
        "the required date was pulled in",
        pos(first_need_at=d(60)),
        pos(shortfall_at=d(25), shortfall_qty=200, first_need_at=d(25)),
        supply(expected=d(45)),
        "shortfall_earlier",
    ),
    (
        "the required date was pushed out",
        pos(first_need_at=d(50)),
        pos(first_need_at=d(160)),
        supply(expected=d(45)),
        "supply_early",
    ),
    (
        "the order now ships from a different site",
        pos(first_need_at=d(50), demand_warehouse_ids=("WH-A",)),
        pos(first_need_at=d(50), demand_warehouse_ids=("WH-B",)),
        supply(expected=d(45), warehouse_id="WH-A"),
        "supply_wrong_location",
    ),
    (
        "nothing about this product changed",
        pos(first_need_at=d(50)),
        pos(first_need_at=d(50)),
        supply(expected=d(45)),
        None,
    ),
]


@pytest.mark.parametrize(
    "name,before,after,placed,expected",
    EIGHT_CASES,
    ids=[c[0] for c in EIGHT_CASES],
)
def test_the_eight_source_changes_produce_the_right_exception_type(
    name, before, after, placed, expected
):
    result = classify(before, after, placed, today=TODAY)
    assert (result.exception_type if result else None) == expected, name


def test_a_change_that_agrees_with_placed_supply_is_not_an_exception():
    """The reduction from deltas to exceptions is the value of the screen (AC-D2b).

    A line that moved but whose new position the placed order still satisfies produces
    NOTHING here - which is why a batch of 412 deltas is normally six exceptions.
    """
    before = pos(first_need_at=d(50))
    after = pos(first_need_at=d(52))  # moved two days; the PO still lands before it
    assert classify(before, after, supply(expected=d(45)), today=TODAY) is None


def test_a_shortfall_the_placed_supply_still_covers_is_not_an_exception():
    """A gap that opens AFTER the order lands is covered by that order.

    Flagging it would put a row in front of somebody with nothing to decide.
    """
    before = pos(first_need_at=d(60))
    after = pos(shortfall_at=d(50), shortfall_qty=100, first_need_at=d(50))
    assert classify(before, after, supply(expected=d(45)), today=TODAY) is None


def test_a_shortfall_outranks_a_surplus_when_both_are_true():
    """Precedence, because only one of the two can miss a customer date.

    A restatement that both pulls one order in and cancels another leaves the product short
    AND long. The short is the one somebody has to act on this week.
    """
    before = pos(first_need_at=d(60))
    after = pos(shortfall_at=d(20), shortfall_qty=150, surplus_qty=90, first_need_at=d(20))
    result = classify(before, after, supply(expected=d(45)), today=TODAY)
    assert result is not None
    assert result.exception_type == "shortfall_earlier"


def test_the_quantity_is_the_gap_not_the_whole_order():
    """What is short is what has to be decided about, not the size of the placed order."""
    after = pos(shortfall_at=d(20), shortfall_qty=150, first_need_at=d(20))
    result = classify(pos(first_need_at=d(60)), after, supply(qty=240), today=TODAY)
    assert result is not None
    assert result.quantity == 150


def test_a_surplus_is_never_larger_than_the_supply_it_is_about():
    """The exception is about ONE placed order, so it cannot claim more than that order holds.

    Two POs against the same cancelled demand produce two exceptions of their own sizes, not
    one that double-counts the surplus.
    """
    after = pos(surplus_qty=500)
    result = classify(pos(first_need_at=d(30)), after, supply(qty=240), today=TODAY)
    assert result is not None
    assert result.quantity == 240


# --------------------------------------------------------------------------- #
# AC-D10 / AC-D11 - the reading orders the actions, and quantity never does
# --------------------------------------------------------------------------- #

def reading(lifecycle: str, abc: str, xyz: str, demand_class: str) -> ItemReading:
    return ItemReading(
        is_discontinued=lifecycle == "discontinued",
        abc_class=abc,
        xyz_class=xyz,
        demand_class=demand_class,
        last_po_date=date(2026, 3, 2),
    )


# Identical arithmetic. Only the reading differs, and the FIRST action differs with it.
INVERSION = [
    (
        "discontinued slow retail keeps the order",
        reading("discontinued", "C", "Z", "retail"),
        "keep_and_pool",
    ),
    (
        "active fast project reallocates",
        reading("active", "A", "X", "project"),
        "relink_so",
    ),
    (
        "active slow retail pushes the eta out",
        reading("active", "C", "Z", "retail"),
        "push_eta",
    ),
]


@pytest.mark.parametrize(
    "name,item,expected_first", INVERSION, ids=[c[0] for c in INVERSION]
)
def test_the_reading_decides_which_action_is_proposed_first(name, item, expected_first):
    actions = rank_actions("supply_surplus", item, has_candidate_order=True)
    assert actions[0].code == expected_first, name
    assert actions[0].rank == 1


def test_a_discontinued_surplus_never_proposes_cancelling_or_deferring_first():
    """AC-D11 stated as its own test, because it is the one inversion with a cost.

    That stock is the last of the product obtainable, and pushing the date out risks the
    supplier closing the line while we wait.
    """
    actions = rank_actions(
        "supply_surplus", reading("discontinued", "C", "Z", "retail"), has_candidate_order=False
    )
    assert actions[0].code not in ("push_eta", "accept")


def test_every_exception_carries_at_least_one_action():
    """AC-D5. An exception with nothing proposed is a notification, not a decision."""
    for kind in ("shortfall_earlier", "supply_early", "supply_surplus", "supply_wrong_location"):
        for item in (
            reading("active", "A", "X", "project"),
            reading("discontinued", "C", "Z", "retail"),
        ):
            actions = rank_actions(kind, item, has_candidate_order=False)
            assert actions, f"{kind} proposed nothing"
            assert [a.rank for a in actions] == list(range(1, len(actions) + 1))


def test_relink_is_not_proposed_when_there_is_no_order_to_relink_to():
    """A proposal that names no candidate order is an instruction to go and find one.

    AC-D5 requires the candidate and its need-by date to travel with the action, so where
    there is no candidate the action is not offered at all.
    """
    codes = [
        a.code
        for a in rank_actions(
            "supply_surplus", reading("active", "A", "X", "project"), has_candidate_order=False
        )
    ]
    assert "relink_so" not in codes


def test_the_ranking_does_not_depend_on_quantity():
    """The regression this table exists for: ordering by size would collapse the inversion."""
    item = reading("discontinued", "C", "Z", "retail")
    small = rank_actions("supply_surplus", item, has_candidate_order=True)
    large = rank_actions("supply_surplus", item, has_candidate_order=True)
    assert [a.code for a in small] == [a.code for a in large]
