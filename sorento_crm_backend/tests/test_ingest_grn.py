"""AutoCount GRN ingest (S17) -> REUSE picking_headers + picking_lines.

Document semantics: idempotent by source_ref (the stable AutoCount {db}:{AutoKey})
via integration_references (entity_type 'picking_headers'); picking_number is
DISPLAY + mutable and is never the adopt key. Quantities are Decimal ("2.5" must
not truncate). supplier_code + uom resolve-or-null (a miss is not a failure);
product / warehouse (location) misses make the WHOLE GRN retryable (never
half-written).

blank_session (isolated scratch schema, create_savepoint join) so the service's
savepoints + commits stay contained and company_id auto-stamps resolve.
"""
import pytest

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.inventory import Warehouse
from app.models.procurement import PickingHeader, PickingLine, Supplier
from app.models.integration_reference import IntegrationReference
from app.schemas.external.procurement import GRNRequest
from app.services.grn_ingest_service import GrnIngestService
from tests._pg_fixture import blank_session


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def svc(db):
    return GrnIngestService(db, integration_id=None)


@pytest.fixture()
def seeded(db):
    cat = ProductCategory(category_code="ZZT-C", category_name="C")
    uom = UnitOfMeasure(uom_code="ZZT-U", uom_name="U")
    db.add_all([cat, uom])
    db.flush()
    p = Product(product_code="ZZT-ITEM", product_name="ZZT Item",
                category_id=cat.id, base_uom_id=uom.id, list_price=0)
    wh = Warehouse(warehouse_code="HQ", warehouse_name="Headquarter")
    sup = Supplier(supplier_code="ZZT-SUP", supplier_name="ZZT Supplier")
    db.add_all([p, wh, sup])
    db.flush()
    return {"product": p, "warehouse": wh, "uom": uom, "supplier": sup}


def _line(product="ZZT-ITEM", loc="HQ", qty="2.5", uom="ZZT-U"):
    return {"product_code": product, "location": loc, "quantity": qty, "uom": uom}


def _grn(source_ref="GRN17:1", picking_number="GRN-0012", supplier="ZZT-SUP", **hdr):
    body = {
        "goods_receive_notes": {
            "picking_number": picking_number,
            "picking_date": "2024-01-15",
            "notes": "received",
            "supplier_code": supplier,
            "source_ref": source_ref,
        },
        "grn_lines": [_line()],
    }
    body["goods_receive_notes"].update(hdr)
    return GRNRequest(**body)


class TestCreate:
    def test_creates_picking_with_lines(self, db, svc, seeded):
        res = svc.ingest(_grn())
        assert res.created == 1
        header = db.query(PickingHeader).one()
        assert header.picking_number == "GRN-0012"
        assert header.picking_type == "goods_received"
        assert header.supplier_code == "ZZT-SUP"
        assert header.supplier_id == seeded["supplier"].id
        lines = db.query(PickingLine).filter_by(picking_header_id=header.id).all()
        assert len(lines) == 1
        assert lines[0].product_id == seeded["product"].id
        assert lines[0].source_warehouse_id == seeded["warehouse"].id
        assert lines[0].uom_id == seeded["uom"].id

    def test_decimal_quantity_not_truncated(self, db, svc, seeded):
        svc.ingest(_grn())
        line = db.query(PickingLine).one()
        assert str(line.quantity_expected) == "2.5000"
        assert str(line.quantity_picked) == "2.5000"
        assert str(line.quantity_discrepancy) == "0.0000"  # generated column

    def test_links_integration_reference(self, db, svc, seeded):
        svc.ingest(_grn())
        header = db.query(PickingHeader).one()
        ref = db.query(IntegrationReference).filter_by(
            entity_type="picking_headers", source_ref="GRN17:1"
        ).one()
        assert ref.entity_id == header.id
        assert ref.source_doc_no == "GRN-0012"


