"""S0: the product-set tables and the computed price.

A Product Set is a code that names an assembly Sorento sells as one thing and
stocks as several - `SRTWC8608-RL` is a pedestal, a cistern and a seat cover. It
is not a `products` row, is never stocked or costed, and is never ordered.

UAC: `documentation/plans/master-data/product-sets-acceptance-criteria.md`,
groups C (model and scope) and D (price). Plan: `PLAN-product-sets.md`.

Every row here is created with a `ZZT` prefix and the assertions filter on it -
the tables under test are new and therefore empty, but `products`, `companies`
and `product_categories` are not, and this suite runs against a copy of real
data.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.company import Company
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet, ProductSetMember
from app.services.company_scope import company_scope, register_company_scope_listeners
from app.services.product_set_service import resolve_set_price

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


def _uid(stem: str) -> str:
    return f"ZZT-{stem}-{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def db() -> Session:
    """A session whose writes are DISCARDED, even when the code under test commits.

    `SessionLocal()` + `begin_nested()` is not enough and it silently leaks: the
    service calls `db.commit()`, which commits the OUTER transaction rather than
    releasing a savepoint, so the fixture's rollback has nothing left to undo and
    every ZZT row lands in the shared database for good. That is what happened
    here - 99 sets, 407 products and 204 companies had to be swept back out.

    Binding to a connection that already holds a transaction, with
    `join_transaction_mode="create_savepoint"`, is what makes a committing test
    safe: its commits land on a savepoint inside the outer transaction, visible
    to the test and to the code under it, and the outer rollback still discards
    everything. Same approach as `tests/_pg_fixture.blank_session`.
    """
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


@pytest.fixture()
def scaffold(db: Session):
    """Two companies, and the category + UOM every product row needs.

    Seeded here rather than read off existing rows: CI's database has no data,
    so a test that reaches for an existing category passes locally and fails
    there.
    """
    companies = {}
    for key in ("a", "b"):
        company = Company(id=str(uuid.uuid4()), name=_uid(f"co-{key}"), code=_uid(f"C{key}")[:20])
        db.add(company)
        companies[key] = company
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=_uid("cat")[:50], category_name=_uid("cat")
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=_uid("u")[:20], uom_name=_uid("uom"))
    db.add_all([category, uom])
    db.flush()
    return {"companies": companies, "category": category, "uom": uom}


def _product(db: Session, scaffold, *, price, company, code: str | None = None,
             discontinued: bool = False) -> Product:
    product = Product(
        id=str(uuid.uuid4()),
        product_code=code or _uid("p"),
        product_name=_uid("name"),
        category_id=scaffold["category"].id,
        base_uom_id=scaffold["uom"].id,
        list_price=Decimal(str(price)),
        is_discontinued=discontinued,
        company_id=company.id,
    )
    db.add(product)
    db.flush()
    return product


def _set_with(db: Session, scaffold, company, members) -> ProductSet:
    """`members` is a list of (list_price, contributes_to_price, quantity)."""
    product_set = ProductSet(
        id=str(uuid.uuid4()),
        set_code=_uid("set"),
        name=_uid("set-name"),
        company_id=company.id,
    )
    db.add(product_set)
    db.flush()
    for index, (price, contributes, quantity) in enumerate(members):
        db.add(
            ProductSetMember(
                id=str(uuid.uuid4()),
                product_set_id=product_set.id,
                product_id=_product(db, scaffold, price=price, company=company).id,
                quantity=Decimal(str(quantity)),
                contributes_to_price=contributes,
                sort_order=index,
            )
        )
    db.flush()
    db.refresh(product_set)
    return product_set


# --------------------------------------------------------------- group C: model


def test_ac_c1_migration_creates_both_tables_explicitly():
    """AC-C.1 - the migration issues real DDL for both tables.

    New tables are absent on a database built by `create_all`, so an
    autogenerate stub that forgets `op.create_table` ships a model with no
    table behind it and every read 500s on `UndefinedTable`.
    """
    from pathlib import Path

    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    migrations = list(versions.glob("*product_sets*.py"))
    assert migrations, "no product-sets migration found in alembic/versions"
    source = migrations[0].read_text()
    assert 'op.create_table(\n        "product_sets"' in source or \
           "op.create_table(\n        'product_sets'" in source, "product_sets not created explicitly"
    assert "product_set_members" in source


def test_ac_c2_set_code_is_unique_per_company_not_globally(db: Session, scaffold):
    """AC-C.2 - SRT and MOCHA both legitimately carry `SRTWC8608-RL`."""
    shared_code = _uid("dup")
    for key in ("a", "b"):
        db.add(
            ProductSet(
                id=str(uuid.uuid4()),
                set_code=shared_code,
                name=_uid("n"),
                company_id=scaffold["companies"][key].id,
            )
        )
    db.flush()  # no IntegrityError: the unique index is (company_id, set_code)

    db.add(
        ProductSet(
            id=str(uuid.uuid4()),
            set_code=shared_code,
            name=_uid("n"),
            company_id=scaffold["companies"]["a"].id,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


def test_ac_c3_a_scoped_reader_never_sees_the_other_companys_sets(db: Session, scaffold):
    """AC-C.3 - the scope filter is fail-closed, not absent."""
    a, b = scaffold["companies"]["a"], scaffold["companies"]["b"]
    set_a = _set_with(db, scaffold, a, [(100, True, 1)])
    set_b = _set_with(db, scaffold, b, [(200, True, 1)])

    with company_scope(db, frozenset({str(b.id)})):
        visible = {
            row.id
            for row in db.query(ProductSet).filter(
                ProductSet.set_code.in_([set_a.set_code, set_b.set_code])
            )
        }
    assert set_b.id in visible
    assert set_a.id not in visible


def test_ac_c4_deleting_a_member_product_is_refused(db: Session, scaffold):
    """AC-C.4 - RESTRICT, so a set can never hold a dangling member."""
    company = scaffold["companies"]["a"]
    product_set = _set_with(db, scaffold, company, [(100, True, 1)])
    member = product_set.members[0]
    product = db.query(Product).filter(Product.id == member.product_id).one()

    db.delete(product)
    with pytest.raises(IntegrityError):
        db.flush()


def test_ac_c5_deleting_a_set_takes_its_members_and_no_product(db: Session, scaffold):
    """AC-C.5 - CASCADE on the set, and the products are untouched."""
    company = scaffold["companies"]["a"]
    product_set = _set_with(db, scaffold, company, [(100, True, 1), (85, False, 1)])
    member_ids = [m.id for m in product_set.members]
    product_ids = [m.product_id for m in product_set.members]

    db.delete(product_set)
    db.flush()

    assert db.query(ProductSetMember).filter(ProductSetMember.id.in_(member_ids)).count() == 0
    assert db.query(Product).filter(Product.id.in_(product_ids)).count() == len(product_ids)


def test_ac_c6_one_product_can_belong_to_two_sets(db: Session, scaffold):
    """AC-C.6 - `SRTWCY8608` is in both the S-trap and the P-trap set."""
    company = scaffold["companies"]["a"]
    cistern = _product(db, scaffold, price=0, company=company)
    sets = []
    for _ in range(2):
        product_set = ProductSet(
            id=str(uuid.uuid4()), set_code=_uid("set"), name=_uid("n"), company_id=company.id
        )
        db.add(product_set)
        db.flush()
        db.add(
            ProductSetMember(
                id=str(uuid.uuid4()),
                product_set_id=product_set.id,
                product_id=cistern.id,
                quantity=Decimal("1"),
                contributes_to_price=False,
                sort_order=0,
            )
        )
        sets.append(product_set)
    db.flush()

    holders = (
        db.query(ProductSetMember.product_set_id)
        .filter(ProductSetMember.product_id == cistern.id)
        .all()
    )
    assert {row[0] for row in holders} == {s.id for s in sets}


def test_ac_c6b_the_same_product_cannot_be_added_to_one_set_twice(db: Session, scaffold):
    """AC-C.6 - membership is a set, not a bag."""
    company = scaffold["companies"]["a"]
    product_set = _set_with(db, scaffold, company, [(100, True, 1)])
    db.add(
        ProductSetMember(
            id=str(uuid.uuid4()),
            product_set_id=product_set.id,
            product_id=product_set.members[0].product_id,
            quantity=Decimal("1"),
            contributes_to_price=False,
            sort_order=1,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


def test_ac_c7_quantity_keeps_its_fraction(db: Session, scaffold):
    """AC-C.7 - NUMERIC, never Integer. An Integer column truncates silently."""
    company = scaffold["companies"]["a"]
    product_set = _set_with(db, scaffold, company, [(100, True, "1.5")])
    db.expire_all()
    reloaded = db.query(ProductSetMember).filter(
        ProductSetMember.product_set_id == product_set.id
    ).one()
    assert reloaded.quantity == Decimal("1.5")


# --------------------------------------------------------------- group D: price


def test_ac_d1_price_is_the_ticked_member_only(db: Session, scaffold):
    """AC-D.1 - 8608: pedestal 1180 ticked, cistern 0, seat cover 85."""
    product_set = _set_with(
        db, scaffold, scaffold["companies"]["a"],
        [(1180, True, 1), (0, False, 1), (85, False, 1)],
    )
    assert resolve_set_price(product_set).computed == Decimal("1180.00")


def test_ac_d2_a_two_member_basis_sums_and_excludes_the_rest(db: Session, scaffold):
    """AC-D.2 - the basis is configurable; the pedestal's 1180 is excluded."""
    product_set = _set_with(
        db, scaffold, scaffold["companies"]["a"],
        [(1180, False, 1), (40, True, 1), (85, True, 1)],
    )
    assert resolve_set_price(product_set).computed == Decimal("125.00")


