"""S3: `check stock SRTWC8608-RL` stops answering "no such product".

`entity_resolver._probe_product` is an EXACT match on `product_code`. The flyer
code is not a product, so today the probe finds nothing and the bot tells the
customer the product does not exist. This adds the probe that answers it.

A set resolves to ONE entity carrying its members, never a fan-out of member
products. That was settled in the grill (Q19): once a set needs a price of its
own it IS an entity, and pretending otherwise costs a branch in the resolver plus
a contract change we do not avoid.

`entity_type: "product_set"` is a NEW value on the frozen `/references/resolve`
contract. It resolves unconditionally - there is no flag, so every test below
exercises what any caller sees from the moment this ships.

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


def test_every_member_carries_its_uuid(db: Session, world):
    """n8n's fan-out needs the MEMBER'S uuid, not the set's - `matches[].uuid`
    already names the set. Asserted against the real seeded row, not merely
    "is not None"."""
    members = _probe(db, world["company"], world["set"].set_code)[0].display["members"]

    by_code = {m["product_code"]: m for m in members}
    assert by_code[world["pedestal"].product_code]["uuid"] == world["pedestal"].id
    assert by_code[world["cistern"].product_code]["uuid"] == world["cistern"].id
    assert by_code[world["seat"].product_code]["uuid"] == world["seat"].id


def test_member_keys_are_the_frozen_five_plus_uuid(db: Session, world):
    """Frozen-contract guard - `uuid` is ADDED, every existing key stays."""
    members = _probe(db, world["company"], world["set"].set_code)[0].display["members"]

    for member in members:
        assert set(member.keys()) == {
            "product_code",
            "description",
            "quantity",
            "available",
            "is_discontinued",
            "uuid",
        }


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


def test_a_scoped_callers_member_uuids_never_cross_companies(db: Session, world):
    """Same-code twin, member-id direction: each company's caller gets its OWN
    members' product ids, never the other company's."""
    other_product = world["product"]("ZZT-OTHER-PED", "1.00", world["other"].id)
    twin = world["make_set"](world["set"].set_code, world["other"].id, [(other_product, 1)])

    hits = _probe(db, world["company"], world["set"].set_code)
    assert len(hits) == 1
    member_ids = {m["uuid"] for m in hits[0].display["members"]}
    assert member_ids == {world["pedestal"].id, world["cistern"].id, world["seat"].id}
    assert other_product.id not in member_ids

    other_hits = _probe(db, world["other"], world["set"].set_code)
    assert len(other_hits) == 1
    assert other_hits[0].uuid == twin.id
    other_member_ids = {m["uuid"] for m in other_hits[0].display["members"]}
    assert other_member_ids == {other_product.id}


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


# ---------------------------------------------------- through the real dispatcher
#
# Every test above calls `entity_resolver._probe_product_set` directly, which
# proves the probe is correct but not that anything actually REACHES it: the
# `/references/resolve` route and every real caller go through
# `resolve_references`, which dispatches Tier 1 via `_TIER1_PROBES` - a table
# this probe is registered in but that no test here exercised. Wiring the table
# entry wrong (wrong probe, wrong `produces` set, entry missing entirely) would
# have shipped invisibly: every AC-E test above would still pass.


def test_the_real_dispatcher_resolves_a_set_code_to_one_product_set_entity(
    db: Session, world
):
    """`resolve_references` is what `/references/resolve` calls. Going through it
    (rather than `_probe_product_set` directly) is what proves the `_TIER1_PROBES`
    entry actually wires the probe in."""
    with company_scope(db, frozenset({str(world["company"].id)})):
        result = entity_resolver.resolve_references(
            db,
            [world["set"].set_code],
            enable_prefix_fallback=False,
            enable_embedding_fallback=False,
        )

    assert len(result.resolutions) == 1
    resolution = result.resolutions[0]
    assert resolution.resolved
    assert len(resolution.matches) == 1

    entity = resolution.matches[0]
    assert entity.entity_type == "product_set"
    assert entity.canonical_code == world["set"].set_code

    member_codes = {m["product_code"] for m in entity.display["members"]}
    assert member_codes == {
        world["pedestal"].product_code,
        world["cistern"].product_code,
        world["seat"].product_code,
    }
    # D7 - a stock/identity answer carries no price, through the real dispatch
    # path too, not only the direct probe call.
    assert "price" not in entity.display
    assert "1180" not in str(entity.display)


def test_a_set_match_carries_its_company(db: Session, world):
    """Change 2 - `product_set` is registered in `_company_scoped_models`, so a
    set match is stamped exactly like every other entity type. Only company
    attribution is checked here, not which rows come back (that is AC-E.8)."""
    with company_scope(db, frozenset({str(world["company"].id)})):
        result = entity_resolver.resolve_references(
            db,
            [world["set"].set_code],
            enable_prefix_fallback=False,
            enable_embedding_fallback=False,
        )

    entity = result.resolutions[0].matches[0]
    assert entity.company_id == world["company"].id
    assert entity.company_name == world["company"].name


# --------------------------------------------------------- n8n's "product" hint
#
# n8n sends `domain_hint="product"` for a flyer code - it has no reason to know
# the glossary term "product_set". `_ENTITY_TYPE_ALIASES` already maps
# `set` / `kit` / `product_set` to the set probe, but a caller that filters
# `allowed_entity_types=["product"]` never gets there: `_TIER1_PROBES` only runs
# a probe when its `produces` set intersects `allowed`, and `product` alone does
# not intersect `{"product_set"}`. `_expand_entity_types` is what widens it.


def test_a_product_hint_reaches_the_set_probe(db: Session, world):
    """The requirement in the user's own words: WC7605 with hint `product`."""
    with company_scope(db, frozenset({str(world["company"].id)})):
        result = entity_resolver.resolve_references(
            db,
            [world["set"].set_code],
            allowed_entity_types=["product"],
            enable_prefix_fallback=False,
            enable_embedding_fallback=False,
        )

    assert len(result.resolutions) == 1
    resolution = result.resolutions[0]
    assert resolution.resolved
    assert len(resolution.matches) == 1
    entity = resolution.matches[0]
    assert entity.entity_type == "product_set"
    assert entity.canonical_code == world["set"].set_code
    member_codes = {m["product_code"] for m in entity.display["members"]}
    assert member_codes == {
        world["pedestal"].product_code,
        world["cistern"].product_code,
        world["seat"].product_code,
    }


def test_a_member_code_alone_under_a_product_hint_still_names_no_set(db: Session, world):
    """D13 regression guard, specifically against the new expansion: widening
    `allowed_entity_types=["product"]` to also reach the set probe must not make
    a MEMBER's own code answer with its parent set. A dealer asking for the
    cistern by its own code still gets only the cistern."""
    with company_scope(db, frozenset({str(world["company"].id)})):
        result = entity_resolver.resolve_references(
            db,
            [world["cistern"].product_code],
            allowed_entity_types=["product"],
            enable_prefix_fallback=False,
            enable_embedding_fallback=False,
        )

    assert len(result.resolutions) == 1
    resolution = result.resolutions[0]
    assert resolution.matches
    assert all(m.entity_type == "product" for m in resolution.matches)
    assert all("product_set" not in str(m.display) for m in resolution.matches)
