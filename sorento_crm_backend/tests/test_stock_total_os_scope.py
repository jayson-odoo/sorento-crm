"""STOCK-TOTAL-OS-SCOPE: the chatbot stock reply's Total O/S respects warehouse visibility.

`documentation/plans/chatbot/PLAN-stock-total-os-scope.md`, owner decision 2 Oct 2026 (a):

- Total O/S = open SO qty on the warehouses the contact may see (the same
  `warehouse_criterion` the location lines are filtered by).
- Open SO lines with NO warehouse ride separately as `unassigned_open_so_qty`, only when
  > 0, and are NOT added to Total O/S.
- Open SO on a hidden warehouse is never shown or hinted.
- No contact (staff grid): unchanged, the product total.
- The open-SO aggregates are company scoped.

Postgres only, blank schema, every row seeded here (CI's database has none).
"""
from __future__ import annotations

import json
import uuid

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.api.v1.inventory.stock import _with_sellable
from app.models.access import RespondContact, StockVisibilityPolicy
from app.models.base import set_company_scope
from app.models.order import SalesOrder, SalesOrderLine
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.inventory_service import StockService

from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha, stock, warehouse
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


def _contact(db) -> RespondContact:
    row = RespondContact(
        id=unique_code("CONTACT"),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name="ZZT Contact",
    )
    db.add(row)
    db.flush()
    return row


def _policy(db, contact, *, mode, warehouse_ids=None, excluded_warehouse_ids=None):
    db.add(
        StockVisibilityPolicy(
            id=str(uuid.uuid4()),
            contact_id=contact.id,
            mode=mode,
            warehouse_ids=warehouse_ids,
            excluded_warehouse_ids=excluded_warehouse_ids,
        )
    )
    db.flush()


def _so_line(db, prod_id, wh_id, *, open_qty, company_id=DEFAULT_COMPANY_ID):
    so_id = str(uuid.uuid4())
    db.add(SalesOrder(id=so_id, so_number=unique_code("SO"), company_id=company_id))
    db.flush()
    db.add(
        SalesOrderLine(
            id=str(uuid.uuid4()),
            sales_order_id=so_id,
            product_id=prod_id,
            warehouse_id=wh_id,
            qty_ordered=open_qty,
            qty_delivered=0,
            line_status="open",
            company_id=company_id,
        )
    )
    db.flush()


def _seed(db, *, unassigned=3):
    """Visible W1 (on hand 54, open SO 10), hidden W2 (on hand 40, open SO 7), and
    `unassigned` open SO with no warehouse."""
    w1 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("VIS"))
    w2 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("HID"))
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=w1.id, on_hand=54)
    stock(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=w2.id, on_hand=40)
    _so_line(db, p.id, w1.id, open_qty=10)
    _so_line(db, p.id, w2.id, open_qty=7)
    if unassigned:
        _so_line(db, p.id, None, open_qty=unassigned)
    return w1, w2, p


def _sellable_body(db, **kwargs) -> dict:
    service = StockService(db)
    result = service.list_stock(**kwargs)
    return json.loads(_with_sellable(service, result).body)


# ------------------------------------------------------------------- compact (the reply)


@pytest.mark.parametrize("rule", ["include", "exclude"])
def test_compact_total_os_counts_only_visible_warehouses(db, rule):
    w1, w2, p = _seed(db)
    contact = _contact(db)
    if rule == "include":
        _policy(db, contact, mode="compact", warehouse_ids=[w1.id])
    else:
        _policy(db, contact, mode="compact", excluded_warehouse_ids=[w2.id])

    body = _sellable_body(db, product_ids=[p.id], contact_id=contact.id)

    entry = body["stock_summary"][0]
    assert entry["total_on_hand"] == 54
    assert entry["open_so_qty"] == 10, "hidden W2's 7 and the unassigned 3 are not Total O/S"
    assert entry["unassigned_open_so_qty"] == 3
    assert entry["sellable"] == 44
    assert [loc["open_so_qty"] for loc in entry["locations"]] == [10]


