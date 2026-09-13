"""Schemas for order-management routes that are not row-CRUD.

CRUD schemas for orders/customers/statuses live in `app/schemas/order.py`; this
file is for a cross-cutting, read-only response shape scoped to
`/api/v1/order-management/*` that is a REPORT, not a listing of one entity -
today, `OutstandingReportResponse`
(`documentation/plans/chatbot/PLAN-chatbot-outstanding-report.md` "Backend
contract"; AC-1110 to AC-1119).
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel


#: Every quantity below is a WHOLE unit. The columns behind them are `Numeric(15,4)`,
#: so a fractional quantity is storable; the service rounds it HALF UP before it reaches
#: these models (`outstanding_report_service._qty`), because the reply prints
#: thousands-separated units and bankers' rounding would print 2 for 2.5 and 4 for 3.5
#: in the same message.
class OutstandingSOBlock(BaseModel):
    ordered_qty: int
    transferred_qty: int
    outstanding_qty: int
    so_count: int
    order_date_min: Optional[date] = None
    order_date_max: Optional[date] = None


class OutstandingDOBlock(BaseModel):
    """Two populations, one block (owner rulings R1 then R6, 13 Sep 2026).

    `do_qty` sums EVERY DO in scope and `delivered_qty` is the rest of it, so
    `do_qty == delivered_qty + pending_qty` holds. `pending_qty`, `do_count` and the
    date range cover DOs that are still outstanding only - "most of the DO are
    delivered right so what's outstanding?" - so the count answers how many DOs are
    still open while the quantities also state what has gone out.
    """

    do_qty: int
    delivered_qty: int
    pending_qty: int
    do_count: int
    do_date_min: Optional[date] = None
    do_date_max: Optional[date] = None


class OutstandingSOLocationRow(BaseModel):
    code: Optional[str] = None
    ordered_qty: int
    outstanding_qty: int


class OutstandingSOCustomerRow(BaseModel):
    customer_name: Optional[str] = None
    ordered_qty: int
    outstanding_qty: int


class OutstandingDOLocationRow(BaseModel):
    """`do_qty` over every DO at this location, `pending_qty` over the outstanding ones
    (R6). A location that only ever had delivered DOs still gets a row, `pending_qty` 0."""

    code: Optional[str] = None
    do_qty: int
    pending_qty: int


class OutstandingDOCustomerRow(BaseModel):
    """As `OutstandingDOLocationRow`, per customer."""

    customer_name: Optional[str] = None
    do_qty: int
    pending_qty: int


class OutstandingSORow(BaseModel):
    so_number: str
    customer_name: Optional[str] = None
    location: Optional[str] = None
    ordered_qty: int
    transferred_qty: int
    outstanding_qty: int
    order_date: Optional[date] = None


class OutstandingDORow(BaseModel):
    """One PENDING delivery order (see `OutstandingDOBlock`).

    R3 (owner ruling, 13 Sep 2026): a ROW states all three quantities - `do_qty`, then
    `delivered_qty`, which is `0` here by construction and is PRINTED as 0 rather than
    omitted ("if it is 0 then we show 0, don't hide"), then `pending_qty`. The block and
    the breakdowns above the list stay pending-only.
    """

    do_number: str
    customer_name: Optional[str] = None
    location: Optional[str] = None
    do_qty: int
    delivered_qty: int
    pending_qty: int
    do_date: Optional[date] = None


class OutstandingReportResponse(BaseModel):
    """`GET /api/v1/order-management/outstanding-report`.

    `so` / `do` is `None` when that scope was not asked (AC-1117) - the ROUTE
    strips the key entirely rather than serializing a null, because the
    chatbot presenter (S1, `sorento_crm_mcp/presenters.py::_outstanding_report`)
    treats "the key is absent" as "not asked" and "present with count 0" as a
    real miss; those are different states and must stay distinguishable on
    the wire, not just in Python.

    Every field below is declared on purpose - a `response_model` silently
    drops any field the schema does not name (see LESSONS-LEARNT.md), so a
    field missing here would vanish from the body with no error anywhere.
    """

    product_code: str
    customer_name: Optional[str] = None
    warehouse_codes: List[str] = []
    order_date_from: Optional[date] = None
    order_date_to: Optional[date] = None
    so: Optional[OutstandingSOBlock] = None
    do: Optional[OutstandingDOBlock] = None
    so_by_location: List[OutstandingSOLocationRow] = []
    so_by_customer: List[OutstandingSOCustomerRow] = []
    do_by_location: List[OutstandingDOLocationRow] = []
    do_by_customer: List[OutstandingDOCustomerRow] = []
    so_rows: List[OutstandingSORow] = []
    do_rows: List[OutstandingDORow] = []
