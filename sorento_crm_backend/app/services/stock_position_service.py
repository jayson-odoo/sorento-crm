"""Stock position: the supplier stock sheet for every supplier, one row per item (lane
STOCK-POSITION-REPORT).

Plan: documentation/plans/inventory/PLAN-stock-position-report-27oct.md (column map, Q1-Q5).

Every quantity is the Stock Status panel's (`stock_status_service`), read for every item at
once rather than one, so the panel and this report cannot disagree:

* **Warehouse columns**: on hand per ACTIVE SITE-POOL warehouse (`pool_predicate.is_site_pool`)
  holding stock for any item. A project bin's stock is committed to its project and is no column.
* **Incoming BRW / Incoming (Project)**: the panel's open SPO rows (`_spo_rows`), split by
  whether the SPO row's warehouse is a site pool or a project location.
* **Total stock** = the warehouse columns + Incoming BRW. **Total incoming** = the two SPO columns.
* **Packing list not on an SPO**: the panel's `counted` figure (rule R3), kept out of both totals.
* **Outstanding dealer**: the panel's SO rule (`so_outstanding_clauses`) on non-project orders,
  printed negative as the sheet does (owed, Q2). **Outstanding PO**: `po_outstanding_clauses`.
* **Supplier**: the last PO's supplier (`scm/last_po_supplier.py`, Q4).
* **Monthly sales / Highest per month**: the loading plan's 12-full-month series (`_series`)
  over the chosen basis (`SALES_BASES`, Q3).

All figures are built in Python over a handful of grouped reads, then filtered, sorted and paged
here, so every column sorts on the server. Trigger for pushing that into SQL: a page load over
~2 s on the live item count.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from io import BytesIO
from typing import Any, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.finance import CREDIT_NOTE, DOCUMENT_TYPES, POSTED, BillingDocument, BillingDocumentLine
from app.models.inventory import Stock, Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Brand, Product
from app.services.error_handler import AppException
from app.services.scm.container_request_service import _series, history_window, ordered_qty_by_month
from app.services.scm import last_po_supplier
from app.services.scm.pool_predicate import PROJECT_SEGMENT, is_site_pool
from app.services.scm.supplier_scope import is_uuid
from app.services.stock_status_service import (
    _spo_rows,
    incoming_pl_by_product,
    po_outstanding_clauses,
    so_outstanding_clauses,
)

#: The monthly sales bases (Q3): SO quantity ordered by order date (the loading plan's own
#: history), or invoiced = invoice + cash sale + debit note - credit note lines by document date.
SALES_BASES = ("so_ordered", "invoiced")

#: The figure columns after the warehouse ones, in the sheet's order: (key, header).
FIGURE_COLUMNS = (
    ("incoming_pool", "Incoming BRW"),
    ("total_stock", "Total stock"),
    ("incoming_project", "Incoming (Project)"),
    ("total_incoming", "Total incoming"),
    ("packing_list_open", "Packing list, no SPO"),
    ("outstanding_dealer", "Outstanding dealer"),
    ("outstanding_po", "Outstanding PO"),
    ("monthly_sales", "Monthly sales"),
    ("highest_month", "Highest / month"),
)
_TEXT_SORTS = ("item_code", "description", "supplier_name", "brand_name")
#: A warehouse column's sort key: this prefix + its code (`wh:BRW`).
WAREHOUSE_SORT_PREFIX = "wh:"


def _num(value: Any) -> float:
    return float(value or 0)


def _monthly_sales(db: Session, basis: str, as_of: Optional[date]) -> dict[str, dict]:
    """Per product, the chosen basis's 12-full-month series (`avg`, `peak_qty`)."""
    since, until, buckets = history_window(as_of)
    by_product: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    if basis == "so_ordered":
        # Every channel: the sheet's monthly sales is the item's, not one channel's.
        for r in ordered_qty_by_month(db, None, since, until):
            by_product[r["product_id"]][r["month"]] += _num(r["qty"])
    else:
        month = func.to_char(func.date_trunc("month", BillingDocument.doc_date), "YYYY-MM")
        rows = (
            db.query(
                BillingDocumentLine.product_id,
                month.label("month"),
                BillingDocument.document_type,
                func.sum(func.coalesce(BillingDocumentLine.quantity, 0)).label("qty"),
            )
            .join(BillingDocument, BillingDocument.id == BillingDocumentLine.document_id)
            .filter(
                BillingDocumentLine.product_id.isnot(None),
                BillingDocument.status == POSTED,
                BillingDocument.document_type.in_(DOCUMENT_TYPES),
                BillingDocument.doc_date >= since,
                BillingDocument.doc_date < until,
            )
            .group_by(BillingDocumentLine.product_id, month, BillingDocument.document_type)
            .all()
        )
        for r in rows:
            # A credit note is stored positive as AutoCount prints it and subtracts here.
            sign = -1.0 if r.document_type == CREDIT_NOTE else 1.0
            by_product[str(r.product_id)][r.month] += sign * _num(r.qty)
    return {pid: _series(buckets, months) for pid, months in by_product.items()}


