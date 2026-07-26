"""AutoCount ingest Slice 8 — SO/PO reuse of the SCM tables.

Idempotent by (source_system='autocount', source_ref=DocKey) on the existing
sales_orders / purchase_orders; so_number/po_number = AC-{DocKey}; a line whose
product has not synced makes the whole document retryable; lines replaced
wholesale; the SCM services 403 every mutation on an autocount-sourced row while
annotation stays open.

blank_session (isolated scratch schema, create_savepoint join).
"""
import pytest

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import Supplier, PurchaseOrder, PurchaseOrderLine
from app.services.sales_order_ingest_service import SalesOrderIngestService
from app.services.purchase_order_ingest_service import PurchaseOrderIngestService
from app.services.scm.sales_order_service import SalesOrderService
from app.services.scm.purchase_order_service import PurchaseOrderService
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def seeded(db):
    cat = ProductCategory(category_code="ZZT-C", category_name="C")
    uom = UnitOfMeasure(uom_code="ZZT-U", uom_name="U")
    db.add_all([cat, uom])
    db.flush()
    p = Product(product_code="ZZT-ITEM", product_name="ZZT Item",
                category_id=cat.id, base_uom_id=uom.id, list_price=0)
    wh = Warehouse(warehouse_code="HQ", warehouse_name="Headquarter")
    cust = Customer(customer_code="ZZT-DEB", customer_name="ZZT Debtor")
    sup = Supplier(supplier_code="ZZT-SUP", supplier_name="ZZT Supplier")
    db.add_all([p, wh, cust, sup])
    db.flush()
    return {"product": p, "warehouse": wh, "customer": cust, "supplier": sup}


# --------------------------------------------------------------------------- SO
def _so_line(product="ZZT-ITEM", qty="10", **extra):
    return {"product_code": product, "location": "HQ", "uom": "PCS", "qty": qty,
            "transfered_qty": "2", "unit_price": "5.00", "discount_amt": "0",
            "tax_code": "SR", "tax_rate": "6", "tax_amt": "3", "sub_total": "50",
            "delivery_date": "2026/08/01", **extra}


def _so(dockey="SK1", **extra):
    return {"source_ref": dockey, "source_doc_no": f"SO-{dockey}",
            "debtor_code": "ZZT-DEB", "doc_date": "2026/07/26",
            "lines": [_so_line()], **extra}


class TestSalesOrder:
    def test_create_maps_pricing_and_provenance(self, db, seeded):
        res = SalesOrderIngestService(db).ingest([_so()])
        assert res.created == 1
        so = db.query(SalesOrder).one()
        assert so.so_number == "AC-SK1"
        assert so.source_system == "autocount"
        assert so.source_ref == "SK1"
        assert so.customer_id == seeded["customer"].id
        line = db.query(SalesOrderLine).filter_by(sales_order_id=so.id).one()
        assert line.product_id == seeded["product"].id
        assert line.warehouse_id == seeded["warehouse"].id
        assert str(line.qty_ordered) == "10.0000"
        assert str(line.qty_delivered) == "2.0000"
        assert line.tax_code == "SR"
        assert str(line.unit_price) == "5.00"

    def test_idempotent_by_source_ref(self, db, seeded):
        SalesOrderIngestService(db).ingest([_so()])
        first = db.query(SalesOrder).one().id
        res = SalesOrderIngestService(db).ingest([_so(lines=[_so_line(qty="99")])])
        assert res.updated == 1
        assert db.query(SalesOrder).count() == 1
        assert db.query(SalesOrder).one().id == first
        line = db.query(SalesOrderLine).one()
        assert str(line.qty_ordered) == "99.0000"

    def test_missing_product_retryable(self, db, seeded):
        res = SalesOrderIngestService(db).ingest([_so(lines=[_so_line(product="PHANTOM")])])
        assert res.retryable == 1
        assert db.query(SalesOrder).count() == 0

    def test_serialize_exposes_source_and_pricing(self, db, seeded):
        SalesOrderIngestService(db).ingest([_so()])
        so = db.query(SalesOrder).one()
        data = SalesOrderService(db).serialize(so)
        assert data["source"] == "autocount"
        assert data["source_doc_no"] == "SO-SK1"
        assert data["lines"][0]["unit_price"] == 5.0
        assert data["lines"][0]["tax_code"] == "SR"

    def test_update_forbidden_annotation_allowed(self, db, seeded):
        SalesOrderIngestService(db).ingest([_so()])
        so = db.query(SalesOrder).one()
        svc = SalesOrderService(db)

        class _U:
            customer_code = order_type = priority = requested_delivery_date = lines = None
        with pytest.raises(AppException) as ei:
            svc.update(so.id, _U(), user_id=None)
        assert ei.value.status_code == 403

        with pytest.raises(AppException):
            svc.delete(so.id)

        out = svc.annotate(so.id, internal_note="watch", follow_up=True)
        assert out["internal_note"] == "watch"
        assert out["follow_up"] is True
        assert out["source"] == "autocount"


