"""Stock-balance default ordering.

With no explicit `sort`, list_stock must return a deterministic order:
product_code asc, then warehouse_name asc. Previously the query had no
ORDER BY at all, so Postgres returned arbitrary heap order (jumbled MCP
answers, unstable offset pagination).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.inventory import Stock, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.inventory_service import StockService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _warehouse(db, code, name):
    wh_id = str(uuid.uuid4())
    db.add(Warehouse(id=wh_id, warehouse_code=code, warehouse_name=name, is_active=True))
    db.flush()
    return wh_id


def _product(db, code):
    prod_id = str(uuid.uuid4())
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
    return prod_id


def _stock(db, prod_id, wh_id, qty=1):
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


def test_no_sort_orders_by_product_code_then_warehouse(db):
    wh_z = _warehouse(db, "ZWH", "ZULU")
    wh_a = _warehouse(db, "AWH", "ALPHA")
    # Insert deliberately out of order so heap order != expected order.
    p_c = _product(db, "CODE-C")
    p_a = _product(db, "CODE-A")
    p_b = _product(db, "CODE-B")
    _stock(db, p_c, wh_a)
    _stock(db, p_b, wh_z)
    _stock(db, p_b, wh_a)
    _stock(db, p_a, wh_z)
    db.commit()

    rows = StockService(db).list_stock(limit=50)["data"]
    ordered = [(r.product.product_code, r.warehouse.warehouse_name) for r in rows]
    assert ordered == [
        ("CODE-A", "ZULU"),
        ("CODE-B", "ALPHA"),
        ("CODE-B", "ZULU"),
        ("CODE-C", "ALPHA"),
    ]


def test_product_ids_filter_keeps_default_order(db):
    wh = _warehouse(db, "AWH", "ALPHA")
    p_b = _product(db, "CODE-B")
    p_a = _product(db, "CODE-A")
    p_c = _product(db, "CODE-C")
    for pid in (p_b, p_c, p_a):
        _stock(db, pid, wh)
    db.commit()

    # product_ids passed in arbitrary order; result still product_code asc.
    rows = StockService(db).list_stock(limit=50, product_ids=[p_c, p_a, p_b])["data"]
    assert [r.product.product_code for r in rows] == ["CODE-A", "CODE-B", "CODE-C"]


def test_explicit_sort_still_wins(db):
    wh = _warehouse(db, "AWH", "ALPHA")
    p_a = _product(db, "CODE-A")
    p_b = _product(db, "CODE-B")
    _stock(db, p_a, wh)
    _stock(db, p_b, wh)
    db.commit()

    rows = StockService(db).list_stock(limit=50, sort="product_code", dir="desc")["data"]
    assert [r.product.product_code for r in rows] == ["CODE-B", "CODE-A"]
