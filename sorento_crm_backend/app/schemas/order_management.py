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


class OutstandingSOBlock(BaseModel):
    ordered_qty: int
    transferred_qty: int
    outstanding_qty: int
    so_count: int
    order_date_min: Optional[date] = None
    order_date_max: Optional[date] = None


class OutstandingDOBlock(BaseModel):
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
    code: Optional[str] = None
    do_qty: int
    pending_qty: int


class OutstandingDOCustomerRow(BaseModel):
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
