"""Netting and the verb rule for the order inquiry (P10, AC-I2, AC-I3, AC-I3a).

No database, no session, no clock of its own. Demand rows and covering pools go in,
instructions come out, and every decision is arithmetic on quantities and dates. The
persistence, the pools and the SCM handoff live in
``project_order_inquiry_service.py``; this file is the part worth pinning as a table.

Three rules carry it.

**A covering pool is consumed FIFO BY DELIVERY DATE** (AC-I3a). The 5,950 pre-ordered
gratings go to the earliest dated demand first, so purchasing reads which dates are
already covered and which still have to be bought. Demand with no date at all is served
last: an undated line cannot claim stock ahead of a line that has a delivery to make.

**The instruction list still reads in the order the lines were given.** Allocation is by
date; PRINTING is by line, so a published sales order's rows come out in line order the
way the client's own file is written. Two different orderings, deliberately.

**An ORDER row is never emitted for a covered quantity** (AC-I3). A line that is half
covered becomes two rows: what the pool covers, saying what covered it, and the balance
that still needs buying. A zero balance emits nothing, because "ORDER 0" is worse than
silence.

Amendment instructions (DELAY, ADVANCE, CANCEL BALANCE, CHANGE SO) pass straight through
and never touch a pool. They are instructions about quantity purchasing already knows
about; only NEW and INCREASED demand asks the question "do we have to buy this".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from app.models.project_so import (
    IV_ADVANCE,
    IV_ALREADY_INBOUND,
    IV_CANCEL_BALANCE,
    IV_CHANGE_SO,
    IV_DELAY,
    IV_ORDER,
    IV_PRE_ORDERED,
    IV_RESERVE_AND_ORDER,
)

_ZERO = Decimal("0")

# What happened to this line, measured against the previously published state. A fresh
# publish is all `new`; an amendment supplies the rest from its computed delta.
CHANGE_NEW = "new"
CHANGE_QTY_INCREASE = "qty_increase"
CHANGE_QTY_DECREASE = "qty_decrease"
CHANGE_DATE_LATER = "date_later"
CHANGE_DATE_EARLIER = "date_earlier"
CHANGE_REPOINT = "repoint"

# Only these two ask purchasing to buy something, so only these two consume a pool.
BUYING_CHANGES = (CHANGE_NEW, CHANGE_QTY_INCREASE)

COVERAGE_NONE = "none"
COVERAGE_PRE_ORDER = "pre_order"
COVERAGE_INBOUND = "inbound"

POOL_PRE_ORDER = "pre_order"
POOL_INBOUND_SPO = "inbound_spo"

_POOL_COVERAGE = {POOL_PRE_ORDER: COVERAGE_PRE_ORDER, POOL_INBOUND_SPO: COVERAGE_INBOUND}

# A pre-order is stock we already committed to and can point at; an inbound SPO is on
# the water and carries a reference purchasing has to quote. Ours first, deterministically.
_POOL_RANK = {POOL_PRE_ORDER: 0, POOL_INBOUND_SPO: 1}

# New demand landing inside this window is RESERVE & ORDER rather than plain ORDER:
# purchasing has to hold what is on the shelf as well as order the balance, because the
# order will not land before the delivery date. Same window as the revision delta
# (``project_so_delta_service.RESERVE_WINDOW_DAYS``), and the same reason.
RESERVE_WINDOW_DAYS = 60

# Sorts after every real date without needing a None branch in three comparisons.
_LAST = date.max
_FIRST = date.min


@dataclass(frozen=True)
class DemandRow:
    """One sales-order line asking purchasing for something."""

    line_id: str
    product_id: str
    item_code: str
    qty: Decimal
    delivery_date: Optional[date]
    stock_location: Optional[str] = None
    change: str = CHANGE_NEW
    # The human half of an amendment instruction: the date a DELAY moved from, the sales
    # order a CHANGE SO points at. A verb on its own is not actionable.
    note: Optional[str] = None


@dataclass(frozen=True)
class CoveringPool:
    """Quantity that already exists, or is on the water, for one product."""

    kind: str
    reference: str
    product_id: str
    qty: Decimal
    # When the stock becomes available. Used only for ordering pools against each
    # other: coverage itself is a quantity fact, and the reference on the row is what
    # lets purchasing judge whether the arrival is soon enough.
    available_from: Optional[date] = None

    @property
    def label(self) -> str:
        if self.kind == POOL_PRE_ORDER:
            return f"Pre-order {self.reference}"
        return f"Inbound SPO {self.reference}"


@dataclass(frozen=True)
class InquiryRowPlan:
    """One instruction, ready to be written as a ``project_order_inquiry_rows`` row."""

    line_id: str
    product_id: str
    item_code: str
    qty: Decimal
    delivery_date: Optional[date]
    stock_location: Optional[str]
    verb: str
    spo_ref: Optional[str] = None
    covered_by: Optional[str] = None
    note: Optional[str] = None


def verb_for(
    change: str,
    coverage: str,
    *,
    delivery_date: Optional[date],
    today: Optional[date] = None,
) -> str:
    """The single verb for one (change, coverage) pair. AC-I2's whole vocabulary.

    Coverage only bears on the two changes that ask purchasing to BUY. A date move or a
    cancellation is an instruction about quantity already ordered, so it reads the same
    whether a pre-order covers it or not.
    """
    if change == CHANGE_DATE_LATER:
        return IV_DELAY
    if change == CHANGE_DATE_EARLIER:
        return IV_ADVANCE
    if change == CHANGE_QTY_DECREASE:
        return IV_CANCEL_BALANCE
    if change == CHANGE_REPOINT:
        return IV_CHANGE_SO
    if coverage == COVERAGE_PRE_ORDER:
        return IV_PRE_ORDERED
    if coverage == COVERAGE_INBOUND:
        return IV_ALREADY_INBOUND
    # A reserve is a promise about a date. With no date there is nothing to reserve for.
    if delivery_date is None:
        return IV_ORDER
    horizon = (today or date.today()) + timedelta(days=RESERVE_WINDOW_DAYS)
    return IV_RESERVE_AND_ORDER if delivery_date <= horizon else IV_ORDER


def net_demand(
    demand: Sequence[DemandRow],
    pools: Sequence[CoveringPool],
    *,
    today: Optional[date] = None,
) -> List[InquiryRowPlan]:
    """Net the demand against the pools and return the instructions, in line order."""
    remaining = _remaining_by_product(pools)
    covered = _allocate_fifo(demand, remaining)

    out: List[InquiryRowPlan] = []
    for row in demand:
        out.extend(_plans_for(row, covered.get(row.line_id, []), today=today))
    return out


# --------------------------------------------------------------------- internals


@dataclass
class _Take:
    """How much of one pool one demand row got."""

    pool: CoveringPool
    qty: Decimal


def _remaining_by_product(
    pools: Sequence[CoveringPool],
) -> Dict[str, List[List]]:
    """Pools per product, in consumption order, each paired with its unconsumed balance."""
    ordered = sorted(
        (pool for pool in pools if pool.qty > _ZERO),
        key=lambda pool: (
            pool.available_from or _FIRST,
            _POOL_RANK.get(pool.kind, 99),
            pool.reference,
        ),
    )
    by_product: Dict[str, List[List]] = {}
    for pool in ordered:
        by_product.setdefault(pool.product_id, []).append([pool, pool.qty])
    return by_product


def _allocate_fifo(
    demand: Sequence[DemandRow], remaining: Dict[str, List[List]]
) -> Dict[str, List[_Take]]:
    """Hand the pool out earliest-delivery-first. Returns takes keyed by line id."""
    buying = [
        row for row in demand if row.change in BUYING_CHANGES and row.qty > _ZERO
    ]
    # Ties broken on item code then line id so two lines on the same date always net
    # the same way, run after run.
    buying.sort(key=lambda row: (row.delivery_date or _LAST, row.item_code, row.line_id))

    takes: Dict[str, List[_Take]] = {}
    for row in buying:
        outstanding = row.qty
        for entry in remaining.get(row.product_id, []):
            if outstanding <= _ZERO:
                break
            pool, available = entry
            if available <= _ZERO:
                continue
            taken = min(available, outstanding)
            entry[1] = available - taken
            outstanding -= taken
            takes.setdefault(row.line_id, []).append(_Take(pool=pool, qty=taken))
    return takes


def _plans_for(
    row: DemandRow, takes: Sequence[_Take], *, today: Optional[date]
) -> List[InquiryRowPlan]:
    if row.qty <= _ZERO:
        return []

    if row.change not in BUYING_CHANGES:
        return [
            InquiryRowPlan(
                line_id=row.line_id,
                product_id=row.product_id,
                item_code=row.item_code,
                qty=row.qty,
                delivery_date=row.delivery_date,
                stock_location=row.stock_location,
                verb=verb_for(
                    row.change, COVERAGE_NONE, delivery_date=row.delivery_date, today=today
                ),
                note=row.note,
            )
        ]

    out: List[InquiryRowPlan] = []
    balance = row.qty
    for take in takes:
        coverage = _POOL_COVERAGE.get(take.pool.kind, COVERAGE_NONE)
        out.append(
            InquiryRowPlan(
                line_id=row.line_id,
                product_id=row.product_id,
                item_code=row.item_code,
                qty=take.qty,
                delivery_date=row.delivery_date,
                stock_location=row.stock_location,
                verb=verb_for(
                    row.change, coverage, delivery_date=row.delivery_date, today=today
                ),
                spo_ref=take.pool.reference if coverage == COVERAGE_INBOUND else None,
                covered_by=take.pool.label,
                note=row.note,
            )
        )
        balance -= take.qty

    if balance > _ZERO:
        out.append(
            InquiryRowPlan(
                line_id=row.line_id,
                product_id=row.product_id,
                item_code=row.item_code,
                qty=balance,
                delivery_date=row.delivery_date,
                stock_location=row.stock_location,
                verb=verb_for(
                    row.change, COVERAGE_NONE, delivery_date=row.delivery_date, today=today
                ),
                note=row.note,
            )
        )
    return out
