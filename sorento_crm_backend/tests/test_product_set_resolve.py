"""S3: `check stock SRTWC8608-RL` stops answering "no such product".

`entity_resolver._probe_product` is an EXACT match on `product_code`. The flyer
code is not a product, so today the probe finds nothing and the bot tells the
customer the product does not exist. This adds the probe that answers it.

A set resolves to ONE entity carrying its members, never a fan-out of member
products. That was settled in the grill (Q19): once a set needs a price of its
own it IS an entity, and pretending otherwise costs a branch in the resolver plus
a contract change we do not avoid.

`entity_type: "product_set"` is a NEW value on the frozen `/references/resolve`
contract, so the probe is gated OFF by default and ships inert until
`sorento-crm-n8n-60` confirms. The gate is the flag, not the code: everything
below runs with it on.

UAC group E. Plan: `documentation/plans/master-data/PLAN-product-sets.md` section 4.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.company import Company
from app.models.inventory import Stock, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet, ProductSetMember
from app.services import entity_resolver
from app.services.company_scope import company_scope, register_company_scope_listeners

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


def _uid(stem: str) -> str:
    return f"ZZT-{stem}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def resolve_enabled(monkeypatch):
    """Every test here runs with the contract gate OPEN.

    The gate exists so the CRM can deploy before n8n is ready, not to make the
    behaviour optional - so it is turned on here rather than tested around.
    """
    monkeypatch.setattr(entity_resolver, "PRODUCT_SET_RESOLVE_ENABLED", True)


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
def world(db: Session):
    """The 8608 family, with stock: pedestal 40, cistern 12, seat cover 0."""
    tag = uuid.uuid4().hex[:6].upper()
    company = Company(id=str(uuid.uuid4()), name=_uid("co"), code=_uid("C")[:20])
    other = Company(id=str(uuid.uuid4()), name=_uid("co2"), code=_uid("C2")[:20])
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=_uid("cat")[:50], category_name=_uid("cat")
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=_uid("u")[:20], uom_name=_uid("uom"))
    warehouse = Warehouse(
        id=str(uuid.uuid4()), warehouse_code=_uid("wh")[:20], warehouse_name=_uid("wh")
    )
    db.add_all([company, other, category, uom, warehouse])
    db.flush()

    def product(code: str, price: str, company_id: str, discontinued: bool = False) -> Product:
        row = Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=code,
            description=f"description of {code}",
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=Decimal(price),
            is_discontinued=discontinued,
            company_id=company_id,
        )
        db.add(row)
        db.flush()
        return row

    def stock(product_row: Product, on_hand: int) -> None:
        db.add(
            Stock(
                id=str(uuid.uuid4()),
                product_id=product_row.id,
                warehouse_id=warehouse.id,
                quantity_on_hand=on_hand,
                quantity_reserved=0,
                company_id=product_row.company_id,
            )
        )
        db.flush()

    pedestal = product(f"ZZTWCX8608{tag}", "1180.00", company.id)
    cistern = product(f"ZZTWCY8608{tag}", "0.00", company.id)
    seat = product(f"ZZTWC8608{tag}-SC", "85.00", company.id)
    stock(pedestal, 40)
    stock(cistern, 12)
    stock(seat, 0)

    def make_set(code: str, company_id: str, members) -> ProductSet:
        row = ProductSet(
            id=str(uuid.uuid4()),
            set_code=code,
            name="Washdown with rimless flushing, S-trap",
            company_id=company_id,
        )
        db.add(row)
        db.flush()
        for index, (member, quantity) in enumerate(members):
            db.add(
                ProductSetMember(
                    id=str(uuid.uuid4()),
                    product_set_id=row.id,
                    product_id=member.id,
                    quantity=Decimal(str(quantity)),
                    contributes_to_price=(index == 0),
                    sort_order=index,
                )
            )
        db.flush()
        return row

    return {
        "company": company,
        "other": other,
        "warehouse": warehouse,
        "category": category,
        "uom": uom,
        "pedestal": pedestal,
        "cistern": cistern,
        "seat": seat,
        "stock": stock,
        "product": product,
        "make_set": make_set,
        "set": make_set(f"ZZTWC8608{tag}-RL", company.id, [(pedestal, 1), (cistern, 1), (seat, 1)]),
    }


def _probe(db: Session, company, token: str):
    with company_scope(db, frozenset({str(company.id)})):
        return entity_resolver._probe_product_set(db, [token])[token]


# ------------------------------------------------------------------- the shape


def test_ac_e1_a_set_code_resolves_to_exactly_one_entity(db: Session, world):
    """AC-E.1 - ONE entity carrying its members, not three top-level products."""
    hits = _probe(db, world["company"], world["set"].set_code)

    assert len(hits) == 1
    entity = hits[0]
    assert entity.entity_type == "product_set"
    assert entity.canonical_code == world["set"].set_code
    assert entity.match_field == "set_code"


def test_ac_e2_every_member_carries_its_code_and_its_own_stock(db: Session, world):
    """AC-E.2 - per-member truth is the primary answer."""
    members = _probe(db, world["company"], world["set"].set_code)[0].display["members"]

    by_code = {m["product_code"]: m for m in members}
    assert by_code[world["pedestal"].product_code]["available"] == 40
    assert by_code[world["cistern"].product_code]["available"] == 12
    assert by_code[world["seat"].product_code]["available"] == 0
    assert all(m["description"] for m in members)


def test_ac_e3_complete_sets_is_zero_and_names_the_member_that_limits_it(db, world):
    """AC-E.3 - a bare 0 reads as a bug when 40 pedestals sit in the warehouse."""
    display = _probe(db, world["company"], world["set"].set_code)[0].display

    assert display["complete_sets"] == 0
    assert display["limiting_member"] == world["seat"].product_code


def test_ac_e4_complete_sets_is_the_minimum_across_members(db: Session, world):
    """AC-E.4 - 40 / 12 / 7 with every quantity 1 gives 7."""
    seat_stock = (
        db.query(Stock).filter(Stock.product_id == world["seat"].id).one()
    )
    seat_stock.quantity_on_hand = 7
    db.flush()

    display = _probe(db, world["company"], world["set"].set_code)[0].display
    assert display["complete_sets"] == 7
    assert display["limiting_member"] == world["seat"].product_code


def test_ac_e5_a_quantity_of_two_halves_what_that_member_can_supply(db, world):
    """AC-E.5 - 7 of a part needed twice supplies floor(7/2) = 3 sets."""
    seat_stock = db.query(Stock).filter(Stock.product_id == world["seat"].id).one()
    seat_stock.quantity_on_hand = 7
    member = (
        db.query(ProductSetMember)
        .filter(
            ProductSetMember.product_set_id == world["set"].id,
            ProductSetMember.product_id == world["seat"].id,
        )
        .one()
    )
    member.quantity = Decimal("2")
    db.flush()

    assert _probe(db, world["company"], world["set"].set_code)[0].display["complete_sets"] == 3


def test_ac_e6_a_discontinued_member_does_not_end_the_set(db: Session, world):
    """AC-E.6 - the flyer code is still asked about, so the set still resolves."""
    world["seat"].is_discontinued = True
    seat_stock = db.query(Stock).filter(Stock.product_id == world["seat"].id).one()
    seat_stock.quantity_on_hand = 99
    db.flush()

    display = _probe(db, world["company"], world["set"].set_code)[0].display
    assert display["complete_sets"] == 0
    assert display["limiting_member"] == world["seat"].product_code
    discontinued = [m for m in display["members"] if m["product_code"] == world["seat"].product_code]
    assert discontinued[0]["is_discontinued"] is True


def test_ac_e9_a_stock_answer_carries_no_price(db: Session, world):
    """AC-E.9 - a stock question gets stock. Price goes through the price path."""
    display = _probe(db, world["company"], world["set"].set_code)[0].display

    flat = str(display)
    assert "price" not in display
    assert "1180" not in flat


# --------------------------------------------------------------- the neighbours


def test_ac_e7_a_member_code_alone_does_not_name_its_parent_set(db: Session, world):
    """AC-E.7 - a dealer asking for a cistern wants the cistern (D13)."""
    with company_scope(db, frozenset({str(world["company"].id)})):
        hits = entity_resolver._probe_product(db, [world["cistern"].product_code])

    resolved = hits[world["cistern"].product_code]
    assert resolved and all(e.entity_type == "product" for e in resolved)
    assert all("product_set" not in str(e.display) for e in resolved)


def test_a_token_naming_no_set_resolves_to_nothing_here(db: Session, world):
    assert _probe(db, world["company"], "ZZT-NO-SUCH-SET-CODE") == []


def test_the_code_is_matched_whitespace_and_case_insensitively(db: Session, world):
    """n8n reads the code off a PDF, so its casing and spacing are whatever printed."""
    scruffy = f" {world['set'].set_code.lower()} "
    assert len(_probe(db, world["company"], scruffy)) == 1


# ------------------------------------------------------------------- isolation


def test_ac_e8_a_scoped_caller_gets_their_own_companys_set(db: Session, world):
    """AC-E.8 - both companies carry the same codes, so this is asserted by ROW."""
    twin = world["make_set"](
        world["set"].set_code,
        world["other"].id,
        [(world["product"]("ZZT-OTHER-PED", "1.00", world["other"].id), 1)],
    )

    hits = _probe(db, world["other"], world["set"].set_code)
    assert len(hits) == 1
    assert hits[0].uuid == twin.id
    assert hits[0].uuid != world["set"].id


def test_another_companys_set_is_invisible_when_this_one_has_none(db: Session, world):
    """Fail-closed: an unknown-here code resolves to nothing, never borrowed."""
    assert _probe(db, world["other"], world["set"].set_code) == []


def test_ac_e10_the_probe_runs_through_the_orm_so_scope_is_injected(db, world):
    """AC-E.10 - raw `text()` bypasses `do_orm_execute` and leaks across companies.

    Asserted behaviourally by the two tests above; this one pins the mechanism, so
    that rewriting the probe as raw SQL for speed fails loudly here.
    """
    import ast
    import inspect

    # The docstring EXPLAINS why raw text() is forbidden, so a plain substring
    # search matches its own prose. Walk the parsed body instead: this fails only
    # on a real call.
    tree = ast.parse(inspect.getsource(entity_resolver._probe_product_set).lstrip())
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "text" not in called, "the set probe must stay ORM-only"


# ----------------------------------------------------------- the contract gate


def test_the_probe_is_gated_off_by_default(monkeypatch, db: Session, world):
    """`product_set` is a new value on a FROZEN contract.

    The CRM must be deployable before n8n has learned the type, so the default is
    off and turning it on is a deliberate act coordinated with them.
    """
    monkeypatch.setattr(entity_resolver, "PRODUCT_SET_RESOLVE_ENABLED", False)
    assert _probe(db, world["company"], world["set"].set_code) == []


def test_the_default_really_is_off_in_the_module(db: Session):
    """Read the module's own default, not the fixture's override."""
    import importlib

    fresh = importlib.reload(entity_resolver)
    try:
        assert fresh.PRODUCT_SET_RESOLVE_ENABLED is False
    finally:
        importlib.reload(entity_resolver)
