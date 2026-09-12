"""Outstanding report: SO backlog + DO pending, one product at a time.

`documentation/plans/chatbot/PLAN-chatbot-outstanding-report.md` ("Backend
contract"); `documentation/plans/chatbot/chatbot-outstanding-report-acceptance-criteria.md`
AC-1110 to AC-1119.

One function, two base SQL queries (every open SO line for the product, every
DO line for the product) - every total, breakdown group and row list below is
rolled up from those two result sets in Python, so "Ordered = Transferred +
Outstanding" (SO) and "DO qty = Delivered + Pending" (DO) are ARITHMETIC over
the SAME population, never two queries that could silently drift apart (the
defect this route replaces - see the plan's "Why", items 1 and 3).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import Customer, Order, OrderLine, SalesOrder, SalesOrderLine
from app.models.product import Product
from app.services.error_handler import handle_not_found
from app.services.order_service import (
    _delivered_clause,
    _delivered_status_ids,
    _plain_number,
    resolve_warehouse_ids,
)

DateLike = Optional[datetime]


def _dec(v: Any) -> Decimal:
    if v is None:
        return Decimal(0)
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _as_date(v: DateLike) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    return v


def _resolve_product(db: Session, product_code: str) -> Optional[Product]:
    code = (product_code or "").strip()
    if not code:
        return None
    return (
        db.query(Product)
        .filter(func.lower(Product.product_code) == code.lower())
        .first()
    )


def outstanding_report(
    db: Session,
    *,
    product_code: str,
    scope: str = "both",
    customer_query: Optional[str] = None,
    warehouse_codes: Optional[list[str]] = None,
    order_date_from: DateLike = None,
    order_date_to: DateLike = None,
) -> dict:
    product = _resolve_product(db, product_code)
    if product is None:
        raise handle_not_found("Product", product_code)

    warehouse_ids = resolve_warehouse_ids(db, warehouse_codes)

    result: dict = {
        "product_code": product.product_code,
        "customer_name": customer_query,
        "warehouse_codes": [str(c).strip() for c in (warehouse_codes or []) if str(c).strip()],
        "order_date_from": _as_date(order_date_from),
        "order_date_to": _as_date(order_date_to),
        "so": None,
        "do": None,
        "so_by_location": [],
        "so_by_customer": [],
        "do_by_location": [],
        "do_by_customer": [],
        "so_rows": [],
        "do_rows": [],
    }

    if scope in ("so", "both"):
        _fill_so(
            db, product, result,
            customer_query=customer_query, warehouse_ids=warehouse_ids,
            order_date_from=order_date_from, order_date_to=order_date_to,
        )
    if scope in ("do", "both"):
        _fill_do(
            db, product, result,
            customer_query=customer_query, warehouse_ids=warehouse_ids,
            order_date_from=order_date_from, order_date_to=order_date_to,
        )
    return result


def _fill_so(
    db: Session,
    product: Product,
    result: dict,
    *,
    customer_query: Optional[str],
    warehouse_ids: Optional[list],
    order_date_from: DateLike,
    order_date_to: DateLike,
) -> None:
    """AC-1110: ONE predicate for every SO figure - header `status='open'`, line
    `line_status='open'`, `qty_ordered - qty_delivered > 0` - so cancelled and
    retired-provisional (closed) lines contribute to nothing below, and
    `ordered_qty == transferred_qty + outstanding_qty` holds by construction.
    """
    q = (
        db.query(
            SalesOrder.id.label("so_id"),
            SalesOrder.so_number,
            SalesOrder.order_date,
            Customer.customer_name,
            Warehouse.warehouse_code,
            SalesOrderLine.qty_ordered,
            SalesOrderLine.qty_delivered,
        )
        .join(SalesOrderLine, SalesOrderLine.sales_order_id == SalesOrder.id)
        .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
        .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
        .filter(
            SalesOrder.status == "open",
            SalesOrderLine.line_status == "open",
            SalesOrderLine.product_id == product.id,
            (SalesOrderLine.qty_ordered - SalesOrderLine.qty_delivered) > 0,
        )
    )
    if customer_query:
        q = q.filter(Customer.customer_name.ilike(f"%{customer_query}%"))
    if warehouse_ids is not None:
        q = q.filter(SalesOrderLine.warehouse_id.in_(warehouse_ids))
    if order_date_from is not None:
        q = q.filter(SalesOrder.order_date >= order_date_from)
    if order_date_to is not None:
        q = q.filter(SalesOrder.order_date <= order_date_to)

    ordered_total = Decimal(0)
    transferred_total = Decimal(0)
    dates: list[date] = []
    by_location: dict = {}
    by_customer: dict = {}
    per_so: dict = {}

    for r in q.all():
        ordered = _dec(r.qty_ordered)
        delivered = _dec(r.qty_delivered)
        ordered_total += ordered
        transferred_total += delivered
        if r.order_date:
            dates.append(r.order_date)

        loc = by_location.setdefault(
            r.warehouse_code,
            {"code": r.warehouse_code, "ordered_qty": Decimal(0), "outstanding_qty": Decimal(0)},
        )
        loc["ordered_qty"] += ordered
        loc["outstanding_qty"] += ordered - delivered

        cust = by_customer.setdefault(
            r.customer_name,
            {"customer_name": r.customer_name, "ordered_qty": Decimal(0), "outstanding_qty": Decimal(0)},
        )
        cust["ordered_qty"] += ordered
        cust["outstanding_qty"] += ordered - delivered

        so_acc = per_so.setdefault(
            r.so_id,
            {
                "so_number": r.so_number, "customer_name": r.customer_name, "order_date": r.order_date,
                "ordered_qty": Decimal(0), "transferred_qty": Decimal(0), "outstanding_qty": Decimal(0),
                "_locations": set(),
            },
        )
        so_acc["ordered_qty"] += ordered
        so_acc["transferred_qty"] += delivered
        so_acc["outstanding_qty"] += ordered - delivered
        if r.warehouse_code:
            so_acc["_locations"].add(r.warehouse_code)

    result["so"] = {
        "ordered_qty": _plain_number(ordered_total),
        "transferred_qty": _plain_number(transferred_total),
        "outstanding_qty": _plain_number(ordered_total - transferred_total),
        "so_count": len(per_so),
        "order_date_min": min(dates) if dates else None,
        "order_date_max": max(dates) if dates else None,
    }
    result["so_by_location"] = [
        {
            "code": v["code"],
            "ordered_qty": _plain_number(v["ordered_qty"]),
            "outstanding_qty": _plain_number(v["outstanding_qty"]),
        }
        for v in by_location.values()
    ]
    result["so_by_customer"] = [
        {
            "customer_name": v["customer_name"],
            "ordered_qty": _plain_number(v["ordered_qty"]),
            "outstanding_qty": _plain_number(v["outstanding_qty"]),
        }
        for v in by_customer.values()
    ]
    # AC-1114: one row per SO, lines rolled up; distinct warehouse codes joined
    # by ", "; sorted by order_date asc then so_number.
    so_rows = [
        {
            "so_number": v["so_number"],
            "customer_name": v["customer_name"],
            "location": ", ".join(sorted(v["_locations"])) if v["_locations"] else None,
            "ordered_qty": _plain_number(v["ordered_qty"]),
            "transferred_qty": _plain_number(v["transferred_qty"]),
            "outstanding_qty": _plain_number(v["outstanding_qty"]),
            "order_date": v["order_date"],
        }
        for v in per_so.values()
    ]
    so_rows.sort(key=lambda r: (r["order_date"] is None, r["order_date"] or date.min, r["so_number"]))
    result["so_rows"] = so_rows


def _fill_do(
    db: Session,
    product: Product,
    result: dict,
    *,
    customer_query: Optional[str],
    warehouse_ids: Optional[list],
    order_date_from: DateLike,
    order_date_to: DateLike,
) -> None:
    """AC-1115 (captain ruling, 12 Sep 2026): the `do` block carries the SAME
    identity as the `so` block. The population is every DO line for the
    product - `_delivered_clause` (`order_service.py`) is the canonical
    "handed to the customer" predicate and its null-safe negation
    (`_outstanding_clause`) is everything else, so classifying each row by
    `is_delivered` alone already exhausts the population: `do_qty =
    delivered_qty + pending_qty` holds by construction, `do_count` counts
    both, and `do_rows[]` lists both kinds of DO.
    """
    delivered_status_ids = _delivered_status_ids(db)
    delivered_clause = _delivered_clause(delivered_status_ids)

    q = (
        db.query(
            Order.id.label("do_id"),
            Order.order_number,
            Order.order_date,
            Customer.customer_name,
            Warehouse.warehouse_code,
            OrderLine.quantity,
            case((delivered_clause, True), else_=False).label("is_delivered"),
        )
        .join(OrderLine, OrderLine.order_id == Order.id)
        .outerjoin(Customer, Customer.id == Order.customer_id)
        .outerjoin(Warehouse, Warehouse.id == OrderLine.warehouse_id)
        .filter(Order.deleted_at.is_(None), OrderLine.product_id == product.id)
    )
    if customer_query:
        q = q.filter(Customer.customer_name.ilike(f"%{customer_query}%"))
    if warehouse_ids is not None:
        q = q.filter(OrderLine.warehouse_id.in_(warehouse_ids))
    if order_date_from is not None:
        q = q.filter(Order.order_date >= order_date_from)
    if order_date_to is not None:
        q = q.filter(Order.order_date <= order_date_to)

    do_qty_total = Decimal(0)
    delivered_total = Decimal(0)
    pending_total = Decimal(0)
    dates: list[date] = []
    by_location: dict = {}
    by_customer: dict = {}
    per_do: dict = {}

    for r in q.all():
        qty = _dec(r.quantity)
        do_qty_total += qty
        if r.is_delivered:
            delivered_total += qty
        else:
            pending_total += qty
        if r.order_date:
            dates.append(r.order_date)

        loc = by_location.setdefault(
            r.warehouse_code, {"code": r.warehouse_code, "do_qty": Decimal(0), "pending_qty": Decimal(0)}
        )
        loc["do_qty"] += qty
        if not r.is_delivered:
            loc["pending_qty"] += qty

        cust = by_customer.setdefault(
            r.customer_name, {"customer_name": r.customer_name, "do_qty": Decimal(0), "pending_qty": Decimal(0)}
        )
        cust["do_qty"] += qty
        if not r.is_delivered:
            cust["pending_qty"] += qty

        do_acc = per_do.setdefault(
            r.do_id,
            {
                "do_number": r.order_number, "customer_name": r.customer_name, "order_date": r.order_date,
                "do_qty": Decimal(0), "delivered_qty": Decimal(0), "pending_qty": Decimal(0),
                "_locations": set(),
            },
        )
        do_acc["do_qty"] += qty
        if r.is_delivered:
            do_acc["delivered_qty"] += qty
        else:
            do_acc["pending_qty"] += qty
        if r.warehouse_code:
            do_acc["_locations"].add(r.warehouse_code)

    result["do"] = {
        "do_qty": _plain_number(do_qty_total),
        "delivered_qty": _plain_number(delivered_total),
        "pending_qty": _plain_number(pending_total),
        "do_count": len(per_do),
        "do_date_min": min(dates) if dates else None,
        "do_date_max": max(dates) if dates else None,
    }
    result["do_by_location"] = [
        {
            "code": v["code"],
            "do_qty": _plain_number(v["do_qty"]),
            "pending_qty": _plain_number(v["pending_qty"]),
        }
        for v in by_location.values()
    ]
    result["do_by_customer"] = [
        {
            "customer_name": v["customer_name"],
            "do_qty": _plain_number(v["do_qty"]),
            "pending_qty": _plain_number(v["pending_qty"]),
        }
        for v in by_customer.values()
    ]
    do_rows = [
        {
            "do_number": v["do_number"],
            "customer_name": v["customer_name"],
            "location": ", ".join(sorted(v["_locations"])) if v["_locations"] else None,
            "do_qty": _plain_number(v["do_qty"]),
            "delivered_qty": _plain_number(v["delivered_qty"]),
            "pending_qty": _plain_number(v["pending_qty"]),
            "do_date": v["order_date"],
        }
        for v in per_do.values()
    ]
    do_rows.sort(key=lambda r: (r["do_date"] is None, r["do_date"] or date.min, r["do_number"]))
    result["do_rows"] = do_rows
