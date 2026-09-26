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


class OutstandingSOProductRow(BaseModel):
    """R13: the By product group, for a CUSTOMER-subject report - "when we ask for
    customer, the by customer section becomes by product section"."""

    product_code: Optional[str] = None
    ordered_qty: int
    outstanding_qty: int


class OutstandingDOProductRow(BaseModel):
    """As `OutstandingSOProductRow`, on the DO side."""

    product_code: Optional[str] = None
    do_qty: int
    pending_qty: int


class OutstandingSORow(BaseModel):
    so_number: str
    customer_name: Optional[str] = None
    product_code: Optional[str] = None
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
    product_code: Optional[str] = None
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

    # R13: the SUBJECT may be a customer alone, so the product echo is nullable.
    product_code: Optional[str] = None
    customer_name: Optional[str] = None
    # #1262 slice 9 (F1a): the brand(s) filtered by `brand_ids`, joined by ", " the same
    # way `customer_name` joins several ledgers - `None` when no brand was named, never
    # printed as "all" (the MCP presenter/chatbot header add the "Brand:" line only when
    # this is filled).
    brand_name: Optional[str] = None
    warehouse_codes: List[str] = []
    order_date_from: Optional[date] = None
    order_date_to: Optional[date] = None
    so: Optional[OutstandingSOBlock] = None
    do: Optional[OutstandingDOBlock] = None
    so_by_location: List[OutstandingSOLocationRow] = []
    # R13: which breakdown groups exist depends on the SUBJECT (product -> by_customer,
    # customer -> by_product, both -> neither). A group the subject does not want is
    # `None` here and the route strips the key, the same way it strips an unasked scope:
    # "nobody" and "not asked" are different answers.
    so_by_customer: Optional[List[OutstandingSOCustomerRow]] = None
    so_by_product: Optional[List[OutstandingSOProductRow]] = None
    do_by_location: List[OutstandingDOLocationRow] = []
    do_by_customer: Optional[List[OutstandingDOCustomerRow]] = None
    do_by_product: Optional[List[OutstandingDOProductRow]] = None
    so_rows: List[OutstandingSORow] = []
    do_rows: List[OutstandingDORow] = []


# ---------------------------------------------------------------------------
# sales report - confirmed vs outstanding sales, by month
# (`documentation/plans/chatbot/PLAN-chatbot-sales-report.md` "Backend contract";
# `documentation/plans/chatbot/chatbot-sales-report-acceptance-criteria.md`
# AC-1620 to AC-1632)
# ---------------------------------------------------------------------------
#: Money fields are `float`, never `Decimal` (captain ruling, S2 fix round): a
#: `Decimal` field serialises through `model_dump(mode="json")` as a STRING
#: (`"1234.50"`), which is not the contract - money must be a JSON NUMBER,
#: rounded to 2 places by the service before it reaches this schema. Quantities
#: are `int`, same as `OutstandingSOBlock` above.
class SalesReportProductRow(BaseModel):
    """The By product group, for a CUSTOMER-subject report (S6)."""

    product_code: Optional[str] = None
    ordered_qty: int
    ordered_value: float
    confirmed_qty: int
    confirmed_value: float
    outstanding_qty: int
    outstanding_value: float


class SalesReportCustomerRow(BaseModel):
    """As `SalesReportProductRow`, for a PRODUCT-subject report."""

    customer_name: Optional[str] = None
    ordered_qty: int
    ordered_value: float
    confirmed_qty: int
    confirmed_value: float
    outstanding_qty: int
    outstanding_value: float


class SalesReportMonth(BaseModel):
    """One month bucket (S3: `required_date`, else the SO's `order_date`).

    `by_product` / `by_customer` follow the report's SUBJECT (AC-1628): a
    customer-subject ask carries `by_product`, a product-subject ask carries
    `by_customer`, both named carries NEITHER - the route strips whichever key
    the subject does not want (`None` here is not asked, an empty list would be
    asked-and-nobody, a different fact).
    """

    month: str
    so_count: int
    ordered_qty: int
    ordered_value: float
    confirmed_qty: int
    confirmed_value: float
    outstanding_qty: int
    outstanding_value: float
    by_product: Optional[List[SalesReportProductRow]] = None
    by_customer: Optional[List[SalesReportCustomerRow]] = None


class SalesReportSORow(BaseModel):
    """One SO, lines rolled up over the WHOLE filtered window (AC-1629) - no
    `product_code` (unlike `OutstandingSORow`): the plan's own contract table
    for `so_rows[]` never names one, and the presenter's detail reply (S1)
    never prints a Product line for this report."""

    so_number: str
    customer_name: Optional[str] = None
    location: Optional[str] = None
    order_date: Optional[date] = None
    ordered_qty: int
    ordered_value: float
    confirmed_qty: int
    confirmed_value: float
    outstanding_qty: int
    outstanding_value: float
    #: S19/AC-1633: the SO's own DISTINCT matched product codes, comma joined -
    #: present ONLY when a `product_code` filter was given (absent otherwise,
    #: never an empty string). The presenter reads it absent-safe so an OLD
    #: body (deployed before this field existed) still renders.
    product_codes: Optional[str] = None


class SalesReportResponse(BaseModel):
    """`GET /api/v1/order-management/sales-report`.

    `so_rows` is `None` (and the route strips the key entirely) unless the
    caller asked `detail=so` (captain ruling, S2 fix round): a big dealer is
    1,230 SOs, so the service never computes or sends them unasked - the SAME
    "declared but stripped by the route when unset" pattern
    `OutstandingReportResponse.so`/`do` already use above.

    Every field is declared on purpose - `response_model` silently drops any
    field the schema does not name (LESSONS-LEARNT.md).
    """

    customer_name: Optional[str] = None
    product_code: Optional[str] = None
    #: S19: the DISTINCT product codes matched by `product_code`'s prefix rule
    #: THAT HAVE ROWS in the filtered report, sorted ascending. `[]` when no
    #: product filter was given (AC-1631, AC-1633).
    product_codes: List[str] = []
    channel: Optional[str] = None
    # Echo only (S9), same contract as `OutstandingReportResponse`'s route-level
    # `location_token` handling - never filters, always present on this report's
    # body (AC-1631), unlike the outstanding route where it is tacked onto the
    # body only when given.
    location_token: Optional[str] = None
    warehouse_codes: List[str] = []
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    months: List[SalesReportMonth] = []
    so_rows: Optional[List[SalesReportSORow]] = None
