"""AutoCount ingest Slice 4 — stock-balance report -> run-history snapshots.

Report semantics, not masters: each ingest is an appended run; resolution is
best-effort (unresolvable item kept raw, not rejected); the run header carries
the annotation.

blank_session (isolated scratch schema, create_savepoint join) so raw-SQL
inserts + the annotation commit stay contained.
"""
import pytest

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.inventory import Warehouse
from app.models.stock_balance_snapshot import StockBalanceSnapshotRun, StockBalanceSnapshot
from app.services.stock_balance_ingest_service import StockBalanceIngestService
from tests._pg_fixture import blank_session


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def svc(db):
    return StockBalanceIngestService(db, integration_id=None)


@pytest.fixture()
def seeded(db):
    cat = ProductCategory(category_code="ZZT-C", category_name="C")
    uom = UnitOfMeasure(uom_code="ZZT-U", uom_name="U")
    db.add_all([cat, uom])
    db.flush()
    p = Product(product_code="ZZT-ITEM", product_name="ZZT Item",
                category_id=cat.id, base_uom_id=uom.id, list_price=0)
    wh = Warehouse(warehouse_code="HQ", warehouse_name="Headquarter")
    db.add_all([p, wh])
    db.flush()
    return {"product": p, "warehouse": wh}


def _row(item="ZZT-ITEM", loc="HQ", bal="10", **extra):
    return {"item_code": item, "location_code": loc, "uom": "PCS", "batch_no": "",
            "balance": bal, "smallest_bal_qty": bal, **extra}


class TestRunCreation:
    def test_creates_a_run_and_rows(self, db, svc, seeded):
        res = svc.ingest([_row(), _row(item="ZZT-ITEM", bal="-2")])
        assert res["created"] is True
        assert res["row_count"] == 2
        run = db.query(StockBalanceSnapshotRun).one()
        assert run.row_count == 2
        assert db.query(StockBalanceSnapshot).filter_by(run_id=run.id).count() == 2

    def test_resolves_product_and_warehouse(self, db, svc, seeded):
        res = svc.ingest([_row()])
        assert res["rows_with_product"] == 1
        row = db.query(StockBalanceSnapshot).one()
        assert row.product_id == seeded["product"].id
        assert row.warehouse_id == seeded["warehouse"].id
        assert row.item_code == "ZZT-ITEM"

    def test_signed_negative_balance_is_kept(self, db, svc, seeded):
        svc.ingest([_row(bal="-58")])
        assert str(db.query(StockBalanceSnapshot).one().balance) == "-58.0000"


class TestBestEffortResolution:
    def test_unresolvable_item_is_kept_raw_not_rejected(self, db, svc):
        # No products/warehouses seeded.
        res = svc.ingest([_row(item="PHANTOM", loc="NOWHERE")])
        assert res["created"] is True
        assert res["rows_with_product"] == 0
        assert res["rows_without_product"] == 1
        row = db.query(StockBalanceSnapshot).one()
        assert row.item_code == "PHANTOM"        # raw code preserved
        assert row.product_id is None
        assert row.warehouse_id is None

    def test_a_malformed_row_fails_the_whole_run(self, db, svc, seeded):
        res = svc.ingest([_row(), {"item_code": ""}])  # empty item_code invalid
        assert res["created"] is False
        assert db.query(StockBalanceSnapshotRun).count() == 0
        assert db.query(StockBalanceSnapshot).count() == 0


class TestRunHistory:
    def test_each_ingest_appends_a_new_run(self, db, svc, seeded):
        svc.ingest([_row(bal="10")])
        svc.ingest([_row(bal="7")])
        assert db.query(StockBalanceSnapshotRun).count() == 2
        # rows from both runs coexist (history preserved)
        assert db.query(StockBalanceSnapshot).count() == 2


class TestRunAnnotation:
    def test_run_note_persists_and_is_independent_of_new_runs(self, db, svc, seeded):
        svc.ingest([_row()])
        run = db.query(StockBalanceSnapshotRun).one()
        run.internal_note = "month-end count"
        run.follow_up = True
        db.commit()
        # A later run does not touch the earlier run's note.
        svc.ingest([_row(bal="99")])
        db.refresh(run)
        assert run.internal_note == "month-end count"
        assert run.follow_up is True
