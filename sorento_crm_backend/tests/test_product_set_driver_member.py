"""F12 / R19 - which member of a set the loading plan reads its figures off.

TEST-FIRST: `product_set_service.driver_member` does not exist when this file is written.

A set is never stocked, never ordered and never costed - its MEMBERS are - so every figure a
set row shows on the loading plan has to come from one of them. R19 rules that it is ONE
member, the DRIVER: the member belonging to the fewest sets, ties broken by `sort_order` and
then by product code.

Both alternatives were rejected for the same reason, and the reason is `CWCY605`: the cistern
sits in six different sets. A minimum across members would understate every one of them
(each set would read the cistern's own thin demand), and a sum would count the cistern six
times over. The pedestal belongs to one set, so it is the member whose numbers actually
describe that set - and on this catalogue the "fewest sets" rule picks the pedestal every
time without anybody having to tag one.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy.orm import Session

from app.database import engine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet, ProductSetMember
from app.services.company_scope import company_scope, register_company_scope_listeners
from app.services.product_set_service import driver_member, driver_members

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

MARKER = "ZZTDRV"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db() -> Session:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        with company_scope(session, None):
            yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


class Catalogue:
    """Marker-prefixed products and sets, so nothing collides with the prod copy."""

    def __init__(self, db: Session):
        self.db = db
        self.tag = uuid.uuid4().hex[:8].upper()
        self.cat = ProductCategory(
            id=_u(), category_code=f"{MARKER}-C-{self.tag}", category_name=f"{MARKER} cat"
        )
        self.uom = UnitOfMeasure(id=_u(), uom_code=f"{MARKER}-U-{self.tag}"[:20], uom_name="pcs")
        db.add_all([self.cat, self.uom])
        db.flush()

    def product(self, code: str) -> Product:
        product = Product(
            id=_u(),
            product_code=f"{MARKER}{self.tag}-{code}",
            product_name=code,
            category_id=self.cat.id,
            base_uom_id=self.uom.id,
            list_price=0,
            is_active=True,
            is_discontinued=False,
        )
        self.db.add(product)
        self.db.flush()
        return product

    def product_set(self, code: str, members: list) -> ProductSet:
        product_set = ProductSet(
            id=_u(), set_code=f"{MARKER}{self.tag}-{code}", name=code, is_active=True
        )
        self.db.add(product_set)
        self.db.flush()
        for product, quantity, sort_order in members:
            self.db.add(
                ProductSetMember(
                    id=_u(),
                    product_set_id=product_set.id,
                    product_id=product.id,
                    quantity=quantity,
                    sort_order=sort_order,
                )
            )
        self.db.flush()
        return product_set


def test_the_driver_is_the_member_in_the_fewest_sets(db: Session):
    """The worked example. `CWC605-RL` reads `CWCX605-RL`'s figures, never `CWCY605`'s -
    the cistern is shared across six sets and its numbers describe none of them."""
    c = Catalogue(db)
    pedestal = c.product("CWCX605-RL")
    cistern = c.product("CWCY605")
    wc = c.product_set("CWC605-RL", [(cistern, 1, 0), (pedestal, 1, 1)])
    for n in range(5):
        c.product_set(f"CWC60{n}-SHARED", [(cistern, 1, 0), (c.product(f"X{n}"), 1, 1)])

    driver = driver_member(db, str(wc.id))

    assert str(driver.product_id) == str(pedestal.id)


def test_a_tie_on_set_count_is_broken_by_sort_order(db: Session):
    """Two members each in one set: the one the author put first wins. `sort_order` is the
    only statement of intent a set carries about its own parts."""
    c = Catalogue(db)
    second = c.product("BBB")
    first = c.product("AAA")
    wc = c.product_set("TIE", [(second, 1, 5), (first, 1, 2)])

    assert str(driver_member(db, str(wc.id)).product_id) == str(first.id)


def test_a_tie_on_sort_order_too_is_broken_by_product_code(db: Session):
    """Never left to physical row order: two runs of the same plan must not disagree about
    whose numbers a row is showing."""
    c = Catalogue(db)
    later = c.product("ZZZ")
    earlier = c.product("AAA")
    wc = c.product_set("TIE2", [(later, 1, 0), (earlier, 1, 0)])

    assert str(driver_member(db, str(wc.id)).product_id) == str(earlier.id)


def test_a_set_with_no_members_has_no_driver(db: Session):
    c = Catalogue(db)
    empty = c.product_set("EMPTY", [])

    assert driver_member(db, str(empty.id)) is None


def test_several_sets_are_answered_in_one_call(db: Session):
    """`build` asks for every set on a supplier's statement at once - a query per set on a
    page of forty is how a screen gets slow without anyone noticing."""
    c = Catalogue(db)
    pedestal_a, cistern = c.product("PA"), c.product("SHARED")
    pedestal_b = c.product("PB")
    a = c.product_set("A", [(pedestal_a, 1, 0), (cistern, 1, 1)])
    b = c.product_set("B", [(pedestal_b, 1, 0), (cistern, 1, 1)])

    found = driver_members(db, [str(a.id), str(b.id)])

    assert str(found[str(a.id)].product_id) == str(pedestal_a.id)
    assert str(found[str(b.id)].product_id) == str(pedestal_b.id)


def test_the_driver_carries_its_own_product_and_quantity(db: Session):
    """The caller needs the member ROW, not an id: the loading plan renders the driver's
    code beneath the set's, and the conversion multiplies by its quantity."""
    c = Catalogue(db)
    pedestal = c.product("CWCX605-RL")
    wc = c.product_set("CWC605-RL", [(pedestal, 2, 0)])

    driver = driver_member(db, str(wc.id))

    assert driver.product.product_code == pedestal.product_code
    assert float(driver.quantity) == 2.0
