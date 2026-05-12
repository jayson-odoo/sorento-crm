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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.audit import AuditLog
from app.models.inventory import Stock, StockLedger, Warehouse
from app.models.lookup import LookupBinding, LookupOption, LookupSet
from app.models.product import Product
from app.services import inventory_service as inventory_service_mod
from app.services.inventory_service import StockService


@pytest.fixture(autouse=True)
def _silence_import_log(monkeypatch):
    """ImportLog uses JSONB so we can't create that table on SQLite — skip it.

    bulk_import_stock already catches the failure, but the broken commit puts
    the test session in PendingRollback state. Replace the call with a no-op so
    we can keep querying the session after the import.
    """

    class _Noop:
        def __init__(self, *_a, **_kw):
            pass

        def create_import_log(self, *args, **kwargs):
            return None

    monkeypatch.setattr(inventory_service_mod, "ImportLogService", _Noop)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Warehouse.__table__,
            Product.__table__,
            Stock.__table__,
            StockLedger.__table__,
            LookupSet.__table__,
            LookupOption.__table__,
            LookupBinding.__table__,
            AuditLog.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


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
    prod_id = str(uuid.uuid4())
    db.add(
        Product(
            id=prod_id,
            product_code=f"SKU-{code_suffix}",
            product_name=f"Product {code_suffix}",
            category_id=str(uuid.uuid4()),
            base_uom_id=str(uuid.uuid4()),
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
        user_id="user-1",
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
        user_id="user-1",
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
        user_id="user-1",
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
