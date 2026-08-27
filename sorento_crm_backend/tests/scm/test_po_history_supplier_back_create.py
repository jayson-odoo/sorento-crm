"""The purchase-history upload back-creates a creditor the supplier master has never seen.

Captain's ruling, 28 Aug 2026: this channel creates a missing supplier by the same rule the
outstanding purchase-order upload already uses - by the creditor CODE where the file states
one, else by the cleaned creditor NAME under a generated code. The structured export states
the name and never a code, so before the ruling every creditor it named that the master had
not caught up on wrote its orders unlinked, and an expediting list cannot say who is late
about an order that belongs to nobody.

The one case that still creates nothing is an AMBIGUOUS name: two supplier rows folding to
one key (the same company held once per currency account). Picking one would attribute a
year of purchases to whichever row Postgres returned first, so the name is reported for
somebody to merge instead.
"""
from __future__ import annotations

import re
import uuid
from datetime import date

import pytest

from app.models.base import set_company_scope
from app.models.procurement import PurchaseOrder, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm import po_history_service as svc
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import workbook

MARKER = "ZZTPHBC"
SORENTO = "00000000-0000-0000-0000-000000000001"

#: The structured export's columns, as `purchase_history_reader` resolves them (migration
#: 358 seeded the aliases). `Creditor Name` and no creditor code at all is the whole point.
HEADERS = ("Doc No", "Doc Date", "Item Code", "Qty", "Location", "Creditor Name",
           "Delivery Date")

#: Document numbers no real book uses, so this file cannot collide with the prod copy the
#: shared local database is.
DOC_A = "209901-S0001"
DOC_B = "209901-S0002"


def _u() -> str:
    return str(uuid.uuid4())


def _slug(name: str) -> str:
    """What `supplier_back_create.supplier_slug` generates for a free name.

    Spelled out rather than imported, so the expected code is stated by the test rather than
    by the code under test.
    """
    return re.sub(r"[^A-Z0-9]", "", name.upper())[:50]


@pytest.fixture()
def db():
    """`autoflush=False`, as `SessionLocal` is: every creation here is a get-or-create."""
    with pg_session(autoflush=False) as s:
        set_company_scope(s, frozenset({SORENTO}))
        yield s


@pytest.fixture()
def catalogue(db):
    """One product of this test's own, so no assertion depends on the customer's data."""
    cat = ProductCategory(id=_u(), category_code=f"{MARKER}-CAT-{uuid.uuid4().hex[:6]}",
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_name=f"{MARKER} unit",
                        uom_code=f"{MARKER[:4]}{uuid.uuid4().hex[:6]}")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
                      product_name=f"{MARKER} item", category_id=cat.id,
                      base_uom_id=uom.id, list_price=0, is_active=True,
                      is_discontinued=False)
    db.add(product)
    db.flush()
    return product


def _creditor() -> str:
    return f"{MARKER} TAIYANG TECHNOLOGY CO.,LTD {uuid.uuid4().hex[:6].upper()}"


def _book(product, *documents) -> bytes:
    """A structured purchase book: one line per (document, creditor name) pair."""
    return workbook(
        [
            (number, date(2099, 1, 2), product.product_code, 12, "", creditor,
             date(2099, 2, 1))
            for number, creditor in documents
        ],
        headers=HEADERS,
        title="PO SPO",
    )


def _order(db, number: str) -> PurchaseOrder:
    return db.query(PurchaseOrder).filter(PurchaseOrder.po_number == number).one()


def _named(db, name: str) -> list[Supplier]:
    return db.query(Supplier).filter(Supplier.supplier_name == name).all()


# --------------------------------------------------------------------------- #
# by name, which is all the structured export states
# --------------------------------------------------------------------------- #

def test_a_creditor_the_master_does_not_hold_is_created_from_its_name(db, catalogue):
    """The ruling itself: name-only creditor, supplier created, order linked, counted."""
    name = _creditor()

    out = svc.apply(db, _book(catalogue, (DOC_A, name)))
    db.flush()

    created = _named(db, name)
    assert len(created) == 1, "the creditor the file named was not created"
    assert created[0].supplier_code == _slug(name)
    assert str(_order(db, DOC_A).supplier_id) == str(created[0].id)
    assert out["suppliers_created"] == 1
    # The NAME the operator's own file said, not the code nobody typed - the same choice the
    # outstanding importer's name path makes.
    assert out["suppliers_created_codes"] == [name]


