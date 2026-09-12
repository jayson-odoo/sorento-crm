"""Last purchase cost per product per location (PLAN-chatbot-last-purchase-cost.md).

Mirrors `spo_last_receipt_service.py`'s own shape: a windowed `row_number()` branch when
the caller names products (one row per `(product, warehouse)`, `top_n` PER group, never
an overall cap), a plain `top_n` cap when they do not.

Owner ruling, 12 Sep 2026: per product code, per location, the last purchase-order line's
`PO number, Product code, PO quantity, PO date, Cost / unit, Discount / unit, Cost after
discount / unit, Warehouse`. Second ruling the same day: the three money figures are PER
UNIT, cancelled lines are excluded, family resolution answers every member, and `top_n`
was never an overall cap when products are named.

`discount` on `purchase_order_lines` is a LINE amount, not a unit figure - measured on the
local prod copy `sorento_ai_automation`, 12 Sep 2026: on 59,585 of 59,859 fully-populated
lines `line_total = qty_ordered * unit_cost - discount` holds to the cent (sample: M218,
qty 19, cost 110.00, discount 1,254.00, total 836.00), and 59,409 of those carry a zero
discount. So the per-unit figures the owner asked for are DERIVED: `discount_per_unit =
discount / qty_ordered` (None unless `discount > 0`), `unit_cost_after_discount =
line_total / qty_ordered` when `line_total` is present, else `unit_cost` (2,245 history
lines carry a cost and no discount and no total, so the after-discount figure there IS the
unit cost).

Location = `warehouse_id`, NULL is its own bucket: Postgres already groups NULLs together
in `PARTITION BY (product_id, warehouse_id)`, so a product bought with no warehouse stated
answers one row with no warehouse, never coalesced onto a real one.

Cancelled excluded: `purchase_order_lines.line_status <> 'cancelled'` AND
`purchase_orders.status <> 'cancelled'`. A line with `unit_cost IS NULL` never answers - a
cost answer with no cost is not an answer.

Ordering key: `purchase_orders.issue_date DESC`, then `purchase_order_lines.created_at
DESC`, then `id` for determinism - `issue_date` is 100% populated (6,349 of 6,349 header
rows on the same measured copy), so unlike `spo_last_receipt_service` there is no fallback
chain and no `_source` field to say which column answered.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.base import get_company_scope
from app.models.inventory import Warehouse
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.product import Product
from app.services.company_scope import build_company_predicate


_CENTS = Decimal("0.01")


def _money(v: Any) -> Optional[float]:
    """Round to 2 dp, half up, before the float conversion (review S1) - a derived
    per-unit figure (`discount / qty_ordered`, `line_total / qty_ordered`) is a Decimal
    division and carries far more than two digits until this rounds it: qty 3,
    discount 100 must answer 33.33, never 33.333333333333333333333333333."""
    if v is None:
        return None
    return float(Decimal(str(v)).quantize(_CENTS, rounding=ROUND_HALF_UP))


def _plain_number(v: Any) -> Any:
    if v is None:
        return None
    d = Decimal(str(v))
    return int(d) if d == d.to_integral_value() else float(d)


_LIVE_LINE_CLAUSES = (
    PurchaseOrderLine.line_status != "cancelled",
    PurchaseOrderLine.unit_cost.isnot(None),
)
_LIVE_PO_CLAUSE = PurchaseOrder.status != "cancelled"


def _row_dict(row: Any) -> dict:
    qty = row.qty_ordered
    unit_cost = _money(row.unit_cost)
    discount_per_unit = (
        _money(Decimal(str(row.discount)) / Decimal(str(qty)))
        if row.discount is not None and Decimal(str(row.discount)) > 0 and qty
        else None
    )
    unit_cost_after_discount = (
        _money(Decimal(str(row.line_total)) / Decimal(str(qty)))
        if row.line_total is not None and qty
        else unit_cost
    )
    return {
        "po_number": row.po_number,
        "product_id": str(row.product_id),
        "product_code": row.product_code,
        "product_name": row.product_name,
        "po_quantity": _plain_number(qty),
        "po_date": row.issue_date.isoformat() if row.issue_date else None,
        "currency": row.currency,
        "unit_cost": unit_cost,
        "discount_per_unit": discount_per_unit,
        "unit_cost_after_discount": unit_cost_after_discount,
        "warehouse": row.warehouse_code,
    }


def last_cost_rows(
    db: Session,
    *,
    product_ids: Optional[list[str]] = None,
    warehouse_ids: Optional[list[str]] = None,
    top_n: int = 1,
) -> list[dict]:
    """The last `top_n` PO lines PER `(product, warehouse)` when `product_ids` is given
    (`top_n` caps EACH group, never the whole answer - a three-member family with
    `top_n=1` returns three rows, one per member). With NO `product_ids`, `top_n` is
    instead a plain cap over every line, newest first, any product - the same rule
    `spo_last_receipt_service.last_receipt_rows` uses for an unscoped ask.

    `warehouse_ids` narrows BEFORE the pick, so a line at an excluded warehouse can never
    displace one at an included warehouse.

    Row keys: `po_number`, `product_id`, `product_code`, `product_name`, `po_quantity`
    (plain number), `po_date` (ISO, or None), `currency` (the LINE's own), `unit_cost`,
    `discount_per_unit` (None unless the line's discount is a positive amount),
    `unit_cost_after_discount`, `warehouse` (the warehouse code, or None).
    """
    top_n = max(int(top_n or 1), 1)

    if product_ids:
        rn = (
            func.row_number()
            .over(
                partition_by=(PurchaseOrderLine.product_id, PurchaseOrderLine.warehouse_id),
                order_by=(
                    PurchaseOrder.issue_date.desc().nulls_last(),
                    PurchaseOrderLine.created_at.desc(),
                    PurchaseOrderLine.id,
                ),
            )
            .label("rn")
        )

        numbered = (
            db.query(
                PurchaseOrderLine.id.label("line_id"),
                PurchaseOrder.po_number,
                PurchaseOrderLine.product_id,
                PurchaseOrderLine.warehouse_id,
                PurchaseOrderLine.qty_ordered,
                PurchaseOrder.issue_date,
                PurchaseOrderLine.currency,
                PurchaseOrderLine.unit_cost,
                PurchaseOrderLine.discount,
                PurchaseOrderLine.line_total,
                rn,
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(
                PurchaseOrderLine.product_id.in_(product_ids),
                *_LIVE_LINE_CLAUSES,
                _LIVE_PO_CLAUSE,
            )
        )
        if warehouse_ids:
            numbered = numbered.filter(PurchaseOrderLine.warehouse_id.in_(warehouse_ids))
        # COMPANY SCOPE, EXPLICITLY, on BOTH tables named in this branch: `.subquery()`
        # loses the `with_loader_criteria` the session's `do_orm_execute` listener
        # injects, and the outer query below names only `Product` / `Warehouse`. Same
        # hand-ANDed predicate, same reason, as `spo_last_receipt_service`'s own
        # windowed branch.
        for model in (PurchaseOrderLine, PurchaseOrder):
            predicate = build_company_predicate(model, get_company_scope(db))
            if predicate is not None:
                numbered = numbered.filter(predicate)
        sub = numbered.subquery()

        rows = (
            db.query(
                sub.c.po_number,
                sub.c.qty_ordered,
                sub.c.issue_date,
                sub.c.currency,
                sub.c.unit_cost,
                sub.c.discount,
                sub.c.line_total,
                Product.id.label("product_id"),
                Product.product_code,
                Product.product_name,
                Warehouse.warehouse_code,
            )
            .join(Product, Product.id == sub.c.product_id)
            .outerjoin(Warehouse, Warehouse.id == sub.c.warehouse_id)
            .filter(sub.c.rn <= top_n)
            .order_by(Product.product_code.asc(), sub.c.rn.asc())
            .all()
        )
    else:
        # Unscoped: NOT windowed per (product, warehouse) - a plain top_n over every
        # live line, newest first, any product. The tool is reachable directly by the
        # AI assistant, not gated behind a resolved product.
        q = (
            db.query(
                PurchaseOrder.po_number,
                PurchaseOrderLine.qty_ordered,
                PurchaseOrder.issue_date,
                PurchaseOrderLine.currency,
                PurchaseOrderLine.unit_cost,
                PurchaseOrderLine.discount,
                PurchaseOrderLine.line_total,
                Product.id.label("product_id"),
                Product.product_code,
                Product.product_name,
                Warehouse.warehouse_code,
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .join(Product, Product.id == PurchaseOrderLine.product_id)
            .outerjoin(Warehouse, Warehouse.id == PurchaseOrderLine.warehouse_id)
            .filter(*_LIVE_LINE_CLAUSES, _LIVE_PO_CLAUSE)
        )
        if warehouse_ids:
            q = q.filter(PurchaseOrderLine.warehouse_id.in_(warehouse_ids))
        rows = (
            q.order_by(
                PurchaseOrder.issue_date.desc().nulls_last(),
                PurchaseOrderLine.created_at.desc(),
                PurchaseOrderLine.id,
            )
            .limit(top_n)
            .all()
        )

    return [_row_dict(row) for row in rows]
