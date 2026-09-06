"""SCM - Order Inquiry / ESB warehouse conflict read route (D22, migration 476).

`OrderInquiryConflict` has had a writer since D22 landed (the Order Inquiry import only
fills a blank `warehouse_id`; the ESB SO line writer overwrites a non-NULL one and records
the disagreement here) but no reader - a row nobody could ever see. This is that reader.
No FE this lane (guide-writer code check, 2026-09-06); the worklist surface is backlogged.

`scm.reorder.run`, matching the permission the outstanding-import writer (the OTHER half of
this same conflict) already runs under, rather than the read-only `scm.dashboard.view` a
report route would use - this is operational data about an import, not a planning report.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.models.inventory import Warehouse
from app.models.order import OrderInquiryConflict, SalesOrder

router = APIRouter()

_RUN = require_permission_with_api_key("scm.reorder.run")


@router.get("/order-inquiry/conflicts")
def list_order_inquiry_conflicts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    """Every recorded warehouse disagreement, newest first.

    Joined to the SO number and both warehouse CODES - no id surfaces (`sales_order_id`,
    `previous_warehouse_id`, `new_warehouse_id` stay off the response). A `NULL` warehouse
    side (the inquiry named none at all before the ESB stated one) reads as `None`, not a
    missing join - both FKs are `ondelete="SET NULL"` and nullable on the model already.

    Warehouse codes are resolved with a SECOND query (id -> code) rather than joining
    `Warehouse` twice by alias in the same statement: the company-scope listener's
    `with_loader_criteria(cls, ..., include_aliases=True)` only reliably adapts to ONE
    aliased occurrence of a class per statement (a SQLAlchemy limitation, not a bug in the
    scope filter itself), and two aliases of `Warehouse` in one query left the second
    join's generated SQL referencing the bare, unaliased `warehouses` table -
    `UndefinedTable` at execute time. A single un-aliased lookup has nothing to adapt.
    """
    base = db.query(OrderInquiryConflict).join(
        SalesOrder, SalesOrder.id == OrderInquiryConflict.sales_order_id
    )
    total = base.with_entities(func.count(OrderInquiryConflict.id)).scalar() or 0
    rows = (
        base.with_entities(
            OrderInquiryConflict.id,
            OrderInquiryConflict.sales_order_line_id,
            SalesOrder.so_number,
            OrderInquiryConflict.previous_warehouse_id,
            OrderInquiryConflict.new_warehouse_id,
            OrderInquiryConflict.source,
            OrderInquiryConflict.created_at,
        )
        .order_by(OrderInquiryConflict.created_at.desc(), OrderInquiryConflict.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    warehouse_ids = {
        wid
        for row in rows
        for wid in (row.previous_warehouse_id, row.new_warehouse_id)
        if wid
    }
    codes_by_id: dict[str, str] = {}
    if warehouse_ids:
        codes_by_id = {
            str(wid): code
            for wid, code in db.query(Warehouse.id, Warehouse.warehouse_code)
            .filter(Warehouse.id.in_(warehouse_ids))
            .all()
        }
    items: list[dict[str, Any]] = [
        {
            "id": str(row.id),
            "sales_order_line_id": str(row.sales_order_line_id),
            "so_number": row.so_number,
            "previous_warehouse_code": codes_by_id.get(str(row.previous_warehouse_id))
            if row.previous_warehouse_id
            else None,
            "new_warehouse_code": codes_by_id.get(str(row.new_warehouse_id))
            if row.new_warehouse_id
            else None,
            "source": row.source,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
    return {"items": items, "total": total, "page": page, "limit": limit}
