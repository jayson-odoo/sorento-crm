"""A2 - stock + sellable (AC-903, AC-904, AC-904b).

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A;
`documentation/plans/chatbot/chatbot-growth-r1-acceptance-criteria.md` section A.

`sellable = on_hand - open_so_qty`, computed only from `sales_order_lines`
(never `orders`/`order_lines` - AutoCount deducts stock at DO creation, so an
open DO is already reflected in `on_hand` and must not be subtracted a second
time, AC-904b). Off the wire unless `include_sellable=true` is asked
(`GET /api/v1/inventory/stock/balance`), so a caller that never asks gets a
byte-identical response (AC-903).

Postgres only, blank schema, every row seeded here (CI's database has none).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.api.v1.inventory.stock import _with_sellable
from app.models.inventory import Stock, Warehouse
from app.models.order import Order, OrderLine, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.inventory_service import StockService
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _warehouse(db, code: str | None = None):
    """A warehouse, with a UNIQUE code by default.

    `uq_warehouses_company_warehouse_code` means a test that wants TWO warehouses cannot
    reuse a fixed code, and the per-warehouse split tests want two.
    """
    wh_id = str(uuid.uuid4())
    db.add(
        Warehouse(
            id=wh_id,
            warehouse_code=code or unique_code("W"),
            warehouse_name="BUKIT RAJA",
            is_active=True,
        )
    )
    db.flush()
    return wh_id


def _product(db, code):
    prod_id = str(uuid.uuid4())
    cat_id = str(uuid.uuid4())
    uom_id = str(uuid.uuid4())
    db.add(ProductCategory(id=cat_id, category_code=unique_code("C"), category_name=code))
    db.add(UnitOfMeasure(id=uom_id, uom_code=unique_code("U"), uom_name="Each"))
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


def _stock(db, prod_id, wh_id, qty):
    row = Stock(
        id=str(uuid.uuid4()),
        product_id=prod_id,
        warehouse_id=wh_id,
        quantity_on_hand=qty,
        quantity_reserved=0,
        quantity_damaged=0,
    )
    db.add(row)
    db.flush()
    return row


def _so_line(db, prod_id, wh_id, *, ordered, delivered, status="open"):
    so_id = str(uuid.uuid4())
    db.add(SalesOrder(id=so_id, so_number=unique_code("SO")))
    db.flush()
    db.add(
        SalesOrderLine(
            id=str(uuid.uuid4()),
            sales_order_id=so_id,
            product_id=prod_id,
            warehouse_id=wh_id,
            qty_ordered=ordered,
            qty_delivered=delivered,
            line_status=status,
        )
    )


# --------------------------------------------------------------------- service


def test_open_so_qty_sums_only_open_positive_delta_lines(db):
    prod_id = _product(db, "SRTWC8517")
    wh_id = _warehouse(db)
    _so_line(db, prod_id, wh_id, ordered=10, delivered=3)  # open, +7
    _so_line(db, prod_id, wh_id, ordered=5, delivered=5)  # open but fully delivered -> excluded
    _so_line(db, prod_id, wh_id, ordered=8, delivered=0, status="closed")  # not open -> excluded
    db.commit()

    result = StockService(db).open_so_qty_by_product([prod_id])
    assert result == {prod_id: 7}


def test_open_so_qty_empty_for_product_with_no_lines(db):
    prod_id = _product(db, "NOLINES")
    db.commit()
    assert StockService(db).open_so_qty_by_product([prod_id]) == {}


def test_open_do_does_not_affect_open_so_qty(db):
    """AC-904b: an open DO (created, not delivered) must never feed sellable a
    second time - `open_so_qty_by_product` reads ONLY `sales_order_lines`."""
    prod_id = _product(db, "SRTWC8517-DO")
    wh_id = _warehouse(db)
    _so_line(db, prod_id, wh_id, ordered=10, delivered=3)  # open SO, +7

    order_id = str(uuid.uuid4())
    db.add(Order(id=order_id, order_number=unique_code("DO")))
    db.flush()
    db.add(
        OrderLine(
            id=str(uuid.uuid4()),
            order_id=order_id,
            product_id=prod_id,
            warehouse_id=wh_id,
            quantity=4,
        )
    )
    db.commit()

    result = StockService(db).open_so_qty_by_product([prod_id])
    assert result == {prod_id: 7}  # the open DO line contributes nothing


# --------------------------------------------------------------------- route helper


def test_with_sellable_attaches_open_so_and_sellable_to_detailed_rows(db):
    prod_id = _product(db, "SRTWC8517-SELL")
    wh_id = _warehouse(db)
    row = _stock(db, prod_id, wh_id, 20)
    _so_line(db, prod_id, wh_id, ordered=10, delivered=3)  # open_so_qty = 7
    db.commit()

    result = {"data": [row], "pagination": {"total": 1, "page": 1, "limit": 50}}
    resp = _with_sellable(StockService(db), result)
    body = __import__("json").loads(resp.body)
    entry = body["data"][0]
    assert entry["open_so_qty"] == 7
    assert entry["sellable"] == 13  # 20 - 7


def test_with_sellable_renders_negative_when_oversold(db):
    prod_id = _product(db, "SRTWC8517-OVERSOLD")
    wh_id = _warehouse(db)
    row = _stock(db, prod_id, wh_id, 5)
    _so_line(db, prod_id, wh_id, ordered=10, delivered=0)  # open_so_qty = 10
    db.commit()

    result = {"data": [row], "pagination": {"total": 1, "page": 1, "limit": 50}}
    resp = _with_sellable(StockService(db), result)
    body = __import__("json").loads(resp.body)
    entry = body["data"][0]
    assert entry["open_so_qty"] == 10
    assert entry["sellable"] == -5  # oversold by 5; the chatbot presenter renders "0 (oversold by 5)"


def test_with_sellable_attaches_to_stock_summary_entries(db):
    """`compact` visibility mode: entries come back as plain dicts under `stock_summary`."""
    prod_id = _product(db, "SRTWC8517-COMPACT")
    wh_id = _warehouse(db)
    _so_line(db, prod_id, wh_id, ordered=10, delivered=6)  # open_so_qty = 4
    db.commit()

    result = {
        "data": [],
        "pagination": {"total": 0, "page": 1, "limit": 50},
        "stock_summary": [
            {
                "product_id": prod_id,
                "product_code": "SRTWC8517-COMPACT",
                "product_name": "SRTWC8517-COMPACT",
                "total_on_hand": 12,
                "locations": [],
                "flags": {},
            }
        ],
    }
    resp = _with_sellable(StockService(db), result)
    body = __import__("json").loads(resp.body)
    entry = body["stock_summary"][0]
    assert entry["open_so_qty"] == 4
    assert entry["sellable"] == 8  # 12 - 4


# ------------------------------------------------- should-fix 5: the per-warehouse split


def test_open_so_splits_by_warehouse_and_keeps_the_unlocated_remainder(db):
    """`open_so_qty_by_product_warehouse` returns the per-pair map AND the lines that
    carry no `warehouse_id`, separately - the plan's split, which the first cut skipped."""
    prod_id = _product(db, "SRTWC8517-SPLIT")
    wh_a = _warehouse(db)
    wh_b = _warehouse(db)
    _so_line(db, prod_id, wh_a, ordered=30, delivered=0)  # 30 in A
    _so_line(db, prod_id, wh_b, ordered=12, delivered=2)  # 10 in B
    _so_line(db, prod_id, None, ordered=5, delivered=0)   # 5 with no warehouse
    db.commit()

    by_pair, unlocated = StockService(db).open_so_qty_by_product_warehouse([prod_id])
    assert by_pair[(prod_id, wh_a)] == 30
    assert by_pair[(prod_id, wh_b)] == 10
    assert unlocated == {prod_id: 5}
    # The product TOTAL is still the sum of all three, which is what the summary row uses.
    assert StockService(db).open_so_qty_by_product([prod_id]) == {prod_id: 45}


