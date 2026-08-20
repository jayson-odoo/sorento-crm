"""Per-location live stock for one product, in one call (reorder Buy view expand panel).

The Buy row already prints ONE pool figure. The captain's ask (20 Aug live) is the same
question `stock_detail` answers on the fulfilment board - on hand, SO qty, SPO qty,
available, per warehouse - but for the reorder screen's product-level popup rather than
one product-at-one-location page, so every ACTIVE location shows in a single response
instead of the caller looping a location at a time.

Nothing here is a new opinion about stock. Every figure comes straight off
`ProjectSupplyService`'s own per-location readers - the same ones
`ProjectFulfilmentBoardService.stock_detail` composes - so this popup and the fulfilment
board can never print two different numbers for the same cell. `available` copies
`stock_detail`'s exact formula (on hand, less open SO demand, plus SPO on the water,
SIGNED and never clamped): a location oversold by 200 says so rather than floors at zero.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.services.error_handler import AppException
from app.services.project_supply_service import ProjectSupplyService, _dec
from app.services.scm.demand import demand_qty, is_open_demand
from app.services.scm.supplier_scope import is_uuid

_ZERO = Decimal("0")


def location_stock_for_product(db: Session, product_id: str) -> dict[str, Any]:
    """One row per ACTIVE warehouse carrying any nonzero figure for ``product_id``.

    All-zero locations are dropped - a product simply is not stocked, ordered or
    incoming at most warehouses, and printing every one of them would turn the popup
    into the warehouse list rather than an answer.

    BL-1: a caller-supplied ``product_id`` that is not id-shaped reached the UUID columns
    raw (``Stock.product_id == product_id`` etc.) and 500'd on `InvalidTextRepresentation`.
    Guarded the same way `supplier_scope.is_uuid` guards every other id-shaped query param
    in this module.
    """
    if not is_uuid(product_id):
        raise AppException(404, "Product not found")

    supply = ProjectSupplyService(db)

    warehouses = (
        db.query(Warehouse.id, Warehouse.warehouse_code)
        .filter(Warehouse.is_active.is_(True))
        .all()
    )
    warehouse_ids = [str(w.id) for w in warehouses]
    code_by_id = {str(w.id): w.warehouse_code for w in warehouses}

    levels = supply.stock_levels_by_location([product_id])
    held = supply.held_stock_by_location([product_id])
    free = supply.free_stock_by_location([product_id])
    incoming = supply.incoming_by_location([product_id], warehouse_ids)

    # The whole-book open-SO-demand total, grouped per location - the same predicate
    # `stock_detail` filters ONE warehouse down to (`SalesOrder.status == 'open'` plus
    # `is_open_demand()`), read once for every location instead of once per location.
    owed = demand_qty()
    so_rows = (
        db.query(SalesOrderLine.warehouse_id, func.sum(owed).label("so_qty"))
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .filter(
            SalesOrderLine.product_id == product_id,
            SalesOrder.status == "open",
            is_open_demand(),
        )
        .group_by(SalesOrderLine.warehouse_id)
        .all()
    )
    so_qty_by_wh = {
        str(row.warehouse_id): _dec(row.so_qty)
        for row in so_rows
        if row.warehouse_id is not None
    }

    locations: list[dict[str, Any]] = []
    for wid in warehouse_ids:
        key = (str(product_id), wid)
        on_hand, reserved = levels.get(key, (_ZERO, _ZERO))
        held_qty = held.get(key, _ZERO)
        free_qty = free.get(key, _ZERO)
        so_qty = so_qty_by_wh.get(wid, _ZERO)
        spo_qty = sum((ref.qty for ref in incoming.get(key, [])), _ZERO)
        # Signed, never clamped - `stock_detail`'s own formula (AutoCount arithmetic: a
        # location oversold by more than it holds says so as a negative number).
        available = on_hand - so_qty + spo_qty
        if not any((on_hand, reserved, held_qty, free_qty, so_qty, spo_qty, available)):
            continue
        locations.append({
            "warehouse_id": wid,
            "warehouse_code": code_by_id.get(wid),
            "on_hand": float(on_hand),
            "reserved": float(reserved),
            "held_by_decisions": float(held_qty),
            "free": float(free_qty),
            "so_qty": float(so_qty),
            "spo_qty": float(spo_qty),
            "available": float(available),
        })

    return {
        "product_id": str(product_id),
        "as_of": datetime.utcnow().isoformat(),
        "locations": locations,
    }