def test_the_currency_note_is_stripped_from_the_supplier_it_creates(db, catalogue):
    """`X (RMB)` is AutoCount naming the ACCOUNT, and the master holds `X`.

    Created under the raw cell it would be a duplicate supplier per currency the client
    happens to buy that item in.
    """
    name = _creditor()

    svc.apply(db, _book(catalogue, (DOC_A, f"{name} (RMB)")))
    db.flush()

    created = _named(db, name)
    assert len(created) == 1, "the currency note became part of the supplier's name"
    assert created[0].supplier_code == _slug(name)


def test_two_spellings_of_one_creditor_create_one_supplier(db, catalogue):
    """The same file states `X` on one document and `X (RMB)` on the next."""
    name = _creditor()

    out = svc.apply(db, _book(catalogue, (DOC_A, name), (DOC_B, f"{name} (RMB)")))
    db.flush()

    created = _named(db, name)
    assert len(created) == 1
    assert out["suppliers_created"] == 1
    assert str(_order(db, DOC_A).supplier_id) == str(created[0].id)
    assert str(_order(db, DOC_B).supplier_id) == str(created[0].id)


def test_an_existing_creditor_is_matched_rather_than_created(db, catalogue):
    name = _creditor()
    held = Supplier(id=_u(), supplier_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
                    supplier_name=name, is_active=True)
    db.add(held)
    db.flush()

    out = svc.apply(db, _book(catalogue, (DOC_A, f"{name} (RMB)")))
    db.flush()

    assert out["suppliers_created"] == 0
    assert str(_order(db, DOC_A).supplier_id) == str(held.id)


# --------------------------------------------------------------------------- #
# what still creates nothing
# --------------------------------------------------------------------------- #

def test_an_ambiguous_creditor_name_creates_nothing_and_is_reported(db, catalogue):
    """Two rows fold to one key, so there is no honest answer to pick and none is invented."""
    name = _creditor()
    db.add_all([
        Supplier(id=_u(), supplier_code=f"{MARKER}-A-{uuid.uuid4().hex[:6]}",
                 supplier_name=name, is_active=True),
        Supplier(id=_u(), supplier_code=f"{MARKER}-B-{uuid.uuid4().hex[:6]}",
                 supplier_name=f"{name} (USD)", is_active=True),
    ])
    db.flush()

    out = svc.apply(db, _book(catalogue, (DOC_A, name)))
    db.flush()

    assert len(_named(db, name)) == 1, "an ambiguous creditor was created a third time"
    assert _order(db, DOC_A).supplier_id is None
    assert name in out["unmatched_creditors"]
    assert out["unmatched_creditor_count"] == 1
    assert out["suppliers_created"] == 0


def test_a_second_upload_of_the_same_book_creates_no_second_supplier(db, catalogue):
    """Re-uploading a wider date range is the normal case, so creation is get-or-create."""
    name = _creditor()
    book = _book(catalogue, (DOC_A, name))

    first = svc.apply(db, book)
    db.flush()
    second = svc.apply(db, book)
    db.flush()

    assert first["suppliers_created"] == 1
    assert second["suppliers_created"] == 0
    assert len(_named(db, name)) == 1


def test_a_slug_collision_takes_a_numeric_suffix(db, catalogue):
    """`supplier_code` is unique, so a generated code somebody else holds is disambiguated.

    A different COMPANY under a code that happens to slug the same way, which is why the
    suffix exists rather than the insert simply failing.
    """
    name = _creditor()
    db.add(Supplier(id=_u(), supplier_code=_slug(name),
                    supplier_name=f"{MARKER} OTHER {uuid.uuid4().hex[:6].upper()}",
                    is_active=True))
    db.flush()

    svc.apply(db, _book(catalogue, (DOC_A, name)))
    db.flush()

    created = _named(db, name)
    assert len(created) == 1
    assert created[0].supplier_code == f"{_slug(name)}-2"


# --------------------------------------------------------------------------- #
# what the confirm screen says before any of it happens
# --------------------------------------------------------------------------- #

def test_preview_creates_nothing_and_names_what_it_would_create(db, catalogue):
    """A preview that does not mention a supplier the commit invents is a preview that lies."""
    name = _creditor()

    out = svc.preview(db, _book(catalogue, (DOC_A, name)))

    assert _named(db, name) == []
    assert out["creditors_to_create"] == [name]
    assert out["creditors_to_create_count"] == 1
    # Creatable is not the same complaint as ambiguous, so it does not bury it.
    assert out["unmatched_creditors"] == []
