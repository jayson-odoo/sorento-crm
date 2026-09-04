"""The Stock Debt payloads (S2, AC-S2-6 / AC-S2-7).

Field for field the same shapes as `app/(protected)/project-sales/stock-debt/types/
stockDebt.types.ts`; the two are one contract written twice, once per language, and neither
restates the other's reasoning - the route contract lives in the FE service's header and the
arithmetic in `supply_assignment`.

A `response_model` DROPS what it does not declare, so every field the service computes is
declared here and asserted by name in `tests/scm/test_stock_debt_routes.py`.
"""
from __future__ import annotations

#: Aliased, because `StockDebtSupplyEvent` has a FIELD called `date` (the arrival, which is
#: what the FE column is called) and a bare `date` annotation inside that class body resolves
#: to the field, not to the type - which pydantic reads as "this must be None" and every
#: dated event then fails response validation.
from datetime import date as DateType
from typing import List, Literal, Optional

from pydantic import BaseModel

Tone = Literal["red", "amber", "green"]
DemandStatus = Literal["covered", "late", "short", "pinned"]
SupplyKind = Literal["on_hand", "spo", "po"]


class StockDebtMonth(BaseModel):
    """One month of a product row, on its own (R37).

    `balance` is the supply dated in the month that is still free when the assignment walk
    is over, less what the lines due in the month were short of on their own dates. It does
    NOT carry: a month with nothing due and nothing arriving reads 0.
    """

    key: str
    balance: float
    tone: Tone


class StockDebtRow(BaseModel):
    product_id: str
    product_code: str
    product_name: Optional[str] = None
    #: One entry per axis month, in axis order.
    months: List[StockDebtMonth]
    #: Demand dated on or after the policy's `tba_date_from`, demand with no date, and
    #: demand booked at no warehouse at all. None of the three draws supply (R14, AC-S2-1b's
    #: sibling case), so all three are plain signed totals and carry no tone.
    tba: float
    undated: float
    unlocated: float


class StockDebtPagination(BaseModel):
    total: int
    page: int
    limit: int


class StockDebtList(BaseModel):
    """The list envelope: the repo's `{data, pagination}` plus the column axis.

    The axis is envelope-level because it belongs to the whole FILTERED SET: derived per
    page, the columns would change under the reader as they page.
    """

    data: List[StockDebtRow]
    pagination: StockDebtPagination
    months: List[str]
    tba_month: str
    groups: List[str]


class StockDebtDemandLine(BaseModel):
    so_number: str
    agent_code: Optional[str] = None
    #: The bin the line is booked in - the drill's Bin column (AC-S2-7).
    warehouse_code: Optional[str] = None
    required_date: Optional[DateType] = None
    open_qty: float
    assigned_qty: float
    assigned_source: Optional[str] = None
    status: DemandStatus
    #: What the line went short of ON ITS OWN DATE - the quantity its month books (R37).
    #: A `late` line ends covered and still carries one.
    short_qty: float


class StockDebtAssignedTo(BaseModel):
    so_number: str
    qty: float


class StockDebtSupplyEvent(BaseModel):
    kind: SupplyKind
    ref: Optional[str] = None
    warehouse_code: Optional[str] = None
    #: Arrival: today for on hand, the SPO's arrival, `issue + lead` for a PO line (R29).
    date: Optional[DateType] = None
    #: PO only: the SO delivery date the line was typed against. Display only (R30).
    bought_for: Optional[DateType] = None
    qty: float
    #: What nobody took by the end of the walk - the quantity its month credits (R37).
    #: Zero for a DEAD document, which is not supply until somebody re-dates it (R31).
    free_qty: float
    #: Arrival passed and the grace period has given up on it (later than
    #: `overdue_dead_days`): listed, and counted as nothing (R31, as R-O leaves it). The
    #: row reads "not counted".
    overdue: bool
    #: The date the DOCUMENT states, when `date` above is the ASSUMED one the grace period
    #: gave a late arrival (R-O). `None` when the two are the same, so a reader can print
    #: "assumed 17 Sep 2026, stated 24 Jul" only where there is something to say.
    #: `response_model` drops an undeclared field, so this is named explicitly.
    stated_date: Optional[DateType] = None
    #: How late the paperwork is, in days, on the day the walk was taken (R-O). 0 when the
    #: arrival is the one the document states.
    days_late: int = 0
    assigned_to: List[StockDebtAssignedTo]


class StockDebtCell(BaseModel):
    """The two tables behind one cell. `sum(supply.free_qty) - sum(demand.short_qty)` is the
    balance the cell that opened them prints (R37)."""

    demand: List[StockDebtDemandLine]
    supply: List[StockDebtSupplyEvent]
