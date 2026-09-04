"""The DOCUMENTS behind three figures on the loading plan row: SPO, Incoming PL, PO.

`PLAN-scm-fulfilment-feedback-p4.md` R8 / AC-B4-B5. The rule this module exists to keep is
one sentence: **`total` IS the figure the cell shows.** Every reader below is the row form of
a predicate `container_request_service._stock_context` already sums, written once here and
read back through `total`, so the number that opened the dialog and the rows inside it cannot
argue. Change a predicate on one side without the other and `test_container_request_drill.py`
fails on the total, not on a column nobody looks at.

Three things this deliberately does NOT do:

  * **It does not filter by supplier.** The cells are product-scoped (`_stock_context` takes
    product ids and nothing else), so a supplier filter here would make the dialog show less
    than the number that opened it. `supplier_id` is the plan's context and the 404 guard -
    a caller asking about a supplier this company does not hold is told the supplier does not
    exist, exactly as `container_request_service.build` does.
  * **It does not read a run.** The reorder-revamp lane's SPO/PO drills are run-scoped
    (frozen figures); this one reads the live book, because the loading plan has no run.
  * **It does not net anything.** Incoming PL and PO are reference figures on this screen
    (Q1 / captain 20 Aug); the dialog states them, the engine ignores them.

Raw SQL for the same reason the rest of this family uses it: `net_position_v` and its
sources are plain views with no ORM mapping, so nothing is scoped automatically, and every
joined side is company-scoped BY HAND here (`company_sql_predicate`) - the exact column
`_stock_context` scopes on for that family, never a different one, or the two totals part
company on a multi-company database.

### SPO: measured, not assumed (28 Aug 2026)

R8a asked for the SPO cell and this dialog to read SPO-kind rows of `purchase_orders` /
`purchase_order_lines`, because SPO uploads will land there. Measured on the dev copy before
writing a line of it, for CHAOZHOU JINBAICHUAN's 71 stock-list products:

  * `net_position_v.on_order` at site pools: **3,051** over 15 (product, location) rows,
    equal to the open `spo_allocations` sum at pools - so the cell reads the allocations.
  * SPO-kind `purchase_order_lines` bound for a site pool: **0**, over 12 rows total.
  * `purchase_orders` rows whose number is an `SPO-` document, whole database: **0**.

The reason is a ruling, not a gap: migration `420_spo_docs_in_allocations` (captain, 25-26
Aug) MOVED all 3,983 SPO documents / 79,968 lines out of `purchase_orders` into
`spo_allocations`, because a shipping order is not a purchase order. Reading the SPO figure
off the PO table today would return zero for every product.

So this reader stays on `spo_allocations` - the same rows `scm.on_order_v` counts, and the
same rows the cell nets - and `_stock_context` is left alone. The trigger for moving it is
named rather than guessed: when the SPO upload lane files SPO documents on `purchase_orders`
with an identity to select on, `_open_spo` swaps its FROM clause and `_stock_context.
incoming_spo` follows it in the same change.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.scm.container_request_service import (
    OPEN_PO_SQL,
    PL_NOT_ARRIVED_SQL,
    PL_REMAINING_SQL,
)
from app.services.scm.pool_predicate import SITE_POOL_SQL
from app.services.scm.supplier_scope import is_uuid, supplier_row

#: What a caller may ask for. `on_hand` is NOT here - it is served by
#: `/reorder-runs/location-stock`, which already answers it per product (R7).
KINDS = ("spo", "incoming_pl", "po")

#: How far back a History tab looks. Twelve months is the window every other SCM history
#: read on this screen uses (`container_request_service.history`), so the two agree about
#: what "recently" means.
_HISTORY_MONTHS = 12

#: The site-pool test, from the one module that spells it (`pool_predicate`). The SPO cell
#: nets POOL supply only, so the dialog behind it counts pool rows only.
_POOL = SITE_POOL_SQL

#: Shipment states that mean the goods have landed - verbatim from migration 337, whose
#: `scm.on_order_v` body the SPO reader below mirrors.
_RECEIVED_SHIPMENT_STATES = (
    "('fully_received', 'closed', 'received', 'completed', 'cancelled')"
)


def _f(value: Any) -> float:
    return float(value or 0)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _assert_supplier(db: Session, supplier_id: str) -> None:
    """A supplier this company does not hold does not exist here (`supplier_scope`'s rule)."""
    if supplier_row(db, supplier_id) is None:
        raise AppException(404, "Supplier not found")


def _assert_product(db: Session, product_id: str) -> None:
    if not product_id or not is_uuid(product_id):
        raise AppException(404, "Product not found")
    scope, params = company_sql_predicate(db, "p.company_id", param_prefix="dp")
    row = db.execute(
        text(
            "SELECT 1 FROM products p WHERE p.id = :i "
            f"AND {scope or 'true'}"
        ),
        {"i": str(product_id), **params},
    ).first()
    if row is None:
        raise AppException(404, "Product not found")


# ---------------------------------------------------------------------------
# PO - `_stock_context.outstanding_po` / `_outstanding_po_lines`, line by line
# ---------------------------------------------------------------------------

#: The open-PO predicate, IMPORTED from the service whose cell this lightbox opens rather
#: than restated here: the cell and its own list of documents have to count the same rows.
_PO_OPEN = OPEN_PO_SQL


def _po_row(r) -> dict:
    return {
        "purchase_order_id": r["purchase_order_id"],
        "po_number": r["po_number"],
        "supplier_name": r["supplier_name"],
        "qty_ordered": _f(r["qty_ordered"]),
        "still_to_come": _f(r["still_to_come"]),
        "unit_price": None if r["unit_cost"] is None else _f(r["unit_cost"]),
        "currency": r["currency"],
        "issued": _iso(r["issue_date"]),
        "eta": _iso(r["expected_date"]),
        "status": r["status"],
    }


def _po_lines(db: Session, product_id: str, *, open_lines: bool) -> list[dict]:
    """Open PO lines (the cell), or the ones that are done (the History tab).

    One row per LINE rather than per document: the sum over lines is the sum over the
    `(product, po_number, expected_date)` groups `_outstanding_po_lines` totals, so the
    figure is unchanged, and a line carries the unit price and the date a group cannot.
    """
    scope, params = company_sql_predicate(db, "po.company_id", param_prefix="dpo")
    if open_lines:
        where = _PO_OPEN
        order = "ORDER BY pol.expected_date NULLS LAST, po.po_number"
    else:
        where = (
            "po.status <> 'draft' AND po.status <> 'draft_recommendation' "
            "AND (pol.line_status <> 'open' OR pol.qty_ordered <= pol.qty_received) "
            f"AND po.issue_date >= (CURRENT_DATE - INTERVAL '{_HISTORY_MONTHS} months')"
        )
        order = "ORDER BY po.issue_date DESC NULLS LAST, po.po_number"
    sql = f"""
        SELECT po.id::text AS purchase_order_id,
               po.po_number,
               s.supplier_name,
               po.issue_date,
               po.status,
               pol.qty_ordered,
               GREATEST(pol.qty_ordered - pol.qty_received, 0) AS still_to_come,
               pol.unit_cost,
               COALESCE(pol.currency, po.currency) AS currency,
               pol.expected_date
        FROM purchase_order_lines pol
        JOIN purchase_orders po ON po.id = pol.purchase_order_id
        LEFT JOIN suppliers s ON s.id = po.supplier_id
        WHERE pol.product_id = CAST(:pid AS uuid)
          AND {where}
          {("AND " + scope) if scope else ""}
        {order}
    """
    rows = db.execute(text(sql), {"pid": str(product_id), **params}).mappings().all()
    return [_po_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Incoming PL - `_stock_context.incoming_pl` / `_incoming_packing_lists`, per shipment
# ---------------------------------------------------------------------------


def _incoming_pl_rows(db: Session, product_id: str) -> list[dict]:
    """Unreceived packing-list quantity, by shipment. Predicate IMPORTED from
    `container_request_service._incoming_packing_lists`, whose cell this opens: "not arrived"
    is BOTH a null `actual_arrival_date` AND a status that is not a finished one, or stock
    that has landed would be counted here as well as in On hand.
    """
    scope, params = company_sql_predicate(db, "s.company_id", param_prefix="dipl")
    remaining = PL_REMAINING_SQL
    sql = f"""
        SELECT s.id::text AS shipment_id,
               s.shipment_number,
               s.shipping_container_number,
               sup.supplier_name,
               s.estimated_arrival_date,
               s.shipment_status,
               SUM({remaining}) AS qty
        FROM inbound_shipment_lines l
        JOIN inbound_shipments s ON s.id = l.shipment_id
        LEFT JOIN suppliers sup ON sup.id = s.supplier_id
        WHERE l.product_id = CAST(:pid AS uuid)
          AND {PL_NOT_ARRIVED_SQL}
          AND {remaining} > 0
          {("AND " + scope) if scope else ""}
        GROUP BY s.id, s.shipment_number, s.shipping_container_number, sup.supplier_name,
                 s.estimated_arrival_date, s.shipment_status
        ORDER BY s.estimated_arrival_date NULLS LAST, s.shipment_number NULLS FIRST
    """
    rows = db.execute(text(sql), {"pid": str(product_id), **params}).mappings().all()
    return [
        {
            "shipment_id": r["shipment_id"],
            # Null on a draft nobody has numbered - emitted as null so the screen can say
            # "draft" rather than invent a number.
            "shipment_number": r["shipment_number"],
            "container_number": r["shipping_container_number"],
            "supplier_name": r["supplier_name"],
            "qty": _f(r["qty"]),
            "eta": _iso(r["estimated_arrival_date"]),
            "status": r["shipment_status"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# SPO - `_stock_context.incoming_spo`, which is `scm.on_order_v` at site pools
# ---------------------------------------------------------------------------


def _spo_rows(db: Session, product_id: str, *, open_rows: bool) -> list[dict]:
    """What is on the water for the site pools (Open), or what has landed (History).

    The Open predicate is `scm.on_order_v`'s own, clause for clause, narrowed to ACTIVE site
    pools the way `_stock_context` narrows it: an allocation with no warehouse is incoming
    supply NOWHERE (migration 420), an allocation on a landed shipment is already in On hand,
    and a project bin's allocation is spoken for. Company scope is on the PRODUCT and the
    WAREHOUSE - the two columns `_stock_context` scopes on - so the two reads cannot disagree
    about which rows belong to this caller.

    The shipment join is a LEFT JOIN, and the view's `s.id IS NULL OR ...` rides with it: an
    SPO allocation that names a warehouse but no shipment yet is on order (the view counts it,
    so the cell counts it), and an inner join silently dropped it from the dialog - the total
    then read lower than the number the buyer clicked. The receipt clauses are the view's
    COALESCE forms for the same reason: `sa.receipt_status <> 'received'` is NULL, not true,
    on the rows where nobody has stamped one yet, which excluded them too.
    """
    prod_scope, prod_params = company_sql_predicate(db, "p.company_id", param_prefix="dsp")
    wh_scope, wh_params = company_sql_predicate(db, "w.company_id", param_prefix="dsw")
    if open_rows:
        where = (
            f"(s.id IS NULL OR s.shipment_status NOT IN {_RECEIVED_SHIPMENT_STATES}) "
            # Verbatim from the view, including the fact that `received` is not one of the
            # four values `spo_allocations_receipt_status_check` allows - so that value
            # excludes nothing today and the shipment status is what does the work. Kept
            # spelling for spelling anyway: this reader has to foot to the cell, and a
            # "tidied" predicate is how the two come to differ by a row nobody expected.
            "AND COALESCE(sa.line_status, 'open') = 'open' "
            "AND COALESCE(sa.receipt_status, 'pending') "
            "NOT IN ('fully_received', 'received') "
            "AND sa.allocated_quantity > COALESCE(sa.quantity_received, 0)"
        )
        order = "ORDER BY s.estimated_arrival_date NULLS LAST, sa.spo_number"
    else:
        where = (
            f"(s.shipment_status IN {_RECEIVED_SHIPMENT_STATES} "
            "OR sa.receipt_status = 'fully_received' "
            "OR sa.allocated_quantity <= COALESCE(sa.quantity_received, 0)) "
            "AND COALESCE(s.actual_arrival_date, s.estimated_arrival_date, s.shipment_date) "
            f">= (CURRENT_DATE - INTERVAL '{_HISTORY_MONTHS} months')"
        )
        order = "ORDER BY COALESCE(s.actual_arrival_date, s.shipment_date) DESC, sa.spo_number"
    # Open counts what is STILL to come (that is the cell); History counts what the shipping
    # order carried, since a landed allocation has nothing outstanding and a column of zeros
    # would say the shipment brought nothing.
    qty_expr = (
        "GREATEST(sa.allocated_quantity - COALESCE(sa.quantity_received, 0), 0)"
        if open_rows
        else "sa.allocated_quantity"
    )
    sql = f"""
        SELECT sa.spo_number,
               s.id::text AS shipment_id,
               s.shipment_number,
               s.shipping_container_number,
               w.warehouse_code,
               s.estimated_arrival_date,
               s.actual_arrival_date,
               s.shipment_status,
               SUM({qty_expr}::numeric) AS qty,
               SUM(COALESCE(sa.quantity_received, 0)::numeric) AS received
        FROM spo_allocations sa
        LEFT JOIN inbound_shipments s ON s.id = sa.inbound_shipment_id
        JOIN products p ON p.id = sa.product_id
        JOIN warehouses w ON w.id = sa.warehouse_id
        WHERE sa.product_id = CAST(:pid AS uuid)
          AND w.is_active
          AND {_POOL}
          AND {where}
          {("AND " + prod_scope) if prod_scope else ""}
          {("AND " + wh_scope) if wh_scope else ""}
        GROUP BY sa.spo_number, s.id, s.shipment_number, s.shipping_container_number,
                 w.warehouse_code, s.estimated_arrival_date, s.actual_arrival_date,
                 s.shipment_status
        {order}
    """
    rows = (
        db.execute(text(sql), {"pid": str(product_id), **prod_params, **wh_params})
        .mappings()
        .all()
    )
    return [
        {
            "spo_number": r["spo_number"],
            "shipment_id": r["shipment_id"],
            "shipment_number": r["shipment_number"],
            "container_number": r["shipping_container_number"],
            "warehouse_code": r["warehouse_code"],
            "qty": _f(r["qty"]),
            "received": _f(r["received"]),
            "eta": _iso(r["estimated_arrival_date"]),
            "arrived_at": _iso(r["actual_arrival_date"]),
            "status": r["shipment_status"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------


def drill(db: Session, *, supplier_id: str, product_id: str, kind: str) -> dict:
    """`{kind, rows, total, history}` - the documents behind one cell of one row.

    `total` is summed over `rows` rather than read separately: a second read is a second
    predicate, and two predicates are how a dialog comes to disagree with the figure that
    opened it.
    """
    _assert_supplier(db, supplier_id)
    _assert_product(db, product_id)

    if kind == "po":
        rows = _po_lines(db, product_id, open_lines=True)
        history = _po_lines(db, product_id, open_lines=False)
        total = sum(r["still_to_come"] for r in rows)
    elif kind == "incoming_pl":
        rows = _incoming_pl_rows(db, product_id)
        # A packing list is a reference figure with no landed counterpart to show: once a
        # shipment arrives its quantity IS the On hand dialog, which has its own drill.
        history = []
        total = sum(r["qty"] for r in rows)
    elif kind == "spo":
        rows = _spo_rows(db, product_id, open_rows=True)
        history = _spo_rows(db, product_id, open_rows=False)
        total = sum(r["qty"] for r in rows)
    else:  # pragma: no cover - the route's Literal refuses this first (422)
        raise AppException(422, f"Unknown drill kind: {kind}")

    return {"kind": kind, "rows": rows, "total": total, "history": history}
