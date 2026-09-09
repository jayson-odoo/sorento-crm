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
from app.models.company import Company
from app.models.inventory import Stock, Warehouse
from app.models.order import Order, OrderLine, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.inventory_service import StockService
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _warehouse(db, code: str | None = None, company_id: str | None = None):
    """A warehouse, with a UNIQUE code by default.

    `uq_warehouses_company_warehouse_code` means a test that wants TWO warehouses cannot
    reuse a fixed code, and the per-warehouse split tests want two.
    """
    wh_id = str(uuid.uuid4())
    extra = {"company_id": company_id} if company_id else {}
    db.add(
        Warehouse(
            id=wh_id,
            warehouse_code=code or unique_code("W"),
            warehouse_name="BUKIT RAJA",
            is_active=True,
            **extra,
        )
    )
    db.flush()
    return wh_id


def _product(db, code, company_id: str | None = None):
    prod_id = str(uuid.uuid4())
    cat_id = str(uuid.uuid4())
    uom_id = str(uuid.uuid4())
    # The feed-flag tests widen company scope to two companies at once, which makes
    # an un-stamped owned insert AMBIGUOUS (raises) - so company_id is threaded onto
    # every owned row the product needs, not just Product itself.
    extra = {"company_id": company_id} if company_id else {}
    db.add(ProductCategory(id=cat_id, category_code=unique_code("C"), category_name=code, **extra))
    db.add(UnitOfMeasure(id=uom_id, uom_code=unique_code("U"), uom_name="Each", **extra))
    db.flush()
    db.add(
        Product(
            id=prod_id,
            product_code=code,
            product_name=code,
            category_id=cat_id,
            base_uom_id=uom_id,
            list_price=0,
            **extra,
        )
    )
    db.flush()
    return prod_id


def _stock(db, prod_id, wh_id, qty, company_id: str | None = None):
    extra = {"company_id": company_id} if company_id else {}
    row = Stock(
        id=str(uuid.uuid4()),
        product_id=prod_id,
        warehouse_id=wh_id,
        quantity_on_hand=qty,
        quantity_reserved=0,
        quantity_damaged=0,
        **extra,
    )
    db.add(row)
    db.flush()
    return row


def _so_line(db, prod_id, wh_id, *, ordered, delivered, status="open", company_id: str | None = None):
    extra = {"company_id": company_id} if company_id else {}
    so_id = str(uuid.uuid4())
    db.add(SalesOrder(id=so_id, so_number=unique_code("SO"), **extra))
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
            **extra,
        )
    )


def _company(db, so_feed_live: bool) -> str:
    """A second company (PLAN company-so-feed-flag), feed on/off per the flag."""
    company_id = str(uuid.uuid4())
    db.add(
        Company(
            id=company_id,
            name=f"ZZT Co {company_id[:8]}",
            code=unique_code("CO"),
            is_active=True,
            so_feed_live=so_feed_live,
        )
    )
    db.flush()
    return company_id


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


def test_with_sellable_attaches_each_compact_locations_own_open_so(db):
    """D1: the compact block's warehouse lines carry their own open SO; the product total
    on the entry keeps the unlocated remainder."""
    import json

    prod_id = _product(db, "SRTWC286-CMP")
    wh_a, wh_b = _warehouse(db), _warehouse(db)
    _stock(db, prod_id, wh_a, 10)
    _stock(db, prod_id, wh_b, 41)
    _so_line(db, prod_id, wh_a, ordered=12, delivered=0)   # 12 at A
    _so_line(db, prod_id, wh_b, ordered=20, delivered=0)   # 20 at B
    _so_line(db, prod_id, None, ordered=4, delivered=0)    # 4 unlocated -> the Total's O/S only
    db.commit()
    from app.models.inventory import Warehouse

    codes = {w.id: w.warehouse_code for w in db.query(Warehouse).filter(Warehouse.id.in_([wh_a, wh_b]))}
    result = {
        "data": [],
        "pagination": {"total": 1, "page": 1, "limit": 50},
        "stock_summary": [{
            "product_id": prod_id, "product_code": "SRTWC286-CMP", "product_name": "x", "total_on_hand": 51,
            "locations": [{"warehouse_code": codes[wh_a], "quantity_on_hand": 10},
                          {"warehouse_code": codes[wh_b], "quantity_on_hand": 41}],
            "flags": {},
        }],
    }
    body = json.loads(_with_sellable(StockService(db), result).body)
    entry = body["stock_summary"][0]
    assert entry["open_so_qty"] == 36 and entry["sellable"] == 15
    assert [loc["open_so_qty"] for loc in entry["locations"]] == [12, 20]