def _grouped(query) -> dict[tuple[str, str], float]:
    """(product id, warehouse id) -> quantity, off a query selecting exactly those three."""
    out: dict[tuple[str, str], float] = defaultdict(float)
    for pid, wid, qty in query.all():
        out[(str(pid), str(wid))] += _num(qty)
    return out


def build_rows(db: Session, *, sales_basis: str = "so_ordered", as_of: Optional[date] = None) -> dict:
    """Every item with something to show, every figure computed, unfiltered and unsorted."""
    if sales_basis not in SALES_BASES:
        raise AppException(422, f"Unknown sales basis '{sales_basis}'")

    # Every warehouse of the caller's company (the ORM scope), inactive included: a document
    # bound to one the caller cannot see is in no figure, as on the panel.
    warehouses = {
        str(w.id): w
        for w in db.query(Warehouse.id, Warehouse.warehouse_code, Warehouse.is_active, Warehouse.segment).all()
    }
    columns_wh = {wid for wid, w in warehouses.items() if w.is_active and is_site_pool(w.segment)}

    on_hand = _grouped(db.query(Stock.product_id, Stock.warehouse_id, Stock.quantity_on_hand))
    dealer = _grouped(
        db.query(
            SalesOrderLine.product_id,
            SalesOrderLine.warehouse_id,
            SalesOrderLine.qty_ordered - SalesOrderLine.qty_delivered,
        )
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .filter(
            *so_outstanding_clauses(),
            or_(SalesOrder.demand_class.is_(None), SalesOrder.demand_class != PROJECT_SEGMENT),
        )
    )
    po = _grouped(
        db.query(
            PurchaseOrderLine.product_id,
            PurchaseOrderLine.warehouse_id,
            PurchaseOrderLine.qty_ordered - PurchaseOrderLine.qty_received,
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(*po_outstanding_clauses())
    )
    spos = [r for r in _spo_rows(db, None, False) if r["warehouse_id"] in warehouses]
    packing = {
        pid: sum(s["counted"] for s in shipments)
        for pid, shipments in incoming_pl_by_product(db, None, spos, False).items()
    }
    sales = _monthly_sales(db, sales_basis, as_of)

    figures: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "stock": {}, "incoming_pool": 0.0, "incoming_project": 0.0, "outstanding_dealer": 0.0,
        "outstanding_po": 0.0, "packing_list_open": 0.0,
    })
    used_columns: set[str] = set()
    for (pid, wid), qty in on_hand.items():
        if wid in columns_wh and qty:
            code = warehouses[wid].warehouse_code
            stock = figures[pid]["stock"]
            stock[code] = stock.get(code, 0.0) + qty
            used_columns.add(wid)
    for row in spos:
        segment = warehouses[row["warehouse_id"]].segment
        key = "incoming_pool" if is_site_pool(segment) else "incoming_project"
        figures[row["product_id"]][key] += row["qty"]
    for source, key, sign in ((dealer, "outstanding_dealer", -1.0), (po, "outstanding_po", 1.0)):
        for (pid, wid), qty in source.items():
            if wid in warehouses:
                figures[pid][key] += sign * qty
    for pid, qty in packing.items():
        if qty:
            figures[pid]["packing_list_open"] += qty
    for pid, series in sales.items():
        if series["total"]:
            figures[pid]  # an item that only sold still has a row

    products = {
        str(p.id): p
        for p in db.query(Product.id, Product.product_code, Product.product_name, Product.brand_id)
        .filter(Product.id.in_(list(figures)))
        .all()
    } if figures else {}
    brands = dict(db.query(Brand.id, Brand.brand_name).all()) if products else {}
    # Q4 (owner ruling 27 Oct): the LAST PO's supplier, the one rule the low stock report reads.
    supplier_of = last_po_supplier.last_po_supplier_ids(db, None) if products else {}
    suppliers = {
        str(s.id): s for s in db.query(Supplier.id, Supplier.supplier_code, Supplier.supplier_name).all()
    } if supplier_of else {}

    rows = []
    for pid, f in figures.items():
        product = products.get(pid)
        if product is None:  # an item outside the caller's scope (brand scope) is no row
            continue
        series = sales.get(pid) or {"avg": 0.0, "peak_qty": 0.0}
        total_stock = sum(f["stock"].values()) + f["incoming_pool"]
        row = {
            "product_id": pid,
            "item_code": product.product_code,
            "description": product.product_name,
            "supplier_id": supplier_of.get(pid),
            "supplier_code": None,
            "supplier_name": None,
            "brand_id": str(product.brand_id) if product.brand_id else None,
            "brand_name": brands.get(product.brand_id),
            "stock": f["stock"],
            "incoming_pool": f["incoming_pool"],
            "total_stock": total_stock,
            "incoming_project": f["incoming_project"],
            "total_incoming": f["incoming_pool"] + f["incoming_project"],
            "packing_list_open": f["packing_list_open"],
            "outstanding_dealer": f["outstanding_dealer"],
            "outstanding_po": f["outstanding_po"],
            "monthly_sales": series["avg"],
            "highest_month": series["peak_qty"],
        }
        supplier = suppliers.get(row["supplier_id"]) if row["supplier_id"] else None
        if supplier is not None:
            row["supplier_code"], row["supplier_name"] = supplier.supplier_code, supplier.supplier_name
        else:
            row["supplier_id"] = None
        if any(row[k] for k, _ in FIGURE_COLUMNS) or row["stock"]:
            rows.append(row)

    columns = sorted(
        ({"id": wid, "code": warehouses[wid].warehouse_code} for wid in used_columns),
        key=lambda c: c["code"] or "",
    )
    return {"warehouses": columns, "rows": rows, "sales_basis": sales_basis}


