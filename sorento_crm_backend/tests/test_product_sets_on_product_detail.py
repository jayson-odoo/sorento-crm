"""S4: a product detail page names the sets the product belongs to.

`SRTWCY8608`, the cistern, is a member of BOTH the S-trap and the P-trap set. So
this is always a list, never a single field, and a dealer who opens the cistern
can see which assemblies it is part of and follow the link.

UAC group G. Plan: `documentation/plans/master-data/PLAN-product-sets.md`.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet, ProductSetMember
from app.services.company_scope import company_scope, register_company_scope_listeners
from app.services.product_service import ProductService

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


def _uid(stem: str) -> str:
    return f"ZZT-{stem}-{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    session.begin_nested()
    try:
        with company_scope(session, None):
            yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def world(db: Session):
    """A cistern in two sets, a seat cover in one, and a lonely product in none."""
    company = Company(id=str(uuid.uuid4()), name=_uid("co"), code=_uid("C")[:20])
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=_uid("cat")[:50], category_name=_uid("cat")
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=_uid("u")[:20], uom_name=_uid("uom"))
    db.add_all([company, category, uom])
    db.flush()

    def product(stem: str) -> Product:
        row = Product(
            id=str(uuid.uuid4()),
            product_code=_uid(stem),
            product_name=_uid(stem),
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=Decimal("1.00"),
            company_id=company.id,
        )
        db.add(row)
        db.flush()
        return row

    cistern, seat, lonely = product("cistern"), product("seat"), product("lonely")

    sets = []
    for label, members in (("s-trap", (cistern, seat)), ("p-trap", (cistern,))):
        product_set = ProductSet(
            id=str(uuid.uuid4()),
            set_code=_uid(label),
            name=f"{label} set",
            company_id=company.id,
        )
        db.add(product_set)
        db.flush()
        for index, member in enumerate(members):
            db.add(
                ProductSetMember(
                    id=str(uuid.uuid4()),
                    product_set_id=product_set.id,
                    product_id=member.id,
                    quantity=Decimal("1"),
                    contributes_to_price=False,
                    sort_order=index,
                )
            )
        db.flush()
        sets.append(product_set)

    return {
        "company": company,
        "cistern": cistern,
        "seat": seat,
        "lonely": lonely,
        "sets": sets,
    }


def _detail(db: Session, company, product_id):
    with company_scope(db, frozenset({str(company.id)})):
        return ProductService(db).get_product(product_id)


def test_ac_g1_a_product_in_two_sets_names_both(db: Session, world):
    """AC-G.1 - a list, never a single field. The cistern serves both traps."""
    product = _detail(db, world["company"], world["cistern"].id)

    codes = {s.set_code for s in product._product_sets}
    assert codes == {world["sets"][0].set_code, world["sets"][1].set_code}


def test_ac_g1_the_refs_are_human_readable(db: Session, world):
    """No UUID reaches the UI, so the ref carries the code and the name."""
    product = _detail(db, world["company"], world["seat"].id)

    ref = product._product_sets[0]
    assert ref.set_code
    assert ref.name


def test_ac_g3_a_product_in_no_set_gets_an_empty_list(db: Session, world):
    """AC-G.3 - an empty list, so the FE renders an empty state, not a crash."""
    product = _detail(db, world["company"], world["lonely"].id)
    assert product._product_sets == []


def test_ac_g1_the_field_survives_the_response_model(db: Session, world):
    """AC-G.1 - asserted explicitly: `response_model` DROPS undeclared fields.

    The field can be populated perfectly by the service and still never reach the
    frontend, which reads as "the backend did not send it" and sends someone
    debugging the wrong half.
    """
    from app.schemas.product import ProductResponse

    product = _detail(db, world["company"], world["cistern"].id)
    serialized = ProductResponse.model_validate(product, from_attributes=True)

    assert "product_sets" in serialized.model_dump()
    assert len(serialized.product_sets) == 2
    assert {s.set_code for s in serialized.product_sets} == {
        world["sets"][0].set_code,
        world["sets"][1].set_code,
    }


def test_another_companys_set_is_not_named_on_this_products_detail(db: Session, world):
    """A set belongs to one company. Its membership must not leak across.

    Reached through the SET, which is company-scoped; `product_set_members` is
    deliberately unscoped and is only ever read through its scoped parent.
    """
    other = Company(id=str(uuid.uuid4()), name=_uid("co2"), code=_uid("C2")[:20])
    db.add(other)
    db.flush()
    foreign = ProductSet(
        id=str(uuid.uuid4()),
        set_code=_uid("foreign"),
        name="foreign set",
        company_id=other.id,
    )
    db.add(foreign)
    db.flush()
    db.add(
        ProductSetMember(
            id=str(uuid.uuid4()),
            product_set_id=foreign.id,
            product_id=world["cistern"].id,
            quantity=Decimal("1"),
            contributes_to_price=False,
            sort_order=0,
        )
    )
    db.flush()

    product = _detail(db, world["company"], world["cistern"].id)
    assert foreign.set_code not in {s.set_code for s in product._product_sets}


def test_the_sets_are_ordered_so_two_reads_agree(db: Session, world):
    """An unordered list reorders itself between reads and reads as a bug."""
    first = _detail(db, world["company"], world["cistern"].id)
    first_codes = [s.set_code for s in first._product_sets]

    db.expire_all()
    second = _detail(db, world["company"], world["cistern"].id)
    assert [s.set_code for s in second._product_sets] == first_codes
    assert first_codes == sorted(first_codes)