# ------------------------------------------ company SO feed gate (PLAN company-so-feed-flag)


def test_no_feed_company_rows_carry_neither_open_so_nor_sellable(db):
    """AC-2: a detailed row whose company has `so_feed_live=false` carries NEITHER
    `open_so_qty` NOR `sellable`; a feed-on company's row is unchanged."""
    from app.models.base import set_company_scope
    from app.services.company_scope import DEFAULT_COMPANY_ID

    off_id = _company(db, so_feed_live=False)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, off_id}))

    off_prod = _product(db, "NOFEED-OFF", company_id=off_id)
    on_prod = _product(db, "NOFEED-ON", company_id=DEFAULT_COMPANY_ID)
    wh_off = _warehouse(db, company_id=off_id)
    wh_on = _warehouse(db, company_id=DEFAULT_COMPANY_ID)
    row_off = _stock(db, off_prod, wh_off, 20, company_id=off_id)
    row_on = _stock(db, on_prod, wh_on, 20, company_id=DEFAULT_COMPANY_ID)
    _so_line(db, off_prod, wh_off, ordered=10, delivered=3, company_id=off_id)  # open_so 7
    _so_line(db, on_prod, wh_on, ordered=10, delivered=3, company_id=DEFAULT_COMPANY_ID)  # open_so 7
    db.commit()

    result = {"data": [row_off, row_on], "pagination": {"total": 2, "page": 1, "limit": 50}}
    resp = _with_sellable(StockService(db), result)
    body = __import__("json").loads(resp.body)
    off_entry, on_entry = body["data"][0], body["data"][1]
    assert "open_so_qty" not in off_entry and "sellable" not in off_entry
    assert on_entry["open_so_qty"] == 7 and on_entry["sellable"] == 13


def test_no_feed_company_compact_entries_and_locations_are_bare(db):
    """AC-3: compact `stock_summary` entry + its location lines for a no-feed
    company carry neither `open_so_qty` nor `sellable`; the feed-on entry is
    unchanged (D1 shape, `test_with_sellable_attaches_each_compact_locations_own_open_so`)."""
    from app.models.base import set_company_scope
    from app.services.company_scope import DEFAULT_COMPANY_ID

    off_id = _company(db, so_feed_live=False)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, off_id}))

    off_prod = _product(db, "NOFEED-CMP-OFF", company_id=off_id)
    on_prod = _product(db, "NOFEED-CMP-ON", company_id=DEFAULT_COMPANY_ID)
    wh_off = _warehouse(db, company_id=off_id)
    wh_on = _warehouse(db, company_id=DEFAULT_COMPANY_ID)
    _so_line(db, off_prod, wh_off, ordered=10, delivered=6, company_id=off_id)  # open_so 4
    _so_line(db, on_prod, wh_on, ordered=10, delivered=6, company_id=DEFAULT_COMPANY_ID)  # open_so 4
    db.commit()

    codes = {
        w.id: w.warehouse_code
        for w in db.query(Warehouse).filter(Warehouse.id.in_([wh_off, wh_on]))
    }
    result = {
        "data": [],
        "pagination": {"total": 2, "page": 1, "limit": 50},
        "stock_summary": [
            {
                "product_id": off_prod, "product_code": "NOFEED-CMP-OFF", "product_name": "x",
                "total_on_hand": 12,
                "locations": [{"warehouse_code": codes[wh_off], "quantity_on_hand": 12}],
                "flags": {},
            },
            {
                "product_id": on_prod, "product_code": "NOFEED-CMP-ON", "product_name": "x",
                "total_on_hand": 12,
                "locations": [{"warehouse_code": codes[wh_on], "quantity_on_hand": 12}],
                "flags": {},
            },
        ],
    }
    body = __import__("json").loads(_with_sellable(StockService(db), result).body)
    off_entry, on_entry = body["stock_summary"][0], body["stock_summary"][1]
    assert "open_so_qty" not in off_entry and "sellable" not in off_entry
    assert "open_so_qty" not in off_entry["locations"][0]
    assert on_entry["open_so_qty"] == 4 and on_entry["sellable"] == 8
    assert on_entry["locations"][0]["open_so_qty"] == 4