def test_each_warehouse_row_subtracts_only_its_own_open_so(db):
    """The defect this closes: the product-wide open SO was subtracted from EVERY
    per-warehouse row, so a product with 30 open SO in warehouse A read as 30 unsellable in
    warehouse B as well - "0 (oversold by 10)" against a warehouse holding 20 and owing
    nothing."""
    prod_id = _product(db, "SRTWC8517-PERWH")
    wh_a = _warehouse(db)
    wh_b = _warehouse(db)
    row_a = _stock(db, prod_id, wh_a, 100)
    row_b = _stock(db, prod_id, wh_b, 20)
    _so_line(db, prod_id, wh_a, ordered=30, delivered=0)  # all of it is warehouse A's
    db.commit()

    result = {"data": [row_a, row_b], "pagination": {"total": 2, "page": 1, "limit": 50}}
    resp = _with_sellable(StockService(db), result)
    body = __import__("json").loads(resp.body)
    a, b = body["data"][0], body["data"][1]
    assert (a["open_so_qty"], a["sellable"]) == (30, 70)
    assert (b["open_so_qty"], b["sellable"]) == (0, 20), (
        "warehouse B owes nothing and must not carry warehouse A's open SO"
    )


def test_the_summary_row_still_carries_the_product_total(db):
    """The other half: the SUMMARY row is the product, so it takes the product total -
    per-warehouse quantities plus the lines that name no warehouse."""
    prod_id = _product(db, "SRTWC8517-TOTAL")
    wh_a = _warehouse(db)
    _so_line(db, prod_id, wh_a, ordered=30, delivered=0)
    _so_line(db, prod_id, None, ordered=5, delivered=0)
    db.commit()

    result = {
        "data": [],
        "pagination": {"total": 0, "page": 1, "limit": 50},
        "stock_summary": [
            {
                "product_id": prod_id,
                "product_code": "SRTWC8517-TOTAL",
                "product_name": "SRTWC8517-TOTAL",
                "total_on_hand": 100,
                "locations": [],
                "flags": {},
            }
        ],
    }
    resp = _with_sellable(StockService(db), result)
    body = __import__("json").loads(resp.body)
    entry = body["stock_summary"][0]
    assert entry["open_so_qty"] == 35
    assert entry["sellable"] == 65