def test_compact_hidden_warehouse_open_so_is_never_in_the_body(db):
    """Neither the hidden warehouse's 7, nor any sum that includes it (17, 20), appears
    anywhere in the answer."""
    w1, w2, p = _seed(db)
    contact = _contact(db)
    _policy(db, contact, mode="compact", warehouse_ids=[w1.id])

    body = _sellable_body(db, product_ids=[p.id], contact_id=contact.id)

    def numbers(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from numbers(v)
        elif isinstance(node, list):
            for v in node:
                yield from numbers(v)
        elif isinstance(node, int) and not isinstance(node, bool):
            yield node

    seen = set(numbers(body["stock_summary"]))
    assert not seen & {7, 17, 20}, seen


def test_compact_no_unassigned_lines_means_no_unassigned_key(db):
    w1, _w2, p = _seed(db, unassigned=0)
    contact = _contact(db)
    _policy(db, contact, mode="compact", warehouse_ids=[w1.id])

    entry = _sellable_body(db, product_ids=[p.id], contact_id=contact.id)["stock_summary"][0]

    assert entry["open_so_qty"] == 10
    assert "unassigned_open_so_qty" not in entry


def test_compact_every_warehouse_policy_counts_both(db):
    """A policy naming neither list = every active warehouse: Total O/S is W1 + W2, and
    the unassigned remainder still rides separately."""
    _w1, _w2, p = _seed(db)
    contact = _contact(db)
    _policy(db, contact, mode="compact")

    entry = _sellable_body(db, product_ids=[p.id], contact_id=contact.id)["stock_summary"][0]

    assert entry["open_so_qty"] == 17
    assert entry["unassigned_open_so_qty"] == 3


def test_compact_inactive_warehouse_open_so_is_not_counted(db):
    """The lines never answer from an inactive warehouse, so Total O/S does not either."""
    w1, w2, p = _seed(db, unassigned=0)
    w2.is_active = False
    db.flush()
    contact = _contact(db)
    _policy(db, contact, mode="compact")

    entry = _sellable_body(db, product_ids=[p.id], contact_id=contact.id)["stock_summary"][0]

    assert entry["open_so_qty"] == 10


# ------------------------------------------------------------------- detailed under policy


def test_detailed_summary_under_policy_counts_only_visible_warehouses(db):
    """The detailed payload's per-product summary (on hand and open SO) is the same
    visible-only answer: a hidden warehouse's stock is not hinted through it either."""
    w1, _w2, p = _seed(db)
    contact = _contact(db)
    _policy(db, contact, mode="detailed", warehouse_ids=[w1.id])

    body = _sellable_body(db, product_ids=[p.id], contact_id=contact.id)

    assert [row["open_so_qty"] for row in body["data"]] == [10]
    entry = body["stock_summary"][0]
    assert entry["total_on_hand"] == 54
    assert entry["open_so_qty"] == 10
    assert entry["unassigned_open_so_qty"] == 3
    assert entry["sellable"] == 44


# ------------------------------------------------------------------- staff path unchanged


def test_staff_call_without_contact_keeps_the_product_total(db):
    _w1, _w2, p = _seed(db)

    body = _sellable_body(db, product_ids=[p.id])

    entry = body["stock_summary"][0]
    assert entry["total_on_hand"] == 94
    assert entry["open_so_qty"] == 20
    assert "unassigned_open_so_qty" not in entry


# ------------------------------------------------------------------- company scope


def test_open_so_aggregates_are_company_scoped(db):
    seed_mocha(db)
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    w_sorento = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("S"))
    w_mocha = warehouse(db, company_id=MOCHA_ID, code=unique_code("M"))
    _so_line(db, p.id, w_sorento.id, open_qty=10)
    _so_line(db, p.id, w_mocha.id, open_qty=500, company_id=MOCHA_ID)
    _so_line(db, p.id, None, open_qty=40, company_id=MOCHA_ID)
    db.flush()
    service = StockService(db)

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    assert service.open_so_qty_by_product([p.id]) == {p.id: 10}
    by_pair, unlocated = service.open_so_qty_by_product_warehouse([p.id])
    assert by_pair == {(p.id, w_sorento.id): 10}
    assert unlocated == {}

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
    assert service.open_so_qty_by_product([p.id]) == {p.id: 550}
