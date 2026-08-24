"""C1 regression - StockLedger bulk insert must NOT leak to the DB-default company.

``InventoryService.bulk_import_stock`` writes its stock-ledger rows via
``bulk_insert_mappings``, which BYPASSES the ``before_insert`` auto-stamp. Without
an explicit stamp those rows fall to migration 306's DB DEFAULT (Sorento), so a
Mocha-scoped stock import would silently write Mocha's ledger under Sorento - a
cross-company leak that the sqlite unit suite cannot catch (no DB default).

This test drives the real service path under a throwaway Mocha scope on the live
Postgres dev DB inside an always-rolled-back savepoint (marker rows only, per the
"tests once wiped the dev DB" rule) and asserts every emitted ``stock_ledger`` row
carries ``company_id == Mocha``.

Before the C1 fix this FAILS (rows land under the Sorento default); after it PASSES.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.company import Company
from app.services.company_scope import register_company_scope_listeners

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    session.begin_nested()
    session.commit = session.flush  # type: ignore[method-assign]
    try:
        yield session
    finally:
        try:
            session.rollback()
        finally:
            session.close()


@pytest.fixture()
def mocha(db: Session) -> str:
    suffix = uuid.uuid4().hex[:8]
    c = Company(id=str(uuid.uuid4()), name=f"ZZLED Mocha {suffix}", code=f"ZLM{suffix}")
    db.add(c)
    db.flush()
    return c.id


def _seed_stock(db: Session, company_id: str, suffix: str) -> tuple[str, str]:
    """Seed a Mocha category/uom/product/warehouse + one stock row (qty 10).
    Returns (product_code, warehouse_code) so the import can match by code."""
    cat_id, uom_id, prod_id, wh_id, stock_id = (str(uuid.uuid4()) for _ in range(5))
    product_code = f"ZZLEDPROD{suffix}"
    warehouse_code = f"ZZLEDWH{suffix}"
    db.execute(
        text(
            "INSERT INTO product_categories (id, category_code, category_name, is_active, company_id, created_at) "
            "VALUES (:id, :code, :name, true, :cid, now())"
        ),
        {"id": cat_id, "code": f"ZZLED-CAT-{suffix}", "name": f"zzled cat {suffix}", "cid": company_id},
    )
    db.execute(
        text(
            "INSERT INTO units_of_measure (id, uom_code, uom_name, is_active, company_id, created_at) "
            "VALUES (:id, :code, :name, true, :cid, now())"
        ),
        {"id": uom_id, "code": f"ZZLED-UOM-{suffix}", "name": f"zzled uom {suffix}", "cid": company_id},
    )
    db.execute(
        text(
            "INSERT INTO products (id, product_code, product_name, category_id, base_uom_id, list_price, "
            " currency, is_active, has_serial_tracking, has_batch_tracking, variant_link_manual, "
            " is_discontinued, company_id, created_at) "
            "VALUES (:id, :code, :name, :cat, :uom, 100, 'MYR', true, false, false, false, false, :cid, now())"
        ),
        {"id": prod_id, "code": product_code, "name": product_code, "cat": cat_id, "uom": uom_id, "cid": company_id},
    )
    db.execute(
        text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, company_id, created_at) "
            "VALUES (:id, :code, :name, true, :cid, now())"
        ),
        {"id": wh_id, "code": warehouse_code, "name": f"zzled wh {suffix}", "cid": company_id},
    )
    db.execute(
        text(
            "INSERT INTO stock (id, product_id, warehouse_id, quantity_on_hand, quantity_reserved, "
            " quantity_damaged, synced_to_excel, company_id, created_at) "
            "VALUES (:id, :pid, :wid, 10, 0, 0, false, :cid, now())"
        ),
        {"id": stock_id, "pid": prod_id, "wid": wh_id, "cid": company_id},
    )
    db.flush()
    return product_code, warehouse_code


def test_bulk_import_stock_ledger_stamps_active_company(db, mocha):
    from app.services.inventory_service import StockService

    suffix = uuid.uuid4().hex[:8]
    product_code, warehouse_code = _seed_stock(db, mocha, suffix)

    # Change on-hand 10 -> 25 so the update path emits a ledger entry.
    stock_rows = [
        {"Item Code": product_code, "Warehouse Code": warehouse_code, "Quantity": 25}
    ]

    with company_scope(db, frozenset({mocha})):
        result = StockService(db).bulk_import_stock(stock_rows, user_id=None)

    # The import must have produced exactly one ledger row for our Mocha product,
    # stamped with Mocha - NOT the Sorento DB default.
    rows = db.execute(
        text(
            "SELECT sl.company_id, sl.transaction_type "
            "FROM stock_ledger sl JOIN products p ON p.id = sl.product_id "
            "WHERE p.product_code = :code"
        ),
        {"code": product_code},
    ).fetchall()

    assert result.get("updated", 0) >= 1, result
    assert len(rows) == 1, f"expected one ledger row, got {rows}"
    assert str(rows[0][0]) == mocha, (
        f"stock_ledger leaked to {rows[0][0]} instead of Mocha {mocha}"
    )
    assert str(rows[0][0]) != SORENTO
