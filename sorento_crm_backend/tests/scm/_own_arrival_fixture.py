"""Shared seeding for the S1/S2/S3 red tests of
`documentation/plans/scm/PLAN-board-received-stock-own-arrival.md` (UAC
`board-received-stock-own-arrival-acceptance-criteria.md`).

The UAC's own fixture-shape paragraph, restated as helpers rather than copied five times:
one sales order with lines L1..L6 of one product; PO lines bought for L1..L6
(`from_so_line_ref` = each line's own `source_ref`), closed, `qty_received = qty_ordered`;
SPO allocations `fully_received` with `from_po_number` = that PO; on hand at the line's
location >= the received total; a second sales order of the same product with earlier and
later lines.

Two fixture families live here, because the plan's own seams sit at two different layers:

* S1/S2 and S3's ladder-level ACs (S3-1..S3-5, S3-9) ask the FULFILMENT BOARD
  (`FulfilmentBoardService.build`) and `planning_change_service`'s pure composers, which
  both read CORE `sales_orders` / `sales_order_lines` directly - no `ProjectSalesOrder`
  wrapper needed, the same convention `tests/test_fulfilment_board.py`'s own `_group_world`
  uses.
* S3's path-picker ACs (S3-6..S3-8) ask `project_order_inquiry_service.py` /
  `planning_change_service.set_row_decision`, which DO need the project layer
  (`ProjectSalesOrder` / `ProjectSalesOrderLine` / `OrderInquiryRow`), the same convention
  `tests/test_planning_changes.py`'s `api` fixture uses.

Postgres only (`tests/_pg_fixture.py`), every FK seeded here, never a borrowed row.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from tests.test_fulfilment_board import (  # noqa: F401  (helpers, not fixtures)
    _line,
    _order,
    _product,
    _uid,
    _warehouse,
)

MARKER = "zzt-ownarrival"


def own_arrival_group(db):
    """A fresh ownership group + product, for one test's own world. Returns `(group,
    product)`."""
    group = f"OA{_uid()[:4]}".upper()
    product = _product(db, f"ZZT-{_uid()[:8]}")
    return group, product


def own_arrival_warehouse(db, group: str, *, site: str = "BRW"):
    """One warehouse in `group` - `ZZT<SITE>-<GROUP>`, the same hyphenated-suffix shape
    `sales_agent_service.group_of_warehouse_code` parses (`_group_world`'s own convention)."""
    return _warehouse(db, f"ZZT{site}{_uid()[:4]}-{group}"[:20])


def supplier_and_po(db, *, po_number: Optional[str] = None):
    from app.models.procurement import PurchaseOrder, Supplier

    supplier = Supplier(
        id=_uid(), supplier_code=f"ZZT-{_uid()[:8]}", supplier_name=f"{MARKER} supplier",
    )
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(
        id=_uid(), po_number=po_number or f"ZZT-PO-{_uid()[:8]}", supplier_id=supplier.id,
        status="active",
    )
    db.add(po)
    db.flush()
    return po


def po_line_bought_for(
    db, po, product, warehouse, *, from_so_line_ref: str, qty_received, qty_ordered=None,
    line_status: str = "closed",
):
    """A PurchaseOrderLine bought FOR one sales-order line: `from_so_line_ref` names the
    line's own `source_ref`, and it is fully received - the plan's tier-1 own-arrival
    fixture shape."""
    from app.models.procurement import PurchaseOrderLine

    row = PurchaseOrderLine(
        id=_uid(), purchase_order_id=po.id, product_id=product.id, warehouse_id=warehouse.id,
        qty_ordered=Decimal(str(qty_ordered if qty_ordered is not None else qty_received)),
        qty_received=Decimal(str(qty_received)), line_status=line_status,
        from_so_line_ref=from_so_line_ref,
    )
    db.add(row)
    db.flush()
    return row


def spo_allocation_fully_received(
    db, product, warehouse, *, qty, from_po_number: str, spo_number: Optional[str] = None,
    arrives: Optional[date] = None,
):
    """A received SPO allocation naming the PO it came off (`from_po_number`) - the
    "landed" half of the fixture shape, `po_line_id` deliberately left NULL (the real
    prod shape: an SPO share's own PO reference travels as the document NUMBER, not a row
    reference)."""
    from app.models.procurement import SPOAllocation

    row = SPOAllocation(
        id=_uid(), spo_number=spo_number or f"ZZT-SPO-{_uid()[:8]}", spo_line_number=1,
        product_id=product.id, warehouse_id=warehouse.id,
        allocated_quantity=int(qty), quantity_received=int(qty),
        receipt_status="fully_received", line_status="closed",
        from_po_number=from_po_number, expected_date=arrives,
    )
    db.add(row)
    db.flush()
    return row


def order_with_lines(
    db, *, so_number: Optional[str] = None, product, warehouse, lines: list[dict],
    order_date=date(2026, 1, 1),
):
    """`lines`: `[{"qty": "20", "required_date": date(...), "source_ref": "L2",
    "line_status": "open", "delivered": "0"}, ...]`. Returns `(order, [core lines])`, in
    the SAME order as `lines`.
    """
    order = _order(db, so_number=so_number or f"ZZT-SO-{_uid()[:8]}", order_date=order_date)
    core_lines = []
    for spec in lines:
        core_line = _line(
            db, order, product, qty=spec["qty"], required_date=spec.get("required_date"),
            warehouse=warehouse, delivered=spec.get("delivered", "0"),
            line_status=spec.get("line_status", "open"),
        )
        core_line.source_ref = spec["source_ref"]
        db.flush()
        core_lines.append(core_line)
    return order, core_lines