def _sort_key(sort: str, codes: set[str]):
    if sort in _TEXT_SORTS:
        # Blank last on either direction is not asked for; a blank reads as "" and sorts first asc.
        return lambda r: ((r[sort] or "").lower(), r["item_code"] or "")
    if sort.startswith(WAREHOUSE_SORT_PREFIX) and sort[len(WAREHOUSE_SORT_PREFIX):] in codes:
        code = sort[len(WAREHOUSE_SORT_PREFIX):]
        return lambda r: (r["stock"].get(code, 0.0), r["item_code"] or "")
    if sort in {k for k, _ in FIGURE_COLUMNS}:
        return lambda r: (r[sort], r["item_code"] or "")
    raise AppException(422, f"Unknown sort column '{sort}'")


def stock_position(
    db: Session,
    *,
    query: Optional[str] = None,
    supplier_ids: Optional[list[str]] = None,
    brand_ids: Optional[list[str]] = None,
    warehouse_ids: Optional[list[str]] = None,
    sort: Optional[str] = None,
    direction: str = "asc",
    sales_basis: str = "so_ordered",
    as_of: Optional[date] = None,
) -> dict:
    """The filtered, sorted row set (unpaged) and its warehouse columns."""
    built = build_rows(db, sales_basis=sales_basis, as_of=as_of)
    # A warehouse sort names one of THIS result's columns; any other is as unknown as `sort=nope`.
    key = _sort_key(sort or "item_code", {c["code"] for c in built["warehouses"]})
    rows = built["rows"]
    if query:
        needle = query.strip().lower()
        rows = [r for r in rows if needle in (r["item_code"] or "").lower()
                or needle in (r["description"] or "").lower()]
    if supplier_ids:
        wanted = set(supplier_ids)
        rows = [r for r in rows if r["supplier_id"] in wanted]
    if brand_ids:
        wanted = set(brand_ids)
        rows = [r for r in rows if r["brand_id"] in wanted]
    if warehouse_ids:
        # A value that is not an id matches nothing (the query string is the caller's typo,
        # not a server error), the same rule `ordered_qty_by_month` follows.
        ids = [w for w in warehouse_ids if is_uuid(w)]
        codes = {
            code for (code,) in db.query(Warehouse.warehouse_code).filter(Warehouse.id.in_(ids)).all()
        } if ids else set()
        rows = [r for r in rows if any(r["stock"].get(code) for code in codes)]
    rows.sort(key=key, reverse=(direction == "desc"))
    return {**built, "rows": rows}


def page(result: dict, page_no: int, limit: int) -> dict:
    """The DataGrid response shape over a `stock_position` result."""
    rows = result["rows"]
    total = len(rows)
    start = (page_no - 1) * limit
    return {
        "data": rows[start:start + limit],
        "warehouses": result["warehouses"],
        "sales_basis": result["sales_basis"],
        "pagination": {
            "page": page_no,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit if limit else 0,
        },
    }


def workbook(result: dict, warehouse_codes: Optional[list[str]] = None) -> bytes:
    """Every row of a `stock_position` result as one sheet, headed as the screen is.

    `warehouse_codes`: the warehouse columns the user shows (Q5, the grid's Columns chooser),
    written in the report's own order; None writes them all. The totals are not recomputed:
    hiding a column hides it, it does not take that warehouse out of Total stock."""
    from openpyxl import Workbook

    codes = [c["code"] for c in result["warehouses"]]
    if warehouse_codes is not None:
        shown = set(warehouse_codes)
        codes = [code for code in codes if code in shown]
    wb = Workbook()
    ws = wb.active
    ws.title = "Stock position"
    ws.append(["Item code", "Supplier", "Brand", *codes, *[label for _, label in FIGURE_COLUMNS]])
    for r in result["rows"]:
        ws.append([
            r["item_code"],
            r["supplier_name"],
            r["brand_name"],
            *[r["stock"].get(code, 0) for code in codes],
            *[round(r[key], 2) for key, _ in FIGURE_COLUMNS],
        ])
    ws.freeze_panes = "B2"
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