# --------------------------------------------------------------------------- PO
def _po_line(product="ZZT-ITEM", qty="8", **extra):
    return {"product_code": product, "location": "HQ", "qty": qty,
            "unit_price": "4.50", "description": "PO line", "sub_total": "36", **extra}


def _po(dockey="PK1", **extra):
    return {"source_ref": dockey, "source_doc_no": f"PO-{dockey}",
            "creditor_code": "ZZT-SUP", "doc_date": "2026/07/26",
            "lines": [_po_line()], **extra}


class TestPurchaseOrder:
    def test_create_maps_and_provenance(self, db, seeded):
        res = PurchaseOrderIngestService(db).ingest([_po()])
        assert res.created == 1
        po = db.query(PurchaseOrder).one()
        assert po.po_number == "AC-PK1"
        assert po.source_system == "autocount"
        assert po.status == "active"
        assert po.supplier_id == seeded["supplier"].id
        line = db.query(PurchaseOrderLine).filter_by(purchase_order_id=po.id).one()
        assert line.product_id == seeded["product"].id
        assert str(line.unit_cost) == "4.50"
        assert line.description == "PO line"

    def test_cancelled_maps_to_status(self, db, seeded):
        PurchaseOrderIngestService(db).ingest([_po(is_cancelled=True)])
        assert db.query(PurchaseOrder).one().status == "cancelled"

    def test_idempotent_and_wholesale_lines(self, db, seeded):
        PurchaseOrderIngestService(db).ingest([_po()])
        first = db.query(PurchaseOrder).one().id
        res = PurchaseOrderIngestService(db).ingest([_po(lines=[_po_line(), _po_line(qty="1")])])
        assert res.updated == 1
        assert db.query(PurchaseOrder).one().id == first
        assert db.query(PurchaseOrderLine).count() == 2

    def test_missing_product_retryable(self, db, seeded):
        res = PurchaseOrderIngestService(db).ingest([_po(lines=[_po_line(product="PHANTOM")])])
        assert res.retryable == 1
        assert db.query(PurchaseOrder).count() == 0

    def test_serialize_source_and_create_gr_forbidden(self, db, seeded):
        PurchaseOrderIngestService(db).ingest([_po()])
        po = db.query(PurchaseOrder).one()
        svc = PurchaseOrderService(db)
        data = svc.serialize(po)
        assert data["source"] == "autocount"
        assert data["lines"][0]["description"] == "PO line"
        with pytest.raises(AppException) as ei:
            svc.create_gr(po.id)
        assert ei.value.status_code == 403
        out = svc.annotate(po.id, internal_note="chase", follow_up=True)
        assert out["internal_note"] == "chase"


class TestDryRun:
    def test_so_dry_run_writes_nothing(self, db, seeded):
        res = SalesOrderIngestService(db).ingest([_so()], dry_run=True)
        assert res.created == 1
        assert db.query(SalesOrder).count() == 0

    def test_po_dry_run_writes_nothing(self, db, seeded):
        res = PurchaseOrderIngestService(db).ingest([_po()], dry_run=True)
        assert res.created == 1
        assert db.query(PurchaseOrder).count() == 0
