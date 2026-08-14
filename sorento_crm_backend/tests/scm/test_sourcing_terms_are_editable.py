"""The price, the money it is in, and the minimum order are things a person can set.

> "all the currency is in RMB (purchase currency for product, need to be able to set that)"

Every one of these already existed as a column on `product_suppliers` and was already read
by the reorder engine. None of them could be written: the API exposed only the lead time, so
a buyer looking at a plan that said "no cost" had nowhere to go and put one. 5,417 of 17,408
links carry no price at all, which is most of what the "No price yet" section is made of.

The rule these tests exist to hold is the currency pairing. `scm.money.normalize_currency`
reads a blank code as ringgit, which is the right reading for rows written before the book
had a second currency. It is the wrong reading for a price typed today: a yuan figure saved
with no code is ranked and budgeted as ringgit, and nothing downstream can tell, because the
number is perfectly well formed. So a price without a currency is refused at entry.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.procurement import ProductSupplier, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.schemas.procurement import ProductSupplierCreate, ProductSupplierUpdate
from app.services.error_handler import AppException
from app.services.procurement_service import ProductSupplierService
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTSRC"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def world(db):
    """A product and two suppliers of our own, so nothing here reads a production row."""
    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                      category_id=cat.id, base_uom_id=uom.id, list_price=0,
                      is_active=True, is_discontinued=False)
    supplier = Supplier(id=_u(), supplier_code=unique_code("S"),
                        supplier_name=f"{MARKER} Supplier")
    db.add_all([product, supplier])
    db.flush()
    return {"product": product, "supplier": supplier}


def _svc(db) -> ProductSupplierService:
    return ProductSupplierService(db)


def _create(db, world, **terms):
    terms.setdefault("standard_lead_time_days", 30)
    return _svc(db).create_product_supplier(
        ProductSupplierCreate(product_id=str(world["product"].id),
                              supplier_id=str(world["supplier"].id), **terms)
    )


# --------------------------------------------------------------------------- #
# the terms round-trip
# --------------------------------------------------------------------------- #

def test_a_link_can_be_created_with_a_price_in_yuan(db, world):
    link = _create(db, world, unit_cost="12.50", currency="CNY", moq=100,
                   order_multiple=25, standard_lead_time_days=45)

    assert float(link.unit_cost) == 12.50
    assert link.currency == "CNY"
    assert link.moq == 100
    assert link.order_multiple == 25
    assert link.standard_lead_time_days == 45


def test_the_currency_code_is_stored_trimmed_and_upper_cased(db, world):
    link = _create(db, world, unit_cost="1", currency=" cny ")
    assert link.currency == "CNY"


def test_a_price_can_be_added_to_a_link_that_had_none(db, world):
    """The case the plan actually produces: a link exists, with no price on it."""
    link = _create(db, world)
    assert link.unit_cost is None

    updated = _svc(db).update_product_supplier(
        str(link.id), ProductSupplierUpdate(unit_cost="8.25", currency="CNY")
    )

    assert float(updated.unit_cost) == 8.25
    assert updated.currency == "CNY"


def test_omitting_the_primary_flag_leaves_the_row_alone(db, world):
    """It is the one NOT NULL column here, so an unset field must not reach it as null."""
    link = _create(db, world, is_primary_supplier=True)

    updated = _svc(db).update_product_supplier(
        str(link.id), ProductSupplierUpdate(moq=10)
    )

    assert updated.is_primary_supplier is True
    assert updated.moq == 10


def test_a_link_created_without_a_primary_flag_is_not_primary(db, world):
    link = _create(db, world)
    assert link.is_primary_supplier is False


# --------------------------------------------------------------------------- #
# a price has to say what money it is in
# --------------------------------------------------------------------------- #

def test_a_price_with_no_currency_is_refused(db, world):
    with pytest.raises(AppException) as err:
        _create(db, world, unit_cost="12.50")

    assert "currency" in str(err.value).lower()


def test_adding_a_price_to_a_link_with_no_currency_is_refused(db, world):
    """The patch alone looks innocent - only the merged row shows the gap."""
    link = _create(db, world)

    with pytest.raises(AppException):
        _svc(db).update_product_supplier(
            str(link.id), ProductSupplierUpdate(unit_cost="12.50")
        )


def test_a_price_keeps_the_currency_already_on_the_row(db, world):
    """Setting only the price on an already-CNY link is fine - the pairing still holds."""
    link = _create(db, world, unit_cost="10", currency="CNY")

    updated = _svc(db).update_product_supplier(
        str(link.id), ProductSupplierUpdate(unit_cost="11")
    )

    assert float(updated.unit_cost) == 11
    assert updated.currency == "CNY"


def test_clearing_the_currency_under_a_live_price_is_refused(db, world):
    link = _create(db, world, unit_cost="10", currency="CNY")

    with pytest.raises(AppException):
        _svc(db).update_product_supplier(
            str(link.id), ProductSupplierUpdate(currency="")
        )


def test_a_link_with_no_price_needs_no_currency(db, world):
    """Nothing to misread, so nothing to require."""
    link = _create(db, world, moq=50)
    assert link.currency is None
    assert link.moq == 50


def test_a_free_item_still_has_to_say_which_currency_it_is_free_in(db, world):
    """Zero is a price, not the absence of one (see test_cost_from_po_history), so it
    travels the same path and is subject to the same pairing."""
    with pytest.raises(AppException):
        _create(db, world, unit_cost="0")

    link = _create(db, world, unit_cost="0", currency="CNY")
    assert float(link.unit_cost) == 0.0


# --------------------------------------------------------------------------- #
# malformed codes never reach the column
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("code", ["RMBX", "C1N", "R M"])
def test_a_code_that_is_not_three_letters_is_rejected(code):
    with pytest.raises(ValueError):
        ProductSupplierUpdate(currency=code)


def test_an_empty_code_reads_as_nothing_on_file():
    assert ProductSupplierUpdate(currency="   ").currency is None


# --------------------------------------------------------------------------- #
# what the engine then sees
# --------------------------------------------------------------------------- #

def test_the_engine_reads_the_price_that_was_just_set(db, world):
    """The point of the whole surface: a price entered here has to reach the plan."""
    from app.services.scm import reorder_engine as eng

    _create(db, world, unit_cost="12.50", currency="CNY", standard_lead_time_days=45)

    rows = eng.load_supplier_candidates(db, str(world["product"].id))
    mine = [c for c in rows if c["supplier_name"] == f"{MARKER} Supplier"]

    assert len(mine) == 1
    assert mine[0]["unit_cost"] == 12.50
    assert mine[0]["currency"] == "CNY"
