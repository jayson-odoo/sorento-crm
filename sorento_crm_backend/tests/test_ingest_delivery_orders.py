"""AutoCount ingest Slice 5 — delivery order -> REUSE orders + order_lines.

Document semantics: idempotent by DocKey (source_ref) via integration_references;
order_number = AC-{DocKey}; sync_source='autocount' makes the row read-only in
the Orders UI, enforced server-side in OrderService (this file covers the 403
guard + the annotation carve-out too). A line whose product OR warehouse has not
synced makes the WHOLE order retryable (never half-written).

blank_session (isolated scratch schema, create_savepoint join) so raw-SQL inserts
+ the service commits stay contained.
"""
import pytest

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.inventory import Warehouse
from app.models.order import Order, OrderLine, Customer
from app.models.integration_reference import IntegrationReference
from app.schemas.order import OrderUpdate, OrderLineCreate
from app.services.delivery_order_ingest_service import DeliveryOrderIngestService
from app.services.order_service import OrderService
from app.services.error_handler import AppException
from app.services.integration_reference_service import IntegrationReferenceService
from tests._pg_fixture import blank_session


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def svc(db):
    return DeliveryOrderIngestService(db, integration_id=None)


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
    db.add_all([p, wh, cust])
    db.flush()
    return {"product": p, "warehouse": wh, "customer": cust}


def _line(product="ZZT-ITEM", loc="HQ", qty="5", **extra):
    return {"product_code": product, "location_code": loc, "qty": qty,
            "unit_price": "12.50", "discount": "0", "tax": "0.75",
            "sub_total": "62.50", **extra}


def _do(dockey="DK1", debtor="ZZT-DEB", **extra):
    return {"source_ref": dockey, "source_doc_no": f"DO-{dockey}",
            "debtor_code": debtor, "debtor_name": "ZZT Debtor",
            "order_date": "2026/07/26", "agent": "AG1",
            "lines": [_line()], **extra}


class TestCreate:
    def test_creates_order_with_lines(self, db, svc, seeded):
        res = svc.ingest([_do()])
        assert res.created == 1
        order = db.query(Order).one()
        assert order.order_number == "AC-DK1"
        assert order.sync_source == "autocount"
        assert order.debtor_code == "ZZT-DEB"
        assert order.customer_id == seeded["customer"].id  # best-effort resolved
        lines = db.query(OrderLine).filter_by(order_id=order.id).all()
        assert len(lines) == 1
        assert lines[0].product_id == seeded["product"].id
        assert lines[0].warehouse_id == seeded["warehouse"].id
        assert str(lines[0].quantity) == "5.0000"

    def test_links_integration_reference(self, db, svc, seeded):
        svc.ingest([_do()])
        order = db.query(Order).one()
        ref = db.query(IntegrationReference).filter_by(
            entity_type="orders", source_ref="DK1"
        ).one()
        assert ref.entity_id == order.id
        assert ref.source_doc_no == "DO-DK1"

    def test_customer_unresolved_is_ok(self, db, svc, seeded):
        # A debtor code with no matching customer still ingests (FK nullable).
        res = svc.ingest([_do(debtor="NOPE")])
        assert res.created == 1
        assert db.query(Order).one().customer_id is None


class TestIdempotency:
    def test_reingest_same_dockey_updates_in_place(self, db, svc, seeded):
        svc.ingest([_do()])
        first = db.query(Order).one().id
        res = svc.ingest([_do(agent="AG2")])
        assert res.updated == 1
        assert db.query(Order).count() == 1
        order = db.query(Order).one()
        assert order.id == first
        assert order.agent == "AG2"

    def test_reingest_replaces_lines_wholesale(self, db, svc, seeded):
        svc.ingest([_do()])
        # Second push carries two lines -> old single line is gone, not merged.
        svc.ingest([_do(lines=[_line(), _line(qty="9")])])
        order = db.query(Order).one()
        assert db.query(OrderLine).filter_by(order_id=order.id).count() == 2


class TestRetryable:
    def test_missing_product_makes_whole_order_retryable(self, db, svc, seeded):
        res = svc.ingest([_do(lines=[_line(product="PHANTOM")])])
        assert res.retryable == 1
        assert res.created == 0
        assert db.query(Order).count() == 0  # never half-written

    def test_missing_warehouse_makes_whole_order_retryable(self, db, svc, seeded):
        res = svc.ingest([_do(lines=[_line(loc="NOWHERE")])])
        assert res.retryable == 1
        assert db.query(Order).count() == 0


class TestDryRun:
    def test_dry_run_writes_nothing(self, db, svc, seeded):
        res = svc.ingest([_do()], dry_run=True)
        assert res.created == 1  # verdict says it WOULD create
        assert db.query(Order).count() == 0  # but nothing persisted


class TestSourceGate:
    """sync_source='autocount' => every mutation 403; annotation still allowed."""

    def _make_autocount_order(self, db, svc, seeded):
        svc.ingest([_do()])
        return db.query(Order).one()

    def test_update_is_forbidden(self, db, svc, seeded):
        order = self._make_autocount_order(db, svc, seeded)
        os = OrderService(db)
        with pytest.raises(AppException) as ei:
            os.update_order(order.id, OrderUpdate(remarks="hi"), updated_by=None)
        assert ei.value.status_code == 403
        assert ei.value.detail["code"] == "AUTOCOUNT_READ_ONLY"

    def test_delete_is_forbidden(self, db, svc, seeded):
        order = self._make_autocount_order(db, svc, seeded)
        os = OrderService(db)
        with pytest.raises(AppException) as ei:
            os.delete_order(order.id)
        assert ei.value.status_code == 403

    def test_create_line_is_forbidden(self, db, svc, seeded):
        order = self._make_autocount_order(db, svc, seeded)
        os = OrderService(db)
        with pytest.raises(AppException) as ei:
            os.create_order_line(order.id, OrderLineCreate(
                product_id=seeded["product"].id, warehouse_id=seeded["warehouse"].id,
                quantity="1"))
        assert ei.value.status_code == 403

    def test_annotation_is_allowed(self, db, svc, seeded):
        order = self._make_autocount_order(db, svc, seeded)
        os = OrderService(db)
        updated = os.annotate_order(order.id, internal_note="checked", follow_up=True)
        assert updated.internal_note == "checked"
        assert updated.follow_up is True
        # ingest still owns the row -- annotation did not flip provenance
        assert updated.sync_source == "autocount"

    def test_native_order_still_mutable(self, db, seeded):
        # A manually-created order (sync_source defaults 'manual') is untouched.
        order = Order(order_number="NATIVE-1", sync_source="manual")
        db.add(order)
        db.flush()
        os = OrderService(db)
        os.update_order(order.id, OrderUpdate(remarks="ok"), updated_by=None)
        assert db.query(Order).filter_by(order_number="NATIVE-1").one().remarks == "ok"
