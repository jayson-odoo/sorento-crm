"""L3 Order Inquiry importer applies Rule 1 (`label_from_inquiry_cell`) on every order the
sheet names AND THE CRM HOLDS: a label that matches no customer (AC-O2), a customer-only cell
that carries no label at all (AC-O3), and a corrected cell on a re-upload (AC-O4, equal rank
overwrites). AC-O1 is now the only shape there is - the sheet stopped creating sales orders
(`PLAN-scm-oi-sheet-migration.md` D4), so every order it names is one somebody else owns.

The SEAM moved with the code (AC-S1-37): these tests drive `apply()` with a real workbook and
the sales order seeded, where they used to call `_create_orders` with a hand-built parse. The
label assertions are unchanged; what went is the pair of counters that counted orders this
feed created and orders it left alone, neither of which it answers with any more.

Substrate: `pg_session()` against the REAL database, rolled back. `project_label` /
`project_label_source` are mapped on the ORM model, and a raw-SQL pre-seed of an existing
label (AC-O3, AC-O4) fails loudly where migration 511 has not been applied.
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


#: The customer's own header row, with the project cell Rule 1 reads.
HEADERS = ("SO NO", "ITEM CODE", "QTY", "DELIVERY DATE", "STOCK LOCATION",
           "PROJECT CUSTOMER")


def _sheet(rows) -> bytes:
    """One tab of the operator's own workbook, read by the importer's own reader.

    A real file rather than a hand-built parse: the seam is `apply()` now, and a fake parsed
    object would let the reader and the importer drift apart unnoticed.
    """
    import openpyxl
    from io import BytesIO

    wb = openpyxl.Workbook()
    tab = wb.active
    tab.append(list(HEADERS))
    for row in rows:
        tab.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row(number, item_code, project, *, qty=10.0, delivery_date=date(2026, 9, 1)):
    return (number, item_code, qty, delivery_date, LOCATION, project)


def _apply(db, rows) -> dict:
    return svc.apply(db, _sheet(rows), file_name="project label.xlsx")


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
    out = _apply(db, [_row(number, world["product"].product_code, cell, qty=1.0)])

    # Not project demand, so nothing is raised against it - and the label still lands,
    # because naming the order is what states the project, whatever class it carries.
    assert out["orders_not_plannable"] == [
        {"so_number": number, "code": "sales_order_not_project_class"}
    ]
    assert out["rows_raised"] == 0
    order = _order(db, number)
    assert order.project_label == "PASAR BESAR CHERAS - RESIDENCE / KUALA LUMPUR"
    assert order.project_label_source == "inquiry"
    line = db.query(SalesOrderLine).filter(
        SalesOrderLine.sales_order_id == str(order.id)
    ).one()
    assert float(line.qty_ordered) == 999, "the sheet must not touch a figure it does not own"


def test_o2_a_label_matching_no_customer_still_lands_on_the_order(db, world):
    """AC-O2, at the only seam left for it.

    It used to be stated as "a provisional order the sheet CREATES carries the label", and
    the sheet creates nothing now (D4) - so what it is really about is the half of the cell
    that names no customer we hold: the project half is still a label, and it still lands.
    """
    number = unique_code(f"{MARKER}-SO")
    theirs = SalesOrder(
        id=_u(), so_number=number, status="open", order_type="dealer",
        source_system="autocount", order_date=date(2026, 1, 1),
    )
    db.add(theirs)
    db.flush()
    cell = "URC ENGINEERING / BAMBOO RESIDENCE / KUALA LUMPUR"

    _apply(db, [_row(number, world["product"].product_code, cell)])

    order = _order(db, number)
    assert order.project_label == "BAMBOO RESIDENCE / KUALA LUMPUR"
    assert order.project_label_source == "inquiry"


def test_o3_a_customer_only_cell_writes_no_label_and_leaves_an_existing_one_untouched(db, world):
    number = unique_code(f"{MARKER}-SO")
    theirs = SalesOrder(
        id=_u(), so_number=number, status="open", order_type="dealer",
        source_system="scm_upload", order_date=date(2026, 1, 1),
    )
    db.add(theirs)
    db.flush()
    _set_label(db, theirs.id, label="PRE-EXISTING LABEL", source="note")

    _apply(db, [_row(number, world["product"].product_code,
                     "PASAR BESAR CHERAS")])  # no slash - a customer name only

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

    _apply(db, [_row(number, world["product"].product_code,
                     "CUSTOMER / CORRECTED LABEL")])

    order = _order(db, number)
    assert order.project_label == "CORRECTED LABEL"
    assert order.project_label_source == "inquiry"
