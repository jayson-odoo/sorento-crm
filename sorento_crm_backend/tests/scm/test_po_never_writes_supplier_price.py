"""Saving a purchase order never writes a supplier price (#1288, fix lane round 3, R1).

Owner ruling on Q16 (27 Sep 2026, 15:31 MYT): "purchase order shouldn't do this la, product
excel import also shouldnt do this". The cost lists are the only source of a supplier cost,
so revising, adding a line to, or confirming a purchase order must leave the
product-supplier link's `unit_cost`/`currency` and the product's `cost_price` exactly as they
were. The order keeps its own line price.

Measured at the start of round 3 (plan section 7.5): no purchase order path writes either
column today. This file pins that, so a future "remember the last paid price" shortcut on a
PO save goes red here rather than quietly overwriting a cost list's price in force.

Postgres only, every FK seeded here (never a borrowed `LIMIT 1` row), rolled back with the
`scm_app` savepoint.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.models.inventory import Warehouse
from app.models.procurement import (
    ProductSupplier, PurchaseOrder, PurchaseOrderLine, Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZCPR3"


def _uid() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{_uid()[:8]}".upper()


def _seed(scm_app):
    app, db, gcu, gcuak = scm_app
    as_user(app, gcu, gcuak, seed_user(db, "purchasing"))

    uom = UnitOfMeasure(id=_uid(), uom_code=_code("UOM")[:20], uom_name="Pieces")
    category = ProductCategory(
        id=_uid(), category_code=_code("CAT"), category_name=f"{MARKER} category"
    )
    db.add_all([uom, category])
    db.flush()
    product = Product(
        id=_uid(), product_code=_code("SKU"), product_name=f"{MARKER} basin",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("120.00"),
        cost_price=Decimal("70.00"),
    )
    supplier = Supplier(
        id=_uid(), supplier_code=_code("SUP")[:30], supplier_name=f"{MARKER} Ceramics",
        is_active=True,
    )
    warehouse = Warehouse(
        id=_uid(), warehouse_code=_code("WH")[:20], warehouse_name=f"{MARKER} store",
        is_active=True,
    )
    db.add_all([product, supplier, warehouse])
    db.flush()
    link = ProductSupplier(
        id=_uid(), product_id=product.id, supplier_id=supplier.id,
        standard_lead_time_days=30, unit_cost=Decimal("100.00"), currency="CNY",
    )
    db.add(link)
    po = PurchaseOrder(
        id=_uid(), po_number=_code("PO"), supplier_id=supplier.id,
        status="draft_recommendation", issue_date=date(2026, 9, 27),
        expected_date=date(2026, 10, 27), currency="USD", source_system="scm_upload",
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_uid(), purchase_order_id=po.id, product_id=product.id,
        warehouse_id=warehouse.id, qty_ordered=Decimal("10"), qty_received=Decimal("0"),
        unit_cost=Decimal("55.00"), currency="USD", line_status="open",
    )
    db.add(line)
    db.flush()
    return app, db, product, link, po, line


def _link_price(db, link_id):
    db.expire_all()
    ps = db.query(ProductSupplier).filter(ProductSupplier.id == link_id).one()
    return ps.unit_cost, ps.currency


def test_revising_and_confirming_a_po_leaves_the_supplier_price_alone(scm_app):
    app, db, product, link, po, line = _seed(scm_app)

    with TestClient(app) as c:
        # Revise: re-price the existing line and add a second, new line at another price.
        res = c.put(f"/api/v1/scm/purchase-orders/{po.id}", json={"lines": [
            {"id": line.id, "sku": product.product_code, "qty_ordered": 10,
             "unit_price": 66.0},
            {"sku": product.product_code, "qty_ordered": 5, "unit_price": 77.0},
        ]})
        assert res.status_code == 200, res.text
        prices = sorted(Decimal(str(ln["unit_price"])) for ln in res.json()["lines"])
        # The PO keeps its own line prices.
        assert prices == [Decimal("66.00"), Decimal("77.00")]
        assert _link_price(db, link.id) == (Decimal("100.00"), "CNY")

        # Confirm.
        res = c.post("/api/v1/scm/purchase-orders/bulk-confirm", json={"ids": [po.id]})
        assert res.status_code == 200, res.text

    assert _link_price(db, link.id) == (Decimal("100.00"), "CNY")
    db.expire_all()
    assert db.query(Product).filter(Product.id == product.id).one().cost_price == Decimal("70.00")
    stored = sorted(
        ln.unit_cost for ln in
        db.query(PurchaseOrderLine).filter(PurchaseOrderLine.purchase_order_id == po.id).all()
    )
    assert stored == [Decimal("66.00"), Decimal("77.00")]
