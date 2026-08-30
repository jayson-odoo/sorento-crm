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
    """One month of a product row. `balance` is the CUMULATIVE dated running balance."""

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
    #: Arrival passed with nothing received: listed, and counted as nothing (R31).
    overdue: bool
    assigned_to: List[StockDebtAssignedTo]


class StockDebtCell(BaseModel):
    demand: List[StockDebtDemandLine]
    supply: List[StockDebtSupplyEvent]