def test_with_sellable_adds_a_product_total_summary_to_detailed_rows_beyond_the_page(db):
    """Review round 2, S2: the detailed payload now carries `stock_summary` per product,
    with `total_on_hand` summed over EVERY warehouse row - the rows may be one page of
    many. The presenter reads the line from here, never from a page sum."""
    prod_id = _product(db, "SRTWC286-SH")
    wh_a, wh_b, wh_c = _warehouse(db), _warehouse(db), _warehouse(db)
    _stock(db, prod_id, wh_a, 10)
    _stock(db, prod_id, wh_b, 20)
    _stock(db, prod_id, wh_c, 30)
    _so_line(db, prod_id, wh_a, ordered=8, delivered=0)  # open SO 8
    db.commit()

    full = StockService(db).list_stock(product_ids=[prod_id], page=1, limit=50)
    page = StockService(db).list_stock(product_ids=[prod_id], page=1, limit=1)  # ONE warehouse row
    assert len(page["data"]) == 1
    body = _with_sellable(StockService(db), page).body
    import json

    body = json.loads(body)
    assert len(body["data"]) == 1
    assert body["stock_summary"] == [{
        "product_id": prod_id, "product_code": "SRTWC286-SH",
        "product_name": body["stock_summary"][0]["product_name"],
        "total_on_hand": 60, "open_so_qty": 8, "sellable": 52,
    }]
    assert json.loads(_with_sellable(StockService(db), full).body)["stock_summary"][0]["total_on_hand"] == 60


def test_on_hand_total_by_product_is_company_scoped(db):
    from app.models.base import set_company_scope
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._mc_lookup_seed import MOCHA_ID, seed_mocha

    seed_mocha(db)
    prod_id = _product(db, "SRTWC286-SCOPE")
    wh = _warehouse(db)
    _stock(db, prod_id, wh, 10)
    other = _stock(db, prod_id, _warehouse(db), 90)
    other.company_id = MOCHA_ID
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    assert StockService(db).on_hand_total_by_product([prod_id]) == {prod_id: 10}
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
    assert StockService(db).on_hand_total_by_product([prod_id]) == {prod_id: 100}
