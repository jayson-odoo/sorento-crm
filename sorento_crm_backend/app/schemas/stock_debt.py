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
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel

Tone = Literal["red", "amber", "green"]
DemandStatus = Literal["covered", "late", "short", "pinned"]
SupplyKind = Literal["on_hand", "spo", "po"]
#: `book` (R1/AC-8): `all` (default) spans flagged project bins AND the site pools in one
#: read; `project` reproduces the pre-24-Sep view (flagged bins only); `retail` is pools
#: only and ignores `group`.
Book = Literal["all", "project", "retail"]
#: The export workbook's split (R5/AC-13..AC-16). One sheet for `none`.
ExportSplit = Literal["none", "supplier", "category", "supplier_category"]


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
    #: The row's LAST supplier (R3/A1, AC-4/AC-5): the supplier on the product's newest
    #: purchase-order line, falling back to the primary-flagged product supplier, else
    #: `None`. Never rendered as an id on the FE - `supplier_name` is what prints.
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    #: `products.category_id` is mandatory, so "no category" is a BLANK code (`""`), the
    #: same convention `low_stock_report_service._master_map` already uses - never `None`.
    category_code: Optional[str] = None
    #: Sum of every month's balance plus `tba` ONLY (R17: "No date"/"No location" leave
    #: the screen and the workbook both, so `undated`/`unlocated` are no longer folded in
    #: here - they still ride on the row, unchanged, just not in this figure).
    total: float = 0.0


class StockDebtPagination(BaseModel):
    total: int
    page: int
    limit: int


class StockDebtTotals(BaseModel):
    """The WHOLE filtered set's own totals (AC-6), never the page's - so the footer
    prints the same figures on page 1 and on page 2.

    `total` sums `months` + `tba` ONLY (R17), the same rule each row's own `total`
    follows - `undated`/`unlocated` still ride here for the two columns that still show
    them, just not folded into `total`.
    """

    months: Dict[str, float]
    tba: float
    undated: float
    unlocated: float
    total: float


class StockDebtSupplier(BaseModel):
    """One entry of the toolbar's supplier select (AC-7) - never an id on screen."""

    id: str
    name: str


class StockDebtSheetCounts(BaseModel):
    """The exact export sheet counts for the CURRENT filtered set (AC-7b), none-buckets
    ("No supplier" / "No category") included - so the export popover's preview never has
    to guess at a bucket it cannot see from one page."""

    supplier: int
    category: int
    supplier_category: int


class StockDebtList(BaseModel):
    """The list envelope: the repo's `{data, pagination}` plus the column axis.

    The axis, `totals`, `suppliers` and `sheet_counts` are envelope-level because each is a
    property of the whole FILTERED SET: derived per page, they would change under the
    reader as they page (AC-6/AC-7/AC-7b).
    """

    data: List[StockDebtRow]
    pagination: StockDebtPagination
    months: List[str]
    tba_month: str
    groups: List[str]
    totals: StockDebtTotals
    suppliers: List[StockDebtSupplier]
    sheet_counts: StockDebtSheetCounts


class StockDebtDemandLine(BaseModel):
    so_number: str
    agent_code: Optional[str] = None
    #: The bin the line is booked in - the drill's Bin column (AC-S2-7).
    warehouse_code: Optional[str] = None
    required_date: Optional[DateType] = None
    open_qty: float
    #: R22: the drill's own Ordered/Delivered columns, beside Outstanding (`open_qty`,
    #: unchanged). `qty_ordered` is `plan_qty()` - CS's own `qty_required` when the Order
    #: Inquiry sheet states one, else the sales-order book's `qty_ordered`.
    qty_ordered: float
    qty_delivered: float
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
    #: R26: an SPO's own Received (`quantity_received`) and Outstanding (the walk's own
    #: netted balance, what `qty` used to state before this ruling split it out) - `qty`
    #: above is now the SPO line's RAW ordered quantity. Both `None` for every other kind
    #: (on hand has no received/outstanding history to state), so the drill prints those
    #: two columns blank rather than a fabricated 0.
    received_qty: Optional[float] = None
    outstanding_qty: Optional[float] = None


class StockDebtCell(BaseModel):
    """The two tables behind one cell. `sum(supply.free_qty) - sum(demand.short_qty)` is the
    balance the cell that opened them prints (R37)."""

    demand: List[StockDebtDemandLine]
    supply: List[StockDebtSupplyEvent]
    #: R25: the tab labels' own quantity totals, over the WHOLE tab - `demand_total_qty`
    #: sums `open_qty` over `demand`; `supply_total_qty` sums each row's own Qty column
    #: (Outstanding for an SPO, the on-hand figure otherwise), never recomputed by the FE.
    demand_total_qty: float
    supply_total_qty: float


class StockDebtExportIn(BaseModel):
    """The export route's body (AC-12): every list filter except `page`/`limit`, plus the
    workbook `split`. Every field optional/defaulted so `{"split": "none"}` alone is a
    valid request - the same shape `list_stock_debt`'s own query params default to.

    `date_from`/`date_to` replace `cutoff` and `supplier_ids` replaces `supplier_id`
    (R14/R15): both are REMOVED, not aliased - a caller still sending the old names sends
    them into nothing, exactly as `group` sends into a param the export never reads (R16
    leaves `group` itself alone on the BACKEND; the export body's own field is unaffected
    by that ruling and stays for parity with `list()`'s own signature).
    """

    query: Optional[str] = None
    group: Optional[str] = None
    only_debt: bool = True
    date_from: Optional[DateType] = None
    date_to: Optional[DateType] = None
    supplier_ids: List[str] = []
    book: Book = "all"
    split: ExportSplit = "none"
