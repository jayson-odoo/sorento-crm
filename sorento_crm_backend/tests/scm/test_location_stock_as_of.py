"""UAC F4 - the On hand lightbox says WHEN the stock it shows was last uploaded.

R7: "'Stock as of' = newest `stock.updated_at` for the product (fallback: last stock
import job finished time)." Plan fact F1 records what it was before: `as_of =
datetime.utcnow()`, the moment the dialog asked - which is the one thing it certainly is
not. AutoCount stock arrives by upload, so a figure stamped "as of now" tells a buyer the
book is live when it may be three days old, and that is the number they decide against.

The same read also carries `is_pool` (already shipped) and `po_qty` per location: the
dialog counts site-pool rows only (R15) and prints what is on order into each of them.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest

from app.models.base import company_scope
from app.models.inventory import Stock
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.services.scm import location_stock_service
from tests._pg_fixture import pg_session
from tests.scm._revamp_fixtures import category_and_uom, product, supplier, warehouse
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg

pytestmark = requires_pg


@pytest.fixture()
def db():
    with pg_session() as s:
        with company_scope(s, frozenset({SORENTO_COMPANY_ID})):
            yield s


def _stock(db, prod, wh, qty, *, updated_at=None):
    row = Stock(id=str(uuid.uuid4()), product_id=prod.id, warehouse_id=wh.id,
                quantity_on_hand=qty)
    db.add(row)
    db.flush()
    if updated_at is not None:
        row.updated_at = updated_at
        db.flush()
    return row


def _open_po(db, *, sup, prod, wh, number, qty):
    po = PurchaseOrder(
        id=str(uuid.uuid4()), po_number=number, supplier_id=sup.id, status="active",
        issue_date=date(2026, 5, 1), currency="MYR",
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=str(uuid.uuid4()), purchase_order_id=po.id, product_id=prod.id,
        warehouse_id=wh.id, qty_ordered=qty, qty_received=0, unit_cost=1,
        currency="MYR", line_status="open",
    ))
    db.flush()


def test_as_of_is_the_newest_stock_update_not_the_clock(db):
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    older, newer = warehouse(db, segment="dealer"), warehouse(db, segment="dealer")
    _stock(db, prod, older, 10, updated_at=datetime(2026, 8, 20, 3, 15))
    _stock(db, prod, newer, 4, updated_at=datetime(2026, 8, 24, 7, 40))

    out = location_stock_service.location_stock_for_product(db, str(prod.id))

    assert out["as_of"] == "2026-08-24T07:40:00"
    assert out["as_of_source"] == "stock"


def test_a_product_with_no_stock_row_says_so_rather_than_stamping_now(db):
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)

    out = location_stock_service.location_stock_for_product(db, str(prod.id))

    assert out["locations"] == []
    # Either a fallback import time or nothing at all - never a fabricated "now".
    assert out["as_of_source"] in ("import_job", "none")
    if out["as_of_source"] == "none":
        assert out["as_of"] is None


def test_each_location_carries_is_pool_and_its_open_po_quantity(db):
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    sup = supplier(db, "location stock supplier")
    pool = warehouse(db, segment="dealer")
    bin_ = warehouse(db, segment="project", pool_warehouse_id=pool.id)
    _stock(db, prod, pool, 12, updated_at=datetime(2026, 8, 24, 7, 40))
    _stock(db, prod, bin_, 5, updated_at=datetime(2026, 8, 24, 7, 40))
    _open_po(db, sup=sup, prod=prod, wh=pool, number="ZZTRVMP-LS-PO", qty=63)

    out = location_stock_service.location_stock_for_product(db, str(prod.id))
    by_id = {loc["warehouse_id"]: loc for loc in out["locations"]}

    assert by_id[str(pool.id)]["is_pool"] is True
    assert by_id[str(pool.id)]["po_qty"] == 63
    assert by_id[str(bin_.id)]["is_pool"] is False
    # A location nothing is on order for says zero, not null: the book has an answer.
    assert by_id[str(bin_.id)]["po_qty"] == 0
