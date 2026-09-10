"""L3 Order Inquiry importer applies Rule 1 (`label_from_inquiry_cell`) on every order the
sheet names, whichever branch writes it: an order AutoCount already owns (AC-O1), a
provisional order this feed creates (AC-O2), a customer-only cell that carries no label at
all (AC-O3), and a corrected cell on a re-upload (AC-O4, equal rank overwrites).

Substrate: `pg_session()` against the REAL database, rolled back - the same substrate
`test_project_order_inquiry_import_creates_demand.py` uses for this service, since the write
under test is `_create_orders` itself rather than a schema surface `blank_session` would
also serve. `project_label`/`project_label_source` are mapped on the ORM model but do not
exist as columns on the real database until migration 511 is actually applied there, so a
raw-SQL pre-seed of an existing label (AC-O3, AC-O4) fails loudly until that lands - which is
the point of a red test.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services import project_order_inquiry_import_service as svc
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTPLOI"
SORENTO = "00000000-0000-0000-0000-000000000001"
LOCATION = f"{MARKER}-WH"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        set_company_scope(s, frozenset({SORENTO}))
        yield s


@pytest.fixture()
def world(db):
    cat = ProductCategory(
        id=_u(), category_code=f"{MARKER}-C-{uuid.uuid4().hex[:6]}", category_name=f"{MARKER} cat"
    )
    uom = UnitOfMeasure(
        id=_u(), uom_name=f"{MARKER} u", uom_code=f"{MARKER[:4]}{uuid.uuid4().hex[:6]}"
    )
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=_u(), product_code=unique_code(MARKER), product_name=f"{MARKER} item",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(product)
    wh = Warehouse(
        id=_u(), warehouse_code=LOCATION, warehouse_name=f"{MARKER} wh",
        is_active=True, counts_as_available=True,
    )
    db.add(wh)
    db.flush()
    return {"product": product, "warehouse": wh}


class _Row:
    def __init__(self, *, so_number, item_code, qty=10.0, so_date=date(2026, 7, 1),
                 delivery_date=date(2026, 9, 1), project="", location=LOCATION,
                 po_numbers=(), not_ordered=False):
        self.so_number = so_number
        self.item_code = item_code
        self.qty = qty
        self.so_date = so_date
        self.delivery_date = delivery_date
        self.project = project
        self.location = location
        self.supplier = ""
        self.po_numbers = po_numbers
        self.not_ordered = not_ordered
        self.sheet = "Sheet1"
        self.source_row = 2


class _Parsed:
    def __init__(self, rows):
        self.rows = rows
        self.ok = True
        self.problems = []
        self.sheets_read = ["Sheet1"]
        self.sheets_skipped = []
        self.with_location = sum(1 for r in rows if r.location)
        self.po_claims = sum(len(r.po_numbers) for r in rows)


def _create(db, rows) -> dict:
    return svc._create_orders(db, _Parsed(rows), svc._now())


def _order(db, number) -> SalesOrder:
    return db.query(SalesOrder).filter(SalesOrder.so_number == number).one()


def _set_label(db, order_id, *, label, source):
    """Pre-seed an existing label. Raw SQL, because the real DATABASE does not carry the
    column yet even though the ORM model now maps it - and this is exactly where the red
    shows up until migration 511 is actually applied there."""
    db.execute(
        text(
            "UPDATE sales_orders SET project_label = :label, project_label_source = :source "
            "WHERE id = :id"
        ),
        {"label": label, "source": source, "id": order_id},
    )
    db.flush()


def test_o1_an_order_autocount_owns_gets_the_inquiry_label_and_keeps_its_figures(db, world):
    number = unique_code(f"{MARKER}-SO")
    theirs = SalesOrder(
        id=_u(), so_number=number, status="open", order_type="dealer",
        source_system="scm_upload", order_date=date(2026, 1, 1),
    )
    db.add(theirs)
    db.flush()
    db.add(SalesOrderLine(
        id=_u(), sales_order_id=str(theirs.id), product_id=str(world["product"].id),
        qty_ordered=999, qty_delivered=0, line_status="open",
        required_date=date(2026, 12, 31),
    ))
    db.flush()

    cell = "PEMBINAAN TEGUH MAJU / PASAR BESAR CHERAS - RESIDENCE / KUALA LUMPUR"
    out = _create(db, [_Row(
        so_number=number, item_code=world["product"].product_code,
        project=cell, qty=1.0, delivery_date=date(2026, 9, 1),
    )])

    assert out["orders_owned_elsewhere"] == 1
    order = _order(db, number)
    assert order.project_label == "PASAR BESAR CHERAS - RESIDENCE / KUALA LUMPUR"
    assert order.project_label_source == "inquiry"
    line = db.query(SalesOrderLine).filter(
        SalesOrderLine.sales_order_id == str(order.id)
    ).one()
    assert float(line.qty_ordered) == 999, "the sheet must not touch a figure it does not own"


def test_o2_a_provisional_order_the_sheet_creates_carries_the_inquiry_label(db, world):
    number = unique_code(f"{MARKER}-SO")
    cell = "URC ENGINEERING / BAMBOO RESIDENCE / KUALA LUMPUR"

    out = _create(
        db, [_Row(so_number=number, item_code=world["product"].product_code, project=cell)]
    )

    assert out["orders_created"] == 1
    order = _order(db, number)
    assert order.project_label == "BAMBOO RESIDENCE / KUALA LUMPUR"
    assert order.project_label_source == "inquiry"
    # Existing note behaviour is unchanged: no customer named "BAMBOO RESIDENCE / KUALA
    # LUMPUR" exists, so the whole cell is also kept as a note.
    assert (order.internal_note or "").startswith("Order Inquiry project:")


def test_o3_a_customer_only_cell_writes_no_label_and_leaves_an_existing_one_untouched(db, world):
    number = unique_code(f"{MARKER}-SO")
    theirs = SalesOrder(
        id=_u(), so_number=number, status="open", order_type="dealer",
        source_system="scm_upload", order_date=date(2026, 1, 1),
    )
    db.add(theirs)
    db.flush()
    _set_label(db, theirs.id, label="PRE-EXISTING LABEL", source="note")

    out = _create(db, [_Row(
        so_number=number, item_code=world["product"].product_code,
        project="PASAR BESAR CHERAS",  # no slash - a customer name only
    )])

    assert out["orders_owned_elsewhere"] == 1
    order = _order(db, number)
    assert order.project_label == "PRE-EXISTING LABEL"
    assert order.project_label_source == "note"


def test_o4_a_reupload_with_a_corrected_cell_overwrites_the_earlier_inquiry_label(db, world):
    number = unique_code(f"{MARKER}-SO")
    theirs = SalesOrder(
        id=_u(), so_number=number, status="open", order_type="dealer",
        source_system="scm_upload", order_date=date(2026, 1, 1),
    )
    db.add(theirs)
    db.flush()
    _set_label(db, theirs.id, label="OLD LABEL", source="inquiry")

    out = _create(db, [_Row(
        so_number=number, item_code=world["product"].product_code,
        project="CUSTOMER / CORRECTED LABEL",
    )])

    assert out["orders_owned_elsewhere"] == 1
    order = _order(db, number)
    assert order.project_label == "CORRECTED LABEL"
    assert order.project_label_source == "inquiry"
