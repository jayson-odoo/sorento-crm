"""A frozen copy of the sales type expression as main had it before INVOICED-CHANNEL-PERF (not a
test module). `tests/test_invoiced_channel_perf.py` compares the rewritten
`app.services.sales.invoiced_sales.sales_type()` against it line by line, so the rewrite is pinned
to give exactly the old values. Do not edit it to follow a rule change: change the rule and its own
tests, then delete this file.
"""
from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import aliased

from app.models.finance import BillingDocument, BillingDocumentLine
from app.models.order import Order, OrderLine, SalesOrder, SalesOrderLine
from app.models.sales import SetApartCustomer
from app.services.sales.invoiced_sales import (
    _CLASS_TYPES, MIXED, NO_SALES_ORDER, SALES_TYPES, SET_APART, TYPE_NOT_SET,
)


def _traced_sales_order_ids(document_id: Any, company_id: Any) -> Any:
    """SELECT of the ids of the sales orders the billing document `document_id` traces to by its
    own lines, matched on `company_id` (DOC-RELATIONS' rules; see the module docstring)."""
    line = aliased(BillingDocumentLine)
    so_line = aliased(SalesOrderLine)
    so = aliased(SalesOrder)
    do = aliased(Order)
    do_line = aliased(OrderLine)
    do_so_line = aliased(SalesOrderLine)
    do_so = aliased(SalesOrder)

    via_line = (
        sa.select(so_line.sales_order_id)
        .join(line, line.sales_order_line_id == so_line.id)
        .where(line.document_id == document_id)
    )
    via_so_number = (
        sa.select(so.id)
        .join(line, sa.and_(line.from_doc_type == "SO", line.from_doc_no == so.so_number))
        .where(line.document_id == document_id, so.company_id == company_id)
    )
    # A DO named by number (not deleted; a cancelled DO still links on this side, as
    # `relations_for_billing_document` resolves it), then that DO's own sales orders.
    do_ids = (
        sa.select(do.id)
        .correlate(BillingDocument)
        .join(line, sa.and_(line.from_doc_type == "DO", line.from_doc_no == do.order_number))
        .where(
            line.document_id == document_id,
            do.company_id == company_id,
            do.deleted_at.is_(None),
        )
    )
    via_do_line = (
        sa.select(do_so_line.sales_order_id)
        .join(do_line, do_line.sales_order_line_id == do_so_line.id)
        .where(do_line.order_id.in_(do_ids))
    )
    via_do_number = (
        sa.select(do_so.id)
        .join(
            do_line,
            sa.and_(
                do_line.from_doc_no == do_so.so_number,
                sa.or_(do_line.from_doc_type.is_(None), do_line.from_doc_type == "SO"),
            ),
        )
        .where(do_line.order_id.in_(do_ids), do_so.company_id == company_id)
    )
    via_do_header = sa.select(do.sales_order_id).where(
        do.id.in_(do_ids), do.sales_order_id.isnot(None)
    )
    return sa.union(
        *(
            part.correlate(BillingDocument)
            for part in (via_line, via_so_number, via_do_line, via_do_number, via_do_header)
        )
    )


def _sales_order_class_kind(in_traced: Any) -> Any:
    """The sales type the traced sales orders give (`in_traced(so_id_column)` says which):
    none -> no sales order; two or more classes -> mixed; no class at all -> type not set;
    else the one class's type."""
    so = aliased(SalesOrder)
    classes = sa.func.count(sa.distinct(so.demand_class))
    one = sa.func.max(so.demand_class)
    return (
        sa.select(
            sa.case(
                (sa.func.count(so.id) == 0, sa.literal(NO_SALES_ORDER)),
                (classes > 1, sa.literal(MIXED)),
                (classes == 0, sa.literal(TYPE_NOT_SET)),
                *[(one == cls, sa.literal(kind)) for cls, kind in _CLASS_TYPES.items()],
                else_=sa.literal(TYPE_NOT_SET),
            )
        )
        .where(in_traced(so.id))
        .correlate(BillingDocument).scalar_subquery()
    )


def in_traced_sales_orders(so_id: Any) -> Any:
    """`so_id` is one of the sales orders this document's figures follow: its own traced
    orders, else (a credit or debit note with no traced line) its invoice's."""
    own = _traced_sales_order_ids(BillingDocument.id, BillingDocument.company_id)
    has_own = (
        sa.select(sa.func.count()).select_from(own.subquery("own_ids")).correlate(BillingDocument).scalar_subquery() > 0
    )
    inherited = _traced_sales_order_ids(
        BillingDocument.against_document_id, BillingDocument.company_id
    )
    return sa.or_(
        so_id.in_(own),
        sa.and_(BillingDocument.against_document_id.isnot(None), ~has_own, so_id.in_(inherited)),
    )


def _set_apart() -> Any:
    row = aliased(SetApartCustomer)
    month = sa.cast(sa.func.date_trunc("month", BillingDocument.doc_date), sa.Date)
    return sa.exists(
        sa.select(row.id).where(
            row.company_id == BillingDocument.company_id,
            row.customer_id == BillingDocument.customer_id,
            row.from_month <= month,
            sa.or_(row.to_month.is_(None), row.to_month >= month),
        ).correlate(BillingDocument)
    )


def sales_type() -> Any:
    """The document's sales type value (`SALES_TYPES`), first match wins: set apart, then the
    traced sales orders' class, then no sales order."""
    return sa.case(
        (_set_apart(), sa.literal(SET_APART)),
        else_=_sales_order_class_kind(in_traced_sales_orders),
    )


def sales_type_label() -> Any:
    value = sales_type()
    return sa.case(
        *[(value == key, sa.literal(label)) for key, label in SALES_TYPES],
        else_=sa.null(),
    )