def test_no_feed_company_synthesised_summary_is_bare(db):
    """AC-4: detailed mode's synthesised per-product `stock_summary` (no backend
    summary on the payload) omits `open_so_qty`/`sellable` for a no-feed product
    while still emitting the entry (product_id/code/name/total_on_hand); a
    feed-on product keeps both."""
    from app.models.base import set_company_scope
    from app.services.company_scope import DEFAULT_COMPANY_ID

    off_id = _company(db, so_feed_live=False)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, off_id}))

    off_prod = _product(db, "NOFEED-SYN-OFF", company_id=off_id)
    on_prod = _product(db, "NOFEED-SYN-ON", company_id=DEFAULT_COMPANY_ID)
    wh_off = _warehouse(db, company_id=off_id)
    wh_on = _warehouse(db, company_id=DEFAULT_COMPANY_ID)
    row_off = _stock(db, off_prod, wh_off, 30, company_id=off_id)
    row_on = _stock(db, on_prod, wh_on, 30, company_id=DEFAULT_COMPANY_ID)
    _so_line(db, off_prod, wh_off, ordered=10, delivered=0, company_id=off_id)  # open_so 10
    _so_line(db, on_prod, wh_on, ordered=10, delivered=0, company_id=DEFAULT_COMPANY_ID)  # open_so 10
    db.commit()

    result = {"data": [row_off, row_on], "pagination": {"total": 2, "page": 1, "limit": 50}}
    body = __import__("json").loads(_with_sellable(StockService(db), result).body)
    summary = {e["product_id"]: e for e in body["stock_summary"]}
    off_entry, on_entry = summary[off_prod], summary[on_prod]
    assert off_entry["total_on_hand"] == 30
    assert "open_so_qty" not in off_entry and "sellable" not in off_entry
    assert on_entry["total_on_hand"] == 30
    assert on_entry["open_so_qty"] == 10 and on_entry["sellable"] == 20


def test_stock_service_company_helpers(db):
    """`companies_without_so_feed` / `company_id_by_product`: empty input is a
    no-op, mixed input resolves each product/company correctly."""
    from app.models.base import set_company_scope
    from app.services.company_scope import DEFAULT_COMPANY_ID

    service = StockService(db)
    assert service.companies_without_so_feed([]) == set()
    assert service.company_id_by_product([]) == {}

    off_id = _company(db, so_feed_live=False)
    on_id = _company(db, so_feed_live=True)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, off_id, on_id}))

    off_prod = _product(db, "HLPR-OFF", company_id=off_id)
    on_prod = _product(db, "HLPR-ON", company_id=on_id)
    db.commit()

    assert service.companies_without_so_feed([off_id, on_id]) == {off_id}
    assert service.company_id_by_product([off_prod, on_prod]) == {
        off_prod: off_id,
        on_prod: on_id,
    }
