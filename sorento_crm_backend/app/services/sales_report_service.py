"""Sales report: confirmed vs outstanding sales, by month.

`documentation/plans/chatbot/PLAN-chatbot-sales-report.md` ("Backend contract");
`documentation/plans/chatbot/chatbot-sales-report-acceptance-criteria.md`
AC-1620 to AC-1632.

ONE base query over `sales_order_lines` (joined to `sales_orders`, `customers`,
`products`, `warehouses`), excluding only cancelled headers/lines - everything
else (the month bucket, the confirmed/outstanding split, the breakdown ranks,
`so_rows`) is rolled up from that SAME result set in Python, so a total can
never drift from the rows that made it (the same reason
`outstanding_report_service.py` gives for its own two base queries).

Per line (S2 rulings):

* `bucket` = `required_date`, else the SO's `order_date` (S3).
* `confirmed_qty = min(qty_delivered, qty_ordered)` - never more than ordered.
* `confirmed_value = line_total * confirmed_qty / qty_ordered`, 0 when
  `qty_ordered` is 0 (never a division error).
* `outstanding_qty` / `outstanding_value` are the REST of the line, counted
  ONLY while the header is `status='open'` AND the line is `line_status='open'`
  - a closed-but-underdelivered line (a data anomaly, not a real one in this
  schema) simply reports less than its `line_total`, rather than raising.
* `ordered = confirmed + outstanding`, by construction (S2).

A line with no bucket at all (neither `required_date` nor its SO's
`order_date`) cannot be placed in any month, so it is excluded from
EVERYTHING - not just `months[]` but also `so_rows[]` - which is what keeps
"row sums equal month sums" (AC-1629) true unconditionally rather than only on
the cases a test happens to cover.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product
from app.services.error_handler import handle_not_found
from app.services.order_service import resolve_warehouse_ids
from app.services.outstanding_report_service import _customer_echo

DateLike = Optional[datetime]

# Same reasoning outstanding_report_service.py gives for its own copy: the
# canonical escaper lives on `product_code_resolution.py` but is module-private,
# so a tiny local copy beats reaching across modules for five lines of LIKE
# escaping.
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


def _qty(v: Decimal) -> int:
    """Every quantity on this report is a WHOLE unit (the schema declares `int`
    and the reply prints thousands-separated units), but `qty_ordered` /
    `qty_delivered` are `Numeric(15,4)`, so a fraction is storable. Rounded HALF
    UP - never Python's `round`, whose bankers' rounding would print 2 for 2.5
    and 4 for 3.5 in the same reply."""
    return int(v.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _money_edge(v: Decimal) -> float:
    """Quantise to 2 places AT THE RESPONSE EDGE and hand back a `float`, so it
    serialises as a JSON NUMBER (captain ruling, S2 fix round) - a `Decimal`
    field serialises as a STRING through `model_dump(mode="json")`, which is
    not the contract. Every internal accumulation before this point stays
    `Decimal`."""
    return float(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _as_date(v: DateLike) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    return v


def _resolve_product(db: Session, product_code: Optional[str]) -> Optional[Product]:
    code = (product_code or "").strip()
    if not code:
        return None
    return (
        db.query(Product)
        .filter(func.lower(Product.product_code) == code.lower())
        .first()
    )


def _rank_breakdown(rows: list[dict], *, name_key: str) -> list[dict]:
    """S6: ranked by `ordered_value` descending, ties by `ordered_qty`
    descending, then name ascending. Sorted HERE, once - the presenter's
    contract is "print them in the order given" (AC-1608), never re-sort."""
    return sorted(
        rows,
        key=lambda r: (
            -r["ordered_value"],
            -r["ordered_qty"],
            str(r.get(name_key) or ""),
        ),
    )


def _new_figures() -> dict:
    return {
        "ordered_qty": Decimal(0), "ordered_value": Decimal(0),
        "confirmed_qty": Decimal(0), "confirmed_value": Decimal(0),
        "outstanding_qty": Decimal(0), "outstanding_value": Decimal(0),
    }


def _accumulate(acc: dict, *, ordered_qty, ordered_value, confirmed_qty, confirmed_value,
                outstanding_qty, outstanding_value) -> None:
    acc["ordered_qty"] += ordered_qty
    acc["ordered_value"] += ordered_value
    acc["confirmed_qty"] += confirmed_qty
    acc["confirmed_value"] += confirmed_value
    acc["outstanding_qty"] += outstanding_qty
    acc["outstanding_value"] += outstanding_value


def _quantised_figures(acc: dict) -> dict:
    return {
        "ordered_qty": _qty(acc["ordered_qty"]), "ordered_value": _money_edge(acc["ordered_value"]),
        "confirmed_qty": _qty(acc["confirmed_qty"]), "confirmed_value": _money_edge(acc["confirmed_value"]),
        "outstanding_qty": _qty(acc["outstanding_qty"]), "outstanding_value": _money_edge(acc["outstanding_value"]),
    }


def sales_report(
    db: Session,
    *,
    product_code: Optional[str] = None,
    customer_query: Optional[str] = None,
    customer_ids: Optional[list[str]] = None,
    channel: Optional[str] = None,
    warehouse_codes: Optional[list[str]] = None,
    date_from: DateLike = None,
    date_to: DateLike = None,
    detail: Optional[str] = None,
) -> dict:
    """S7: the SUBJECT is a product, a customer, or both - never neither (the
    ROUTE raises 422 `subject_required` before calling this). `channel` is
    already normalised to `"dealer"` / `"project"` / `None` by the route (S8);
    `detail` is `"so"` or `None` - `so_rows` is computed ONLY when it is `"so"`
    (captain ruling: a big dealer is 1,230 SOs, never build that unasked)."""
    product = _resolve_product(db, product_code) if (product_code or "").strip() else None
    if (product_code or "").strip() and product is None:
        raise handle_not_found("Product", product_code)

    warehouse_ids = resolve_warehouse_ids(db, warehouse_codes)
    customer_ids = [str(c).strip() for c in (customer_ids or []) if str(c).strip()] or None
    has_customer = bool(customer_ids) or bool((customer_query or "").strip())
    has_product = product is not None
    # S6/AC-1628: customer subject -> By product; product subject -> By customer;
    # both named -> neither breakdown.
    want_by_product = has_customer and not has_product
    want_by_customer = has_product and not has_customer
    want_so_rows = (detail or "").strip().lower() == "so"

    q = (
        db.query(
            SalesOrder.id.label("so_id"),
            SalesOrder.so_number,
            SalesOrder.order_date,
            SalesOrder.created_at,
            SalesOrder.status.label("so_status"),
            SalesOrder.demand_class,
            Customer.customer_name,
            Warehouse.warehouse_code,
            Product.product_code,
            SalesOrderLine.qty_ordered,
            SalesOrderLine.qty_delivered,
            SalesOrderLine.line_total,
            SalesOrderLine.line_status,
            SalesOrderLine.required_date,
        )
        .join(SalesOrderLine, SalesOrderLine.sales_order_id == SalesOrder.id)
        .join(Product, Product.id == SalesOrderLine.product_id)
        .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
        .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
        .filter(
            SalesOrder.status != "cancelled",
            SalesOrderLine.line_status != "cancelled",
        )
    )
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
    if channel == "dealer":
        q = q.filter(SalesOrder.demand_class == "retail")
    elif channel == "project":
        q = q.filter(SalesOrder.demand_class == "project")
    if date_from is not None or date_to is not None:
        # S3/AC-1623: the window filters on the SAME bucket date each row uses
        # below (required_date, else order_date) - never order_date alone, or a
        # July-only window would keep a June-order/July-required line's SIBLING
        # row (same SO, a June-required line) too. Expressed as SQL so a line
        # whose bucket falls outside the window is dropped before Python ever
        # sees it, matching the identical predicate the Python loop bucket uses.
        bucket_expr = func.coalesce(SalesOrderLine.required_date, SalesOrder.order_date)
        if date_from is not None:
            q = q.filter(bucket_expr >= _as_date(date_from))
        if date_to is not None:
            q = q.filter(bucket_expr <= _as_date(date_to))

    months_acc: dict[str, dict] = {}
    month_so_ids: dict[str, set] = {}
    month_product_acc: dict[str, dict[str, dict]] = {}
    month_customer_acc: dict[str, dict[str, dict]] = {}
    so_acc: dict[str, dict] = {}

    for r in q.all():
        # S3's bucket is `required_date`, else `order_date` - both are nullable
        # in this schema, so a line with NEITHER (no plan/UAC case covers this)
        # falls back a third time to its SO's `created_at`, which the model
        # declares NOT NULL (`server_default=func.now()`), so a row is never
        # silently dropped from every total for want of a date to bucket it by.
        bucket_date = r.required_date or r.order_date or r.created_at.date()
        month_key = f"{bucket_date.year:04d}-{bucket_date.month:02d}"

        qty_ordered = _dec(r.qty_ordered)
        qty_delivered = _dec(r.qty_delivered)
        line_total = _dec(r.line_total)
        confirmed_qty = min(qty_delivered, qty_ordered)
        if qty_ordered != 0:
            confirmed_value = (line_total * confirmed_qty / qty_ordered)
        else:
            confirmed_value = Decimal(0)
        is_open = r.so_status == "open" and r.line_status == "open"
        if is_open:
            outstanding_qty = qty_ordered - confirmed_qty
            outstanding_value = line_total - confirmed_value
        else:
            outstanding_qty = Decimal(0)
            outstanding_value = Decimal(0)
        ordered_qty = confirmed_qty + outstanding_qty
        ordered_value = confirmed_value + outstanding_value

        m = months_acc.setdefault(month_key, _new_figures())
        _accumulate(
            m, ordered_qty=ordered_qty, ordered_value=ordered_value,
            confirmed_qty=confirmed_qty, confirmed_value=confirmed_value,
            outstanding_qty=outstanding_qty, outstanding_value=outstanding_value,
        )
        month_so_ids.setdefault(month_key, set()).add(r.so_id)

        if want_by_product:
            prod_acc = month_product_acc.setdefault(month_key, {}).setdefault(
                r.product_code, _new_figures()
            )
            _accumulate(
                prod_acc, ordered_qty=ordered_qty, ordered_value=ordered_value,
                confirmed_qty=confirmed_qty, confirmed_value=confirmed_value,
                outstanding_qty=outstanding_qty, outstanding_value=outstanding_value,
            )
        if want_by_customer:
            cust_acc = month_customer_acc.setdefault(month_key, {}).setdefault(
                r.customer_name, _new_figures()
            )
            _accumulate(
                cust_acc, ordered_qty=ordered_qty, ordered_value=ordered_value,
                confirmed_qty=confirmed_qty, confirmed_value=confirmed_value,
                outstanding_qty=outstanding_qty, outstanding_value=outstanding_value,
            )

        if want_so_rows:
            so = so_acc.setdefault(
                r.so_id,
                {
                    "so_number": r.so_number, "customer_name": r.customer_name,
                    "order_date": r.order_date, "_locations": set(),
                    **_new_figures(),
                },
            )
            _accumulate(
                so, ordered_qty=ordered_qty, ordered_value=ordered_value,
                confirmed_qty=confirmed_qty, confirmed_value=confirmed_value,
                outstanding_qty=outstanding_qty, outstanding_value=outstanding_value,
            )
            if r.warehouse_code:
                so["_locations"].add(r.warehouse_code)

    months: list[dict] = []
    for month_key in sorted(months_acc.keys(), reverse=True):
        entry = {
            "month": month_key,
            "so_count": len(month_so_ids.get(month_key, ())),
            **_quantised_figures(months_acc[month_key]),
        }
        if want_by_product:
            rows = [
                {"product_code": code, **_quantised_figures(acc)}
                for code, acc in month_product_acc.get(month_key, {}).items()
            ]
            entry["by_product"] = _rank_breakdown(rows, name_key="product_code")
        if want_by_customer:
            rows = [
                {"customer_name": name, **_quantised_figures(acc)}
                for name, acc in month_customer_acc.get(month_key, {}).items()
            ]
            entry["by_customer"] = _rank_breakdown(rows, name_key="customer_name")
        months.append(entry)

    so_rows: Optional[list[dict]] = None
    if want_so_rows:
        rows = [
            {
                "so_number": v["so_number"],
                "customer_name": v["customer_name"],
                "location": ", ".join(sorted(v["_locations"])) if v["_locations"] else None,
                "order_date": v["order_date"],
                **_quantised_figures(v),
            }
            for v in so_acc.values()
        ]
        # AC-1629: order_date descending, ties by so_number descending, undated
        # last - the same two-step stable-sort idiom
        # `outstanding_report_service.py` uses for its own `so_rows`/`do_rows`.
        rows.sort(
            key=lambda r: (r["order_date"] is None, r["order_date"] or date.min, r["so_number"]),
            reverse=True,
        )
        rows.sort(key=lambda r: r["order_date"] is None)
        so_rows = rows

    return {
        "customer_name": _customer_echo(db, customer_query, customer_ids),
        "product_code": product.product_code if product is not None else None,
        "channel": channel,
        "warehouse_codes": [str(c).strip() for c in (warehouse_codes or []) if str(c).strip()],
        "date_from": _as_date(date_from),
        "date_to": _as_date(date_to),
        "months": months,
        "so_rows": so_rows,
    }
