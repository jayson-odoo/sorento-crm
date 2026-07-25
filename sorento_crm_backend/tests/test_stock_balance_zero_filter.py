"""Stock-balance `exclude_zero_system_adjustment` filter.

When enabled (the MCP always sends it), a stock row whose on-hand is 0 ONLY
because its most-recent ledger movement was a SYSTEM_ADJUSTMENT (e.g. "missing
from full stock take") is hidden. A genuine 0 (last movement an import/sale, or
no ledger at all) and any non-zero row are still returned.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.models.inventory import Stock, StockLedger, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.inventory_service import StockService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _warehouse(db, active=True):
    wh_id = str(uuid.uuid4())
    db.add(Warehouse(id=wh_id, warehouse_code="BRW", warehouse_name="BUKIT RAJA", is_active=active))
    db.flush()
    return wh_id


def _stock(db, wh_id, code, qty):
    prod_id = str(uuid.uuid4())
    # category_id / base_uom_id are real, NOT NULL foreign keys -- Postgres
    # enforces them, so the parent rows must exist (sqlite did not care).
    cat_id = str(uuid.uuid4())
    uom_id = str(uuid.uuid4())
    db.add(ProductCategory(id=cat_id, category_code=f"C{uuid.uuid4().hex[:8]}", category_name=code))
    db.add(UnitOfMeasure(id=uom_id, uom_code=f"U{uuid.uuid4().hex[:8]}", uom_name="Each"))
    db.flush()
    db.add(
        Product(
            id=prod_id,
            product_code=code,
            product_name=code,
            category_id=cat_id,
            base_uom_id=uom_id,
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
    return prod_id


def _ledger(db, prod_id, wh_id, txn, new_qty, when):
    db.add(
        StockLedger(
            id=str(uuid.uuid4()),
            product_id=prod_id,
            warehouse_id=wh_id,
            transaction_type=txn,
            quantity_change=new_qty,
            previous_quantity=0,
            new_quantity=new_qty,
            created_at=when,
        )
    )


def _seed(db):
    wh = _warehouse(db)
    # 1) zero, latest movement = SYSTEM_ADJUSTMENT  -> hidden when flag on
    p_sa = _stock(db, wh, "ZERO-SYSADJ", 0)
    _ledger(db, p_sa, wh, "BULK_IMPORT", 7, datetime(2026, 6, 1))
    _ledger(db, p_sa, wh, "SYSTEM_ADJUSTMENT", 0, datetime(2026, 6, 12))
    # 2) zero, latest movement = BULK_IMPORT  -> genuine 0, shown
    p_imp = _stock(db, wh, "ZERO-IMPORT", 0)
    _ledger(db, p_imp, wh, "SYSTEM_ADJUSTMENT", 3, datetime(2026, 6, 1))
    _ledger(db, p_imp, wh, "BULK_IMPORT", 0, datetime(2026, 6, 12))
    # 3) zero, no ledger at all  -> shown
    _stock(db, wh, "ZERO-NOLEDGER", 0)
    # 4) non-zero, latest movement = SYSTEM_ADJUSTMENT  -> shown (filter targets zeros only)
    p_nz = _stock(db, wh, "NONZERO-SYSADJ", 5)
    _ledger(db, p_nz, wh, "SYSTEM_ADJUSTMENT", 5, datetime(2026, 6, 12))
    db.commit()
    return wh


def _codes(result):
    return {row.product.product_code for row in result["data"]}


def test_flag_off_returns_every_row(db):
    _seed(db)
    codes = _codes(StockService(db).list_stock(limit=50, exclude_zero_system_adjustment=False))
    assert codes == {"ZERO-SYSADJ", "ZERO-IMPORT", "ZERO-NOLEDGER", "NONZERO-SYSADJ"}


def test_flag_on_hides_only_system_adjustment_zero(db):
    _seed(db)
    result = StockService(db).list_stock(limit=50, exclude_zero_system_adjustment=True)
    codes = _codes(result)
    assert "ZERO-SYSADJ" not in codes  # zeroed by system adjustment -> hidden
    assert codes == {"ZERO-IMPORT", "ZERO-NOLEDGER", "NONZERO-SYSADJ"}
    assert result["pagination"]["total"] == 3  # filtered before pagination count