def test_ac_d3_quantity_multiplies_a_contributing_member(db: Session, scaffold):
    """AC-D.3 - two of a part means twice its list price."""
    product_set = _set_with(
        db, scaffold, scaffold["companies"]["a"], [(85, True, 2), (1180, False, 1)]
    )
    assert resolve_set_price(product_set).computed == Decimal("170.00")


def test_ac_d4_the_override_wins_and_the_computed_figure_survives(db: Session, scaffold):
    """AC-D.4 - both travel, so the FE can badge the override against what it replaced."""
    product_set = _set_with(
        db, scaffold, scaffold["companies"]["a"], [(1180, True, 1), (85, True, 1)]
    )
    product_set.list_price_override = Decimal("1180.00")
    db.flush()

    price = resolve_set_price(product_set)
    assert price.resolved == Decimal("1180.00")
    assert price.override == Decimal("1180.00")
    assert price.computed == Decimal("1265.00")
    assert price.is_overridden is True


def test_ac_d5_the_price_follows_a_members_edit_with_no_backfill(db: Session, scaffold):
    """AC-D.5 - computed at read time, never stored."""
    company = scaffold["companies"]["a"]
    product_set = _set_with(db, scaffold, company, [(1180, True, 1)])
    assert resolve_set_price(product_set).computed == Decimal("1180.00")

    product = db.query(Product).filter(
        Product.id == product_set.members[0].product_id
    ).one()
    product.list_price = Decimal("1200.00")
    db.flush()
    db.expire_all()

    reloaded = db.query(ProductSet).filter(ProductSet.id == product_set.id).one()
    assert resolve_set_price(reloaded).computed == Decimal("1200.00")


