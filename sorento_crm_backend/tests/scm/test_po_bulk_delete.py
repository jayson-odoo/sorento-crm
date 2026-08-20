"""SCM purchase orders — bulk delete (captain, 20 Aug: "give me an option to bulk delete
purchase orders ... maybe need to recreate").

Covers: the happy path (hard delete, lines cascade), the side effect on an order-inquiry
row PLACED on one of the deleted lines (unplaced back to `raised`, not left dangling),
auth denial, empty-ids validation, and honest skipping of an id that does not exist.

Same discipline as `tests/scm/test_m1_purchase_orders.py`: every purchase order, supplier,
order inquiry and row is seeded by the test under its own marker, inside the `scm_app`
savepoint, which rolls back.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient

from tests.scm.conftest import (
    _REF_PRODUCT_CODE,
    _REF_WAREHOUSE_CODE,
    as_user,
    requires_pg,
    seed_user,
)

pytestmark = requires_pg


def _as(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _seed_po(db, marker: str) -> tuple[str, str, str]:
    """A purchase order this test owns, with one open line. Returns
    (po_id, po_number, po_line_id)."""
    from app.models.inventory import Warehouse
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
    from app.models.product import Product

    product = db.query(Product).filter(Product.product_code == _REF_PRODUCT_CODE).one()
    warehouse = (
        db.query(Warehouse).filter(Warehouse.warehouse_code == _REF_WAREHOUSE_CODE).one()
    )
    supplier = Supplier(
        id=str(uuid.uuid4()), supplier_code=marker[:30], supplier_name=f"{marker} supplier",
    )
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(
        id=str(uuid.uuid4()), po_number=marker, supplier_id=str(supplier.id),
        status="active", issue_date=date(2026, 7, 16), expected_date=date(2026, 8, 4),
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=str(uuid.uuid4()), purchase_order_id=str(po.id), product_id=str(product.id),
        warehouse_id=str(warehouse.id), qty_ordered=500, qty_received=0,
        line_status="open", expected_date=date(2026, 8, 4),
    )
    db.add(line)
    db.flush()
    return str(po.id), marker, str(line.id)


def _seed_placed_row(db, marker: str, po_line_id: str, *, qty=10) -> str:
    """An order-inquiry row PLACED on `po_line_id`, mirroring what `place_on_po` writes
    (`project_order_inquiry_service.place_on_po`), so the bulk-delete side effect has a
    real row to unplace. Returns the row id."""
    from app.models.project_so import (
        INQUIRY_PLACED,
        IV_ORDER,
        OrderInquiry,
        OrderInquiryRow,
        ProjectSalesOrder,
    )

    order = ProjectSalesOrder(id=str(uuid.uuid4()), provisional_ref=marker)
    db.add(order)
    db.flush()
    inquiry = OrderInquiry(id=str(uuid.uuid4()), project_sales_order_id=order.id)
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=str(uuid.uuid4()), order_inquiry_id=inquiry.id, item_code=marker, qty=qty,
        verb=IV_ORDER, state=INQUIRY_PLACED, po_ref=marker, po_line_id=po_line_id,
        note="pre-existing note",
    )
    db.add(row)
    db.flush()
    return str(row.id)


def _po_exists(db, po_id: str) -> bool:
    from app.models.procurement import PurchaseOrder
    return db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first() is not None


def test_bulk_delete_removes_the_orders_and_their_lines(scm_app):
    app, db = _as(scm_app, "purchasing")
    marker_a = f"ZZBD-A-{uuid.uuid4().hex[:8]}"
    marker_b = f"ZZBD-B-{uuid.uuid4().hex[:8]}"
    po_a, _num_a, line_a = _seed_po(db, marker_a)
    po_b, _num_b, line_b = _seed_po(db, marker_b)

    with TestClient(app) as c:
        res = c.post("/api/v1/scm/purchase-orders/bulk-delete", json={"ids": [po_a, po_b]})

    assert res.status_code == 200, res.text
    assert res.json() == {"deleted": 2, "unplaced_rows": 0}
    assert not _po_exists(db, po_a)
    assert not _po_exists(db, po_b)
    from app.models.procurement import PurchaseOrderLine
    assert db.query(PurchaseOrderLine).filter(
        PurchaseOrderLine.id.in_([line_a, line_b])
    ).count() == 0, "lines must cascade with their header"


def test_bulk_delete_unplaces_an_order_inquiry_row_placed_on_a_deleted_line(scm_app):
    """The row this deletion would otherwise strand: `po_line_id` SET NULL by the FK
    alone would leave it `state = 'placed'` and permanently out of the reorder engine,
    even though the supply it was placed against is gone. It must come back to
    `raised` with the placement cleared and a note explaining why."""
    app, db = _as(scm_app, "purchasing")
    marker = f"ZZBD-UNP-{uuid.uuid4().hex[:8]}"
    po_id, po_number, line_id = _seed_po(db, marker)
    row_id = _seed_placed_row(db, marker, line_id)

    with TestClient(app) as c:
        res = c.post("/api/v1/scm/purchase-orders/bulk-delete", json={"ids": [po_id]})

    assert res.status_code == 200, res.text
    assert res.json() == {"deleted": 1, "unplaced_rows": 1}

    from app.models.project_so import INQUIRY_RAISED, OrderInquiryRow
    row = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_id).one()
    assert row.state == INQUIRY_RAISED
    assert row.po_ref is None
    assert row.po_line_id is None
    assert row.note == "pre-existing note; PO deleted - back on the board"
    assert not _po_exists(db, po_id)


def test_bulk_delete_denied_without_reorder_run_permission(scm_app):
    app, _db = _as(scm_app, None)
    with TestClient(app) as c:
        res = c.post("/api/v1/scm/purchase-orders/bulk-delete", json={"ids": [str(uuid.uuid4())]})
    assert res.status_code == 403, res.text


def test_bulk_delete_with_no_ids_is_rejected(scm_app):
    app, _db = _as(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.post("/api/v1/scm/purchase-orders/bulk-delete", json={"ids": []})
    assert res.status_code == 422, res.text


def test_bulk_delete_skips_an_id_that_does_not_exist(scm_app):
    """A stale row in the caller's selection (already deleted by someone else, or never
    existed) must not fail the batch - it is skipped, and the count says so honestly."""
    app, db = _as(scm_app, "purchasing")
    marker = f"ZZBD-MIX-{uuid.uuid4().hex[:8]}"
    po_id, _num, _line = _seed_po(db, marker)
    unknown = str(uuid.uuid4())

    with TestClient(app) as c:
        res = c.post(
            "/api/v1/scm/purchase-orders/bulk-delete", json={"ids": [po_id, unknown]}
        )

    assert res.status_code == 200, res.text
    assert res.json() == {"deleted": 1, "unplaced_rows": 0}
    assert not _po_exists(db, po_id)
