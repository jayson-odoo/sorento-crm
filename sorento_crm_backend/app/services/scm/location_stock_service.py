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

from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.inventory import Stock, Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.services.error_handler import AppException
from app.services.project_supply_service import ProjectSupplyService, _dec
from app.services.scm.demand import demand_qty, is_open_demand
from app.services.scm.pool_predicate import is_site_pool
from app.services.scm.supplier_scope import is_uuid

_ZERO = Decimal("0")


def location_stock_for_product(db: Session, product_id: str) -> dict[str, Any]:
    """Every ACTIVE site pool, plus each project bin carrying a nonzero figure.

    R16 (captain, 28 Aug): a SITE POOL is listed whatever it holds. Dropping the all-zero
    pools answered a different question - "DC1 has none" is a fact a buyer choosing where
    to buy into needs to read, while a missing row says only that nobody told them, and
    the two are indistinguishable on screen.

    A PROJECT BIN is still dropped when every figure is zero: there are fifty-five of them
    against five pools, and listing them all would turn the dialog into the warehouse list
    rather than an answer.

    Ordered pools first, then bins, each by warehouse code - one reading order, so this
    dialog is walked the same way as the fulfilment board's own location table rather than
    in whatever order Postgres returned the warehouses.

    BL-1: a caller-supplied ``product_id`` that is not id-shaped reached the UUID columns
    raw (``Stock.product_id == product_id`` etc.) and 500'd on `InvalidTextRepresentation`.
    Guarded the same way `supplier_scope.is_uuid` guards every other id-shaped query param
    in this module.
    """
    if not is_uuid(product_id):
        raise AppException(404, "Product not found")

    supply = ProjectSupplyService(db)

    warehouses = (
        db.query(Warehouse.id, Warehouse.warehouse_code, Warehouse.segment)
        .filter(Warehouse.is_active.is_(True))
        .all()
    )
    warehouse_ids = [str(w.id) for w in warehouses]
    code_by_id = {str(w.id): w.warehouse_code for w in warehouses}
    # `segment` is the test, through the one module that spells it (`pool_predicate`) - it
    # was written out by hand here, which is how this panel could come to disagree with the
    # cell that opens it. This is the same rule the reorder engine reads, so this panel's
    # `on_hand` and the engine's counted `on_hand` for the SAME location can never
    # disagree about which side of the dealer/project line it sits on (captain, 20 Aug:
    # pool-only counted supply). NOT `pool_warehouse_id`: that FK also drives the
    # unrelated fulfilment-pool netting opt-in, whose members are not necessarily
    # project-segment locations.
    is_pool_by_id = {str(w.id): is_site_pool(w.segment) for w in warehouses}

    # What is already ORDERED into each location, on the same predicate `scm.po_ordered_v`
    # and `po_book_service` use - one definition of "still to come" per screen, so the
    # dialog's PO qty column and the row's own PO cell cannot disagree.
    po_by_wh = {
        str(r[0]): float(r[1] or 0)
        for r in db.execute(text("""
            SELECT pol.warehouse_id, SUM(pol.qty_ordered - pol.qty_received)
              FROM purchase_order_lines pol
              JOIN purchase_orders po ON po.id = pol.purchase_order_id
             WHERE pol.product_id = CAST(:pid AS uuid)
               AND pol.warehouse_id IS NOT NULL
               AND po.status = ANY(ARRAY['active', 'received', 'partial', 'closed'])
               AND pol.line_status = 'open'
               AND pol.qty_ordered > pol.qty_received
             GROUP BY pol.warehouse_id
        """), {"pid": str(product_id)}).all()
    }

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
        po_qty = po_by_wh.get(wid, 0.0)
        # Signed, never clamped - `stock_detail`'s own formula (AutoCount arithmetic: a
        # location oversold by more than it holds says so as a negative number).
        available = on_hand - so_qty + spo_qty
        is_pool = is_pool_by_id.get(wid, True)
        if not is_pool and not any((on_hand, reserved, held_qty, free_qty, so_qty,
                                    spo_qty, available, po_qty)):
            # An empty project bin only. A pool holding nothing still says so (R16).
            continue
        locations.append({
            "warehouse_id": wid,
            "warehouse_code": code_by_id.get(wid),
            # Whether THIS location's own stock is counted by the reorder engine's
            # `on_hand` (pool-only, captain 20 Aug) or is project-held supply that is
            # visible here but not counted there.
            "is_pool": is_pool,
            "on_hand": float(on_hand),
            "reserved": float(reserved),
            "held_by_decisions": float(held_qty),
            "free": float(free_qty),
            "so_qty": float(so_qty),
            "spo_qty": float(spo_qty),
            "available": float(available),
            # Ordered, not yet received, bound HERE. A location with nothing on order says
            # 0 rather than null: the purchase book has an answer for every location.
            "po_qty": po_qty,
        })

    # Pools first, then bins, each by code (R16). The query above returns the warehouses
    # in no stated order at all, so without this the same product listed its locations
    # differently on two reads of the same page.
    locations.sort(key=lambda loc: (not loc["is_pool"], loc["warehouse_code"] or ""))

    # The SOURCE of the answer stays inside `_stock_as_of` (its own return says which
    # branch answered, which is what its tests read). The dialog prints one line, "Stock as
    # of <when>", and never names the branch, so shipping the code would be a field with
    # nobody to read it.
    as_of, _source = _stock_as_of(db, product_id)
    return {
        "product_id": str(product_id),
        "as_of": as_of,
        "locations": locations,
    }


def _stock_as_of(db: Session, product_id: str) -> tuple[Optional[str], str]:
    """When the stock shown here was last written, and where that answer came from (R7).

    This used to be ``datetime.utcnow()`` - the moment the dialog asked, which is the one
    thing it is certainly not. AutoCount stock arrives by UPLOAD, so a buyer reading "as of
    now" is told the book is live when it may be three days old, and that is the number
    they decide against.

    Newest ``stock.updated_at`` (or ``created_at`` for a row never updated since its
    insert) for THIS product first, because it is the closest thing to "when did this
    item's figure last move". A product with no stock row at all falls back to the last
    completed stock import, which is when the file that would have moved them was taken. Neither answer available is stated as ``none`` - never
    filled in with the clock.
    """
    # A row inserted by an upload and never updated since carries its write time in
    # `created_at` (`updated_at` stays NULL until a later upload touches it), so the
    # newest write is the max over both, per row.
    newest = (
        db.query(func.max(func.coalesce(Stock.updated_at, Stock.created_at)))
        .filter(Stock.product_id == product_id)
        .scalar()
    )
    if newest is not None:
        return newest.isoformat(), "stock"
    finished = db.execute(text(
        "SELECT max(completed_at) FROM import_jobs "
        "WHERE job_type = 'stock_import' AND completed_at IS NOT NULL"
    )).scalar()
    if finished is not None:
        return finished.isoformat(), "import_job"
    return None, "none"