def test_ac_d5b_no_member_ticked_means_absent_not_zero(db: Session, scaffold):
    """AC-B.4 / AC-D.6 - a price of zero and a missing price are different facts.

    The dealer-kit pricing work already paid for this one: a list price of zero
    is missing data, not a free product.
    """
    product_set = _set_with(
        db, scaffold, scaffold["companies"]["a"], [(1180, False, 1), (85, False, 1)]
    )
    price = resolve_set_price(product_set)
    assert price.computed is None
    assert price.resolved is None
    assert price.reason == "no_member_contributes"


def test_ac_d5c_a_set_with_no_members_has_no_price(db: Session, scaffold):
    """A set mid-authoring must not claim a price of 0.00."""
    product_set = _set_with(db, scaffold, scaffold["companies"]["a"], [])
    price = resolve_set_price(product_set)
    assert price.computed is None
    assert price.reason == "no_members"


def test_ac_d6_every_price_field_is_present_on_the_response(db: Session, scaffold):
    """AC-D.6 - asserted explicitly, because `response_model` drops undeclared fields."""
    product_set = _set_with(
        db, scaffold, scaffold["companies"]["a"], [(1180, True, 1)]
    )
    payload = resolve_set_price(product_set).as_dict()
    assert set(payload) == {"computed", "override", "resolved", "is_overridden", "reason"}
