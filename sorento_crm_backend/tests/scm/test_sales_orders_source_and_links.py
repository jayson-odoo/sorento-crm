"""N5 - seeing the orders the Order Inquiry sheet created, and what they wait on.

> "it should be a list of SO basically, cause order inquiry is essentially SO ... then the
> linkage also needs to be visualized, location etc"

A FILTER on the existing sales-order list, not a second screen. A separate list of the same
entity is how two screens start disagreeing about the same order, and the row has to open the
sales-order detail page that already exists.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi.testclient import TestClient

from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import OrderLinkClaim
from tests.scm.conftest import requires_pg
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZTSOSRC"
URL = "/api/v1/scm/sales-orders"


def _u() -> str:
    return str(uuid.uuid4())


def _world(db):
    cat = ProductCategory(id=_u(), category_code=f"{MARKER}-C-{uuid.uuid4().hex[:6]}",
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_name=f"{MARKER} u",
                        uom_code=f"{MARKER[:4]}{uuid.uuid4().hex[:6]}")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=f"{MARKER}-ITEM-{uuid.uuid4().hex[:6]}",
                      product_name=f"{MARKER} item", category_id=cat.id,
                      base_uom_id=uom.id, list_price=0, is_active=True,
                      is_discontinued=False)
    wh = Warehouse(id=_u(), warehouse_code=f"{MARKER}-WH-{uuid.uuid4().hex[:6]}",
                   warehouse_name=f"{MARKER} wh", is_active=True, counts_as_available=True)
    db.add_all([product, wh])
    db.flush()
    return product, wh


def _order(db, product, wh, *, number, source_system, note=None):
    so = SalesOrder(id=_u(), so_number=number, status="open",
                    order_date=date(2026, 7, 1), source_system=source_system,
                    internal_note=note)
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_u(), sales_order_id=str(so.id), product_id=str(product.id),
        warehouse_id=str(wh.id), qty_ordered=12, qty_delivered=0,
        line_status="open", required_date=date(2026, 9, 1),
    ))
    db.flush()
    return so


def test_the_list_can_be_narrowed_to_the_orders_the_sheet_created(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    product, wh = _world(db)
    mine = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
    theirs = f"{MARKER}-CS-{uuid.uuid4().hex[:8]}"
    _order(db, product, wh, number=mine, source_system="scm_order_inquiry")
    _order(db, product, wh, number=theirs, source_system="scm_upload")

    r = TestClient(app).get(URL, params={"source": "inquiry", "limit": 200})

    assert r.status_code == 200, r.text
    numbers = {row["so_number"] for row in r.json()["data"]}
    assert mine in numbers
    assert theirs not in numbers, "the filter let CS's order through"


def test_every_row_says_where_it_came_from(scm_app):
    """A buyer reading the list is entitled to know which of the two feeds wrote a row -
    it decides who may edit its figures."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    product, wh = _world(db)
    number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
    _order(db, product, wh, number=number, source_system="scm_order_inquiry")

    r = TestClient(app).get(URL, params={"query": number})
    row = next(x for x in r.json()["data"] if x["so_number"] == number)

    assert row["source"] == "inquiry"


def test_the_row_carries_its_stock_location(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    product, wh = _world(db)
    number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
    _order(db, product, wh, number=number, source_system="scm_order_inquiry")

    r = TestClient(app).get(URL, params={"query": number})
    row = next(x for x in r.json()["data"] if x["so_number"] == number)

    assert row["stock_locations"] == [wh.warehouse_code]


def test_the_row_shows_the_purchase_orders_it_waits_on_and_which_are_resolved(scm_app):
    """The waiting ones are the reason this column exists: "which of my orders is stuck
    behind a purchase order we have not received" has no other answer."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    product, wh = _world(db)
    number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
    _order(db, product, wh, number=number, source_system="scm_order_inquiry")
    db.add_all([
        OrderLinkClaim(id=_u(), so_number=number, po_number="ZZT-PO-WAITING",
                       item_code=product.product_code, source="order_inquiry",
                       claimed_at=datetime(2026, 8, 5, 12, 0, 0)),
        OrderLinkClaim(id=_u(), so_number=number, po_number="ZZT-PO-DONE",
                       item_code=None, source="order_inquiry",
                       claimed_at=datetime(2026, 8, 5, 12, 0, 0),
                       resolved_at=datetime(2026, 8, 5, 13, 0, 0)),
    ])
    db.flush()

    r = TestClient(app).get(URL, params={"query": number})
    row = next(x for x in r.json()["data"] if x["so_number"] == number)

    by_po = {l["po_number"]: l for l in row["linked_purchase_orders"]}
    assert by_po["ZZT-PO-WAITING"]["resolved"] is False
    assert by_po["ZZT-PO-DONE"]["resolved"] is True
    assert row["awaiting_purchase_orders"] == 1


def test_the_project_survives_when_no_customer_matched_it(scm_app):
    """Otherwise an order the sheet created for a named project reads as anonymous."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    product, wh = _world(db)
    number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
    _order(db, product, wh, number=number, source_system="scm_order_inquiry",
           note="Order Inquiry project: HOMEPRO")

    r = TestClient(app).get(URL, params={"query": number})
    row = next(x for x in r.json()["data"] if x["so_number"] == number)

    assert row["customer_name"] == ""
    assert "HOMEPRO" in (row["internal_note"] or "")


def test_an_unknown_source_does_not_silently_return_everything(scm_app):
    """A filter that quietly ignores a value it does not understand shows the whole book
    under a heading that says otherwise."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    product, wh = _world(db)
    number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
    _order(db, product, wh, number=number, source_system="scm_order_inquiry")

    r = TestClient(app).get(URL, params={"source": "nonsense", "query": number})

    assert r.status_code == 200
    assert r.json()["data"] == []