class TestSupplierResolveOrNull:
    def test_supplier_miss_keeps_code_null_id(self, db, svc, seeded):
        # A supplier code with no match still ingests (captured-if-resolvable).
        res = svc.ingest(_grn(supplier="NOPE"))
        assert res.created == 1
        header = db.query(PickingHeader).one()
        assert header.supplier_code == "NOPE"
        assert header.supplier_id is None

    def test_no_supplier_code_is_ok(self, db, svc, seeded):
        res = svc.ingest(_grn(supplier=None))
        assert res.created == 1
        header = db.query(PickingHeader).one()
        assert header.supplier_code is None
        assert header.supplier_id is None


class TestIdempotency:
    def test_reingest_same_source_ref_updates_in_place(self, db, svc, seeded):
        svc.ingest(_grn())
        first = db.query(PickingHeader).one().id
        # doc no. renamed on the AutoCount side -> still the same picking.
        res = svc.ingest(_grn(picking_number="GRN-RENAMED"))
        assert res.updated == 1
        assert db.query(PickingHeader).count() == 1
        header = db.query(PickingHeader).one()
        assert header.id == first
        assert header.picking_number == "GRN-RENAMED"  # display key rewritten
        assert db.query(IntegrationReference).filter_by(
            entity_type="picking_headers", source_ref="GRN17:1"
        ).count() == 1  # no duplicate reference

    def test_reingest_replaces_lines_wholesale(self, db, svc, seeded):
        svc.ingest(_grn())
        # Second push carries two lines -> old single line is gone, not merged.
        body = _grn()
        body.grn_lines.append(body.grn_lines[0].model_copy(update={"quantity": "9"}))
        svc.ingest(body)
        header = db.query(PickingHeader).one()
        assert db.query(PickingLine).filter_by(picking_header_id=header.id).count() == 2


class TestRetryable:
    def test_missing_product_makes_whole_grn_retryable(self, db, svc, seeded):
        body = _grn()
        body.grn_lines[0].product_code = "PHANTOM"
        res = svc.ingest(body)
        assert res.retryable == 1
        assert res.created == 0
        assert db.query(PickingHeader).count() == 0  # never half-written

    def test_missing_warehouse_makes_whole_grn_retryable(self, db, svc, seeded):
        body = _grn()
        body.grn_lines[0].location = "NOWHERE"
        res = svc.ingest(body)
        assert res.retryable == 1
        assert db.query(PickingHeader).count() == 0


class TestUomBestEffort:
    def test_uom_miss_leaves_uom_id_null(self, db, svc, seeded):
        body = _grn()
        body.grn_lines[0].uom = "NO-SUCH-UOM"
        res = svc.ingest(body)
        assert res.created == 1  # uom is best-effort, not a hard requirement
        assert db.query(PickingLine).one().uom_id is None


class TestDryRun:
    def test_dry_run_writes_nothing(self, db, svc, seeded):
        res = svc.ingest(_grn(), dry_run=True)
        assert res.created == 1  # verdict says it WOULD create
        assert db.query(PickingHeader).count() == 0
        assert db.query(PickingLine).count() == 0
        assert db.query(IntegrationReference).count() == 0

    def test_dry_run_update_reports_diff_and_writes_nothing(self, db, svc, seeded):
        svc.ingest(_grn())
        # Commit the base row so it survives the dry_run's rollback, mirroring
        # production where the create is a separate committed request. (create_savepoint
        # mode: this commit lands on a savepoint the outer fixture rollback still discards.)
        db.commit()
        res = svc.ingest(_grn(picking_number="GRN-RENAMED"), dry_run=True)
        assert res.updated == 1
        rec = res.records[0]
        assert rec.diff is not None
        assert rec.diff["picking_number"] == {"current": "GRN-0012", "incoming": "GRN-RENAMED"}
        # the live row was not renamed by the preview
        assert db.query(PickingHeader).one().picking_number == "GRN-0012"
