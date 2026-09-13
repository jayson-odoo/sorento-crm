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
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import Customer, Order, OrderLine, SalesOrder, SalesOrderLine
from app.models.product import Product
from app.services.error_handler import handle_not_found
from app.services.order_service import (
    _delivered_status_ids,
    _outstanding_clause,
    resolve_warehouse_ids,
)

DateLike = Optional[datetime]

# N1 (security review, 13 Sep 2026): `order_service.py` has no equivalent helper
# (grepped) - `product_code_resolution.py::_escape_like` is the established
# pattern this mirrors, kept local rather than imported since that one is
# module-private. Without it, a `customer_query` of e.g. `%` matches every
# customer instead of none, and `_` matches any single character.
_LIKE_ESCAPE = "\\"


def _escape_like(value: str) -> str:
    return (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )


def _dec(v: Any) -> Decimal:
    if v is None:
        return Decimal(0)
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _qty(v: Any) -> int:
    """Every quantity on this report is a WHOLE unit (the schema declares `int` and the
    reply prints thousands-separated units), but `qty_ordered` / `order_lines.quantity`
    are `Numeric(15,4)`, so a fraction is storable. Rounded HALF UP - never Python's
    `round`, whose bankers' rounding would print 2 for 2.5 and 4 for 3.5 in the same
    reply, which reads as an arithmetic error to whoever checks the column."""
    return int(_dec(v).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _rank(rows: list[dict], *, outstanding_key: str, total_key: str, name_key: str) -> list[dict]:
    """R10 (owner ruling, 13 Sep 2026): every breakdown group is ranked by OUTSTANDING
    quantity descending, ties by the total descending, then by name ascending.

    Sorted HERE, once, rather than in each renderer: the reply, a future screen and any
    other reader all show the same order, and the presenter's contract is simply "print
    them in the order given". A NULL name (`Unassigned`) takes its place by its numbers
    like any other name - pinning it to an end would state a ranking the quantities do
    not support.
    """
    return sorted(
        rows,
        key=lambda r: (
            -_dec(r.get(outstanding_key)),
            -_dec(r.get(total_key)),
            str(r.get(name_key) or ""),
        ),
    )


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


def _customer_echo(
    db: Session, customer_query: Optional[str], customer_ids: Optional[list]
) -> Optional[str]:
    """What the reply's `Customer:` line says (AC-1136).

    The CHATBOT filters by `customer_ids` (the resolved entity), never by
    `customer_query`, so echoing the query alone printed `Customer: all` over figures
    that were filtered to one customer. The names are read back and joined by ", ";
    `customer_query` stays the echo when no ids were given (n8n's own path)."""
    if customer_ids:
        names = [
            row[0]
            for row in db.query(Customer.customer_name)
            .filter(Customer.id.in_(customer_ids))
            .order_by(Customer.customer_name)
            .all()
            if row[0]
        ]
        if names:
            return ", ".join(names)
    return customer_query


def outstanding_report(
    db: Session,
    *,
    product_code: Optional[str] = None,
    scope: str = "both",
    customer_query: Optional[str] = None,
    customer_ids: Optional[list[str]] = None,
    warehouse_codes: Optional[list[str]] = None,
    order_date_from: DateLike = None,
    order_date_to: DateLike = None,
) -> dict:
    """R13 (owner ruling, 13 Sep 2026): the report's SUBJECT is a product, a customer, or
    both - "when we generate the outstanding summary for customer and for product it is
    different, they should be the same ... when we ask for customer, the by customer
    section becomes by product section."

    One summary shape, and the subject only decides which breakdown the reader needs:

    * product -> By location + By customer (who is waiting for this product)
    * customer -> By location + By product (what this customer is waiting for)
    * both     -> By location only (the other two would each have one row, naming
                  back what the question already said)

    A group the subject does not want is `None` here and ABSENT from the response, never
    an empty list: "nobody" and "not asked" are different answers.
    """
    product = _resolve_product(db, product_code) if (product_code or "").strip() else None
    if (product_code or "").strip() and product is None:
        raise handle_not_found("Product", product_code)

    warehouse_ids = resolve_warehouse_ids(db, warehouse_codes)
    customer_ids = [str(c).strip() for c in (customer_ids or []) if str(c).strip()] or None
    has_customer = bool(customer_ids) or bool((customer_query or "").strip())

    result: dict = {
        "product_code": product.product_code if product is not None else None,
        "customer_name": _customer_echo(db, customer_query, customer_ids),
        "warehouse_codes": [str(c).strip() for c in (warehouse_codes or []) if str(c).strip()],
        "order_date_from": _as_date(order_date_from),
        "order_date_to": _as_date(order_date_to),
        "so": None,
        "do": None,
        "so_by_location": [],
        "so_by_customer": None if (has_customer or product is None) else [],
        "so_by_product": [] if (has_customer and product is None) else None,
        "do_by_location": [],
        "do_by_customer": None if (has_customer or product is None) else [],
        "do_by_product": [] if (has_customer and product is None) else None,
        "so_rows": [],
        "do_rows": [],
    }

    if scope in ("so", "both"):
        _fill_so(
            db, product, result,
            customer_query=customer_query, customer_ids=customer_ids, warehouse_ids=warehouse_ids,
            order_date_from=order_date_from, order_date_to=order_date_to,
        )
    if scope in ("do", "both"):
        _fill_do(
            db, product, result,
            customer_query=customer_query, customer_ids=customer_ids, warehouse_ids=warehouse_ids,
            order_date_from=order_date_from, order_date_to=order_date_to,
        )
    return result


def _fill_so(
    db: Session,
    product: Product,
    result: dict,
    *,
    customer_query: Optional[str],
    customer_ids: Optional[list],
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
            Product.product_code,
            SalesOrderLine.qty_ordered,
            SalesOrderLine.qty_delivered,
        )
        .join(SalesOrderLine, SalesOrderLine.sales_order_id == SalesOrder.id)
        .join(Product, Product.id == SalesOrderLine.product_id)
        .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
        .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
        .filter(
            SalesOrder.status == "open",
            SalesOrderLine.line_status == "open",
            (SalesOrderLine.qty_ordered - SalesOrderLine.qty_delivered) > 0,
        )
    )
    # R13: the product is the subject only when one was named; a customer-subject ask
    # spans every product that customer is waiting for.
    if product is not None:
        q = q.filter(SalesOrderLine.product_id == product.id)
    if customer_query:
        q = q.filter(
            Customer.customer_name.ilike(
                f"%{_escape_like(customer_query)}%", escape=_LIKE_ESCAPE
            )
        )
    if customer_ids is not None:
        q = q.filter(SalesOrder.customer_id.in_(customer_ids))
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
    by_product: dict = {}
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

        prod_row = by_product.setdefault(
            r.product_code,
            {"product_code": r.product_code, "ordered_qty": Decimal(0), "outstanding_qty": Decimal(0)},
        )
        prod_row["ordered_qty"] += ordered
        prod_row["outstanding_qty"] += ordered - delivered

        so_acc = per_so.setdefault(
            r.so_id,
            {
                "so_number": r.so_number, "customer_name": r.customer_name, "order_date": r.order_date,
                "ordered_qty": Decimal(0), "transferred_qty": Decimal(0), "outstanding_qty": Decimal(0),
                "_locations": set(), "_products": set(),
            },
        )
        so_acc["ordered_qty"] += ordered
        so_acc["transferred_qty"] += delivered
        so_acc["outstanding_qty"] += ordered - delivered
        if r.warehouse_code:
            so_acc["_locations"].add(r.warehouse_code)
        if r.product_code:
            so_acc["_products"].add(r.product_code)

    result["so"] = {
        "ordered_qty": _qty(ordered_total),
        "transferred_qty": _qty(transferred_total),
        "outstanding_qty": _qty(ordered_total - transferred_total),
        "so_count": len(per_so),
        "order_date_min": min(dates) if dates else None,
        "order_date_max": max(dates) if dates else None,
    }
    result["so_by_location"] = _rank(
        [
            {
                "code": v["code"],
                "ordered_qty": _qty(v["ordered_qty"]),
                "outstanding_qty": _qty(v["outstanding_qty"]),
            }
            for v in by_location.values()
        ],
        outstanding_key="outstanding_qty", total_key="ordered_qty", name_key="code",
    )
    if result.get("so_by_customer") is not None:
        result["so_by_customer"] = _rank(
            [
                {
                    "customer_name": v["customer_name"],
                    "ordered_qty": _qty(v["ordered_qty"]),
                    "outstanding_qty": _qty(v["outstanding_qty"]),
                }
                for v in by_customer.values()
            ],
            outstanding_key="outstanding_qty", total_key="ordered_qty", name_key="customer_name",
        )
    if result.get("so_by_product") is not None:
        result["so_by_product"] = _rank(
            [
                {
                    "product_code": v["product_code"],
                    "ordered_qty": _qty(v["ordered_qty"]),
                    "outstanding_qty": _qty(v["outstanding_qty"]),
                }
                for v in by_product.values()
            ],
            outstanding_key="outstanding_qty", total_key="ordered_qty", name_key="product_code",
        )
    # AC-1114: one row per SO, lines rolled up; distinct warehouse codes joined
    # by ", "; sorted by order_date asc then so_number.
    so_rows = [
        {
            "so_number": v["so_number"],
            "customer_name": v["customer_name"],
            # R13: a row always names BOTH axes, whatever the subject - an SO with two
            # products under a customer-subject ask says which ones.
            "product_code": ", ".join(sorted(v["_products"])) if v["_products"] else None,
            "location": ", ".join(sorted(v["_locations"])) if v["_locations"] else None,
            "ordered_qty": _qty(v["ordered_qty"]),
            "transferred_qty": _qty(v["transferred_qty"]),
            "outstanding_qty": _qty(v["outstanding_qty"]),
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
    customer_ids: Optional[list],
    warehouse_ids: Optional[list],
    order_date_from: DateLike,
    order_date_to: DateLike,
) -> None:
    """AC-1115, REWRITTEN FOUR TIMES by the owner's own testing, 13 Sep 2026. R11 is
    the settled one: "the breakdown list should tally with whatever reported at the
    summary at the top."

    ONE population - DOs that are still outstanding (`_outstanding_clause`, the null-safe
    negation of the canonical delivered predicate) - and every figure in the block is
    computed over exactly it: `do_count` counts them, `do_qty` sums their line quantity,
    `pending_qty` is what is still outstanding on them, `delivered_qty` is the difference
    (the part-delivered portion, 0 while a DO is outstanding as a whole), the date range
    spans them, the breakdowns name them and the detail list is them.

    So every number tallies with every other by construction: the breakdown quantities
    sum to the block's, the brackets sum to its Outstanding, and a fully delivered DO
    appears nowhere - not as a total, not as a name with `(O/S: 0)` beside it, not as a
    row. R6's two-population block (totals over every DO, count over the outstanding
    ones) is what made the breakdown disagree with the summary above it.
    """
    delivered_status_ids = _delivered_status_ids(db)
    outstanding_clause = _outstanding_clause(delivered_status_ids)

    q = (
        db.query(
            Order.id.label("do_id"),
            Order.order_number,
            Order.order_date,
            Customer.customer_name,
            Warehouse.warehouse_code,
            Product.product_code,
            OrderLine.quantity,
        )
        .join(OrderLine, OrderLine.order_id == Order.id)
        .join(Product, Product.id == OrderLine.product_id)
        .outerjoin(Customer, Customer.id == Order.customer_id)
        .outerjoin(Warehouse, Warehouse.id == OrderLine.warehouse_id)
        .filter(Order.deleted_at.is_(None))
    )
    # R13: as on the SO side - the product narrows only when one was named.
    if product is not None:
        q = q.filter(OrderLine.product_id == product.id)
    # `None` means no delivered status is configured at all, so every DO is outstanding
    # and no filter is needed (`_outstanding_clause`'s own docstring).
    if outstanding_clause is not None:
        q = q.filter(outstanding_clause)
    if customer_query:
        q = q.filter(
            Customer.customer_name.ilike(
                f"%{_escape_like(customer_query)}%", escape=_LIKE_ESCAPE
            )
        )
    if customer_ids is not None:
        q = q.filter(Order.customer_id.in_(customer_ids))
    if warehouse_ids is not None:
        q = q.filter(OrderLine.warehouse_id.in_(warehouse_ids))
    if order_date_from is not None:
        q = q.filter(Order.order_date >= order_date_from)
    if order_date_to is not None:
        q = q.filter(Order.order_date <= order_date_to)

    do_qty_total = Decimal(0)
    pending_total = Decimal(0)
    dates: list[date] = []
    by_location: dict = {}
    by_customer: dict = {}
    by_product: dict = {}
    per_do: dict = {}

    for r in q.all():
        qty = _dec(r.quantity)
        do_qty_total += qty
        pending_total += qty

        loc = by_location.setdefault(
            r.warehouse_code,
            {"code": r.warehouse_code, "do_qty": Decimal(0), "pending_qty": Decimal(0)},
        )
        loc["do_qty"] += qty
        loc["pending_qty"] += qty

        cust = by_customer.setdefault(
            r.customer_name,
            {"customer_name": r.customer_name, "do_qty": Decimal(0), "pending_qty": Decimal(0)},
        )
        cust["do_qty"] += qty
        cust["pending_qty"] += qty

        prod_row = by_product.setdefault(
            r.product_code,
            {"product_code": r.product_code, "do_qty": Decimal(0), "pending_qty": Decimal(0)},
        )
        prod_row["do_qty"] += qty
        prod_row["pending_qty"] += qty

        if r.order_date:
            dates.append(r.order_date)

        do_acc = per_do.setdefault(
            r.do_id,
            {
                "do_number": r.order_number, "customer_name": r.customer_name, "order_date": r.order_date,
                "pending_qty": Decimal(0),
                "_locations": set(), "_products": set(),
            },
        )
        do_acc["pending_qty"] += qty
        if r.warehouse_code:
            do_acc["_locations"].add(r.warehouse_code)
        if r.product_code:
            do_acc["_products"].add(r.product_code)

    result["do"] = {
        "do_qty": _qty(do_qty_total),
        "delivered_qty": _qty(do_qty_total - pending_total),
        "pending_qty": _qty(pending_total),
        "do_count": len(per_do),
        "do_date_min": min(dates) if dates else None,
        "do_date_max": max(dates) if dates else None,
    }
    result["do_by_location"] = _rank(
        [
            {
                "code": v["code"],
                "do_qty": _qty(v["do_qty"]),
                "pending_qty": _qty(v["pending_qty"]),
            }
            for v in by_location.values()
        ],
        outstanding_key="pending_qty", total_key="do_qty", name_key="code",
    )
    if result.get("do_by_customer") is not None:
        result["do_by_customer"] = _rank(
            [
                {
                    "customer_name": v["customer_name"],
                    "do_qty": _qty(v["do_qty"]),
                    "pending_qty": _qty(v["pending_qty"]),
                }
                for v in by_customer.values()
            ],
            outstanding_key="pending_qty", total_key="do_qty", name_key="customer_name",
        )
    if result.get("do_by_product") is not None:
        result["do_by_product"] = _rank(
            [
                {
                    "product_code": v["product_code"],
                    "do_qty": _qty(v["do_qty"]),
                    "pending_qty": _qty(v["pending_qty"]),
                }
                for v in by_product.values()
            ],
            outstanding_key="pending_qty", total_key="do_qty", name_key="product_code",
        )
    # R3 (owner testing round 2, 13 Sep 2026): "need to show delivered also, doesn't
    # mean if it is 0 then we don't show, if it is 0 then we show 0, don't hide." The
    # ROWS carry `do_qty` and `delivered_qty` again - only the rows: the block and the
    # two breakdowns stay pending-only (R1). `do_qty` is this DO's line quantity for the
    # product and `delivered_qty` is the rest of it, which is 0 by construction here
    # because a delivered DO is not in the population at all - and 0 is PRINTED, which
    # is the whole point of the ruling.
    do_rows = [
        {
            "do_number": v["do_number"],
            "customer_name": v["customer_name"],
            "product_code": ", ".join(sorted(v["_products"])) if v["_products"] else None,
            "location": ", ".join(sorted(v["_locations"])) if v["_locations"] else None,
            "do_qty": _qty(v["pending_qty"]),
            "delivered_qty": 0,
            "pending_qty": _qty(v["pending_qty"]),
            "do_date": v["order_date"],
        }
        for v in per_do.values()
    ]
    do_rows.sort(key=lambda r: (r["do_date"] is None, r["do_date"] or date.min, r["do_number"]))
    result["do_rows"] = do_rows
