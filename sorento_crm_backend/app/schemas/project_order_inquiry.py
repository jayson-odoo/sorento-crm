"""Order inquiry schemas (P10, AC-I1 to AC-I7).

A row is one instruction to purchasing. It carries the sales order NUMBER rather than its
id, the item CODE rather than the product id, and the warehouse CODE rather than the
warehouse id, so nothing on this screen is a UUID a person has to resolve for themselves.

``remark`` is the same field the client's own spreadsheet calls REMARK: the verb in their
spelling, or the SPO reference itself for a row already on the water. It ships beside the
raw ``verb`` so the screen can colour by verb while printing what purchasing reads.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class OrderInquiryRowOut(BaseModel):
    id: str
    order_inquiry_id: str
    so_line_id: Optional[str] = None
    project_sales_order_id: Optional[str] = None
    sales_order_ref: Optional[str] = None
    # AC-D06: the Project SO reference, its line number and the decision revision the Buy
    # came from. Absent on an amendment exception row, which no revision decided.
    project_so_ref: Optional[str] = None
    line_no: Optional[int] = None
    decision_revision: Optional[int] = None
    so_date: Optional[datetime] = None
    project_customer: Optional[str] = None
    is_amendment: bool = False

    item_code: Optional[str] = None
    qty: str
    delivery_date: Optional[date] = None
    # Empty when no allocation has been confirmed yet (AC-H5). Never defaulted.
    stock_location: Optional[str] = None
    verb: str
    remark: Optional[str] = None
    spo_ref: Optional[str] = None
    covered_by: Optional[str] = None
    note: Optional[str] = None
    # The outstanding supplier PO this row was tagged to (section G). Blank until
    # "Place on PO" is used; never a guess at what would cover it.
    po_ref: Optional[str] = None
    po_line_id: Optional[str] = None

    state: str
    actioned_at: Optional[datetime] = None
    actioned_by_name: Optional[str] = None
    created_at: Optional[datetime] = None


class OrderInquiryDetail(BaseModel):
    id: str
    project_sales_order_id: str
    amendment_id: Optional[str] = None
    state: str
    raised_at: Optional[datetime] = None
    # The purchasing task the rows are attached to (AC-I4).
    task_id: Optional[str] = None
    task_name: Optional[str] = None
    rows: List[OrderInquiryRowOut] = []


class OrderInquirySummary(BaseModel):
    total: int = 0
    raised: int = 0
    actioned: int = 0
    cancelled: int = 0


class OrderInquiryWorklistRow(BaseModel):
    """One instruction on purchasing's own list, in the spreadsheet's columns.

    Same vocabulary as the per-project row above - the sales order NUMBER, the item CODE,
    a quantity as a string - plus the three facts the cross-project view needs and the
    per-project one does not: which document to open (a core sales order for an adopted
    record, the project document for an authored one), who it is for when there is no
    project to name, and whether anybody has placed it yet.
    """

    id: str
    so_date: Optional[date] = None
    so_number: Optional[str] = None
    item_code: Optional[str] = None
    product_name: Optional[str] = None
    qty: str
    delivery_date: Optional[date] = None
    project_customer: Optional[str] = None
    # Blank until the row traces to a placed purchase order. Never a guess at who would
    # supply it: purchasing reads a filled cell as a statement that an order exists.
    supplier: Optional[str] = None
    supplier_id: Optional[str] = None
    po_number: Optional[str] = None
    # The location the PO is placed for: the donor to order back for an order-back row,
    # the confirmed allocation's warehouse for a plan/confirmed row, otherwise the line's
    # own fulfilment location. Blank when neither is known.
    location: Optional[str] = None
    # Who sold it (`sales_orders.sales_agent_id` -> `sales_agents`), read off the same core
    # sales order the SO DATE / S/O NO columns already join to. Null on an authored row
    # that reaches no core order and on one whose core order carries no agent.
    agent_code: Optional[str] = None
    agent_label: Optional[str] = None
    state: str
    raised_at: Optional[datetime] = None
    verb: str
    note: Optional[str] = None

    # Addressing only, never rendered.
    project_id: Optional[str] = None
    project_sales_order_id: Optional[str] = None
    core_sales_order_id: Optional[str] = None
    is_adopted: bool = False


class OrderInquiryMonthTotal(BaseModel):
    month: str
    #: `JAN 26`, spelled the way their sheet tab is.
    label: str
    rows: int = 0
    qty: str = "0"


class OrderInquiryFacet(BaseModel):
    id: str
    label: str
    rows: int = 0


class OrderInquiryStateCounts(BaseModel):
    raised: int = 0
    actioned: int = 0
    cancelled: int = 0
    total: int = 0


class OrderInquiryWorklistSummary(BaseModel):
    """The strip above the list, and the three controls beside it.

    The totals honour every filter, the month included, because they describe what is on
    screen. The three axes each drop their OWN filter, because a control that empties
    itself the moment it is used cannot be used a second time.
    """

    total_rows: int = 0
    total_qty: str = "0"
    by_state: OrderInquiryStateCounts = OrderInquiryStateCounts()
    by_month: List[OrderInquiryMonthTotal] = []
    suppliers: List[OrderInquiryFacet] = []
    projects: List[OrderInquiryFacet] = []


class MarkInquiryRowsRequest(BaseModel):
    row_ids: List[str] = Field(..., min_length=1)
    state: str = Field(..., description="raised, actioned or cancelled")


class OrderInquiryPoCandidate(BaseModel):
    """One open supplier PO line this row could be tagged to (section G).

    Ordered soonest `expected_date` first; `recommended` marks the earliest one whose
    `remaining` balance covers the row's whole quantity. `already_tagged` is what OTHER
    placed rows already claim off this same line, so `remaining` is never a promise this
    line cannot keep.
    """

    po_line_id: str
    po_number: str
    supplier_name: Optional[str] = None
    expected_date: Optional[date] = None
    qty_ordered: str
    qty_received: str
    already_tagged: str
    remaining: str
    covers: bool
    recommended: bool = False


class PlaceOnPoRequest(BaseModel):
    po_line_id: str = Field(..., description="One of the row's own PO candidates.")
