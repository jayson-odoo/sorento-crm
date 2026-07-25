"""Full-snapshot stock import behavior.

Verifies:
  * Active-warehouse stock rows missing from the upload get zeroed and a
    SYSTEM_ADJUSTMENT ledger entry.
  * Inactive-warehouse stock rows are NOT touched.
  * validate_only does not mutate data and reports the would-be zero count.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.inventory import Stock, StockLedger, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.inventory_service import StockService
from tests._pg_fixture import blank_session


# The old sqlite fixture stubbed out ImportLogService, because ImportLog's JSONB
# columns could not be created on sqlite. The real schema has the table, so the
# import log is now exercised for real rather than skipped.
@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _seed(db, *, active_wh: bool = True, qty: int = 50, code_suffix: str = "A"):
    wh_id = str(uuid.uuid4())
    db.add(
        Warehouse(
            id=wh_id,
            warehouse_code=f"WH-{code_suffix}",
            warehouse_name=f"WH {code_suffix}",
            is_active=active_wh,
        )
    )
    # category_id and base_uom_id are real foreign keys, so the parent rows must
    # exist. The sqlite fixture invented loose UUIDs for both, which only worked
    # because sqlite did not enforce the constraint.
    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=f"CAT-{code_suffix}",
        category_name=f"Category {code_suffix}",
    )
    uom = UnitOfMeasure(
        id=str(uuid.uuid4()), uom_code=f"UOM-{code_suffix}", uom_name="Each"
    )
    db.add_all([category, uom])
    db.flush()

    prod_id = str(uuid.uuid4())
    db.add(
        Product(
            id=prod_id,
            product_code=f"SKU-{code_suffix}",
            product_name=f"Product {code_suffix}",
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=0,
        )
    )
    db.flush()
    db.add(
        Stock(
            id=str(uuid.uuid4()),
            product_id=prod_id,
            warehouse_id=wh_id,
            quantity_on_hand=qty,
            quantity_reserved=0,
            quantity_damaged=0,
        )
    )
    db.commit()
    return prod_id, wh_id


def test_missing_active_row_is_zeroed_with_system_adjustment_ledger(db):
    _, missing_wh = _seed(db, active_wh=True, qty=42, code_suffix="MISS")
    keep_prod, keep_wh = _seed(db, active_wh=True, qty=10, code_suffix="KEEP")

    service = StockService(db)
    result = service.bulk_import_stock(
        stock_data=[
            {"Item Code": "SKU-KEEP", "Location": "WH-KEEP", "Total Quantity": 10},
        ],
        user_id="717677a2-1052-5fb1-9f10-981584261561",
        validate_only=False,
    )

    assert result.get("errors") == []
    missing_row = (
        db.query(Stock)
        .filter(Stock.warehouse_id == missing_wh)
        .one()
    )
    assert missing_row.quantity_on_hand == 0

    keep_row = (
        db.query(Stock)
        .filter(Stock.warehouse_id == keep_wh)
        .one()
    )
    assert keep_row.quantity_on_hand == 10

    sysadj = (
        db.query(StockLedger)
        .filter(StockLedger.transaction_type == "SYSTEM_ADJUSTMENT")
        .all()
    )
    assert len(sysadj) == 1
    assert sysadj[0].previous_quantity == 42
    assert sysadj[0].new_quantity == 0
    assert sysadj[0].reference_type == "stock_snapshot_import"


def test_inactive_warehouse_row_is_not_zeroed(db):
    inactive_prod, inactive_wh = _seed(db, active_wh=False, qty=99, code_suffix="OFF")
    _seed(db, active_wh=True, qty=10, code_suffix="ON")

    service = StockService(db)
    result = service.bulk_import_stock(
        stock_data=[
            {"Item Code": "SKU-ON", "Location": "WH-ON", "Total Quantity": 10},
        ],
        user_id="717677a2-1052-5fb1-9f10-981584261561",
        validate_only=False,
    )

    assert result.get("errors") == []
    inactive_row = (
        db.query(Stock)
        .filter(Stock.warehouse_id == inactive_wh)
        .one()
    )
    assert inactive_row.quantity_on_hand == 99

    assert (
        db.query(StockLedger)
        .filter(StockLedger.transaction_type == "SYSTEM_ADJUSTMENT")
        .count()
        == 0
    )


def test_validate_only_reports_zero_count_without_mutating(db):
    _, missing_wh = _seed(db, active_wh=True, qty=42, code_suffix="MISS")
    _seed(db, active_wh=True, qty=10, code_suffix="KEEP")

    service = StockService(db)
    result = service.bulk_import_stock(
        stock_data=[
            {"Item Code": "SKU-KEEP", "Location": "WH-KEEP", "Total Quantity": 10},
        ],
        user_id="717677a2-1052-5fb1-9f10-981584261561",
        validate_only=True,
    )

    assert result["valid"] is True
    assert result["summary"]["would_system_adjust_to_zero"] == 1

    untouched = (
        db.query(Stock)
        .filter(Stock.warehouse_id == missing_wh)
        .one()
    )
    assert untouched.quantity_on_hand == 42

    assert db.query(StockLedger).count() == 0
