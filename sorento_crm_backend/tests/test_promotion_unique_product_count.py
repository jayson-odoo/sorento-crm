"""The promotions list "Products" column counts PRODUCTS, not link rows.

A product legitimately appears in more than one promotion group - the same item
bundled at a different price - so ``promotion_products`` holds one row per
(product, group). Counting rows made a promotion covering 12 products report 17
under a column headed "Products", and there is no way to tell from the screen
that the extra 5 are the same items priced twice.

On the live dataset 6 promotions disagreed, and every duplicate pair was ACROSS
groups, never within one: 100 duplicate (promotion, product) pairs,
0 within-group. So the data is right and the count was wrong - which is why this
is a counting fix and not a de-duplication.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.marketing import Promotion, PromotionGroup, PromotionProduct
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _product(db) -> str:
    code = f"ZZTPC-{uuid.uuid4().hex[:6]}"
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=f"CAT-{code}", category_name=code
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"UOM-{code}", uom_name="Each")
    db.add_all([category, uom])
    db.flush()
    p = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=0,
        is_active=True,
    )
    db.add(p)
    db.flush()
    return p.id


def _promotion(db) -> str:
    promo = Promotion(id=str(uuid.uuid4()), description=f"ZZT promo {uuid.uuid4().hex[:6]}")
    db.add(promo)
    db.flush()
    return promo.id


def _group(db, promotion_id: str):
    # PromotionGroup.id / PromotionProduct.promotion_group_id are UUID(as_uuid=True)
    # - pass a real UUID object, not a str.
    g = PromotionGroup(id=uuid.uuid4(), promotion_id=promotion_id, group_name="G")
    db.add(g)
    db.flush()
    return g.id


def _link(db, promotion_id: str, product_id: str, group_id) -> None:
    db.add(
        PromotionProduct(
            id=str(uuid.uuid4()),
            promotion_id=promotion_id,
            product_id=product_id,
            promotion_group_id=group_id,
        )
    )
    db.flush()


def _count(db, promotion_id: str) -> int:
    from app.services.marketing_service import PromotionService

    return PromotionService(db).get_promotion(promotion_id).products_count


def test_a_product_in_two_groups_counts_once(db):
    """The exact live shape: one product, two groups, two link rows."""
    pid, prod = _promotion(db), None
    prod = _product(db)
    _link(db, pid, prod, _group(db, pid))
    _link(db, pid, prod, _group(db, pid))
    db.commit()

    assert _count(db, pid) == 1, "the same product in two groups is still one product"


def test_distinct_products_are_all_counted(db):
    """Guard the other direction - de-duplicating must not collapse real products."""
    pid = _promotion(db)
    a, b, c = _product(db), _product(db), _product(db)
    g1, g2 = _group(db, pid), _group(db, pid)
    _link(db, pid, a, g1)
    _link(db, pid, b, g1)
    _link(db, pid, c, g2)
    db.commit()

    assert _count(db, pid) == 3


def test_the_mixed_case_matching_the_live_data(db):
    """Three products, five rows: two of them priced in a second group."""
    pid = _promotion(db)
    a, b, c = _product(db), _product(db), _product(db)
    g1, g2 = _group(db, pid), _group(db, pid)
    for prod in (a, b, c):
        _link(db, pid, prod, g1)
    _link(db, pid, a, g2)
    _link(db, pid, b, g2)
    db.commit()

    rows = (
        db.query(PromotionProduct).filter(PromotionProduct.promotion_id == pid).count()
    )
    assert rows == 5, "fixture should hold five link rows"
    assert _count(db, pid) == 3, "but only three products"


def test_a_promotion_with_no_products_counts_zero(db):
    pid = _promotion(db)
    db.commit()

    assert _count(db, pid) == 0


def test_the_list_agrees_with_the_detail(db):
    """Two separate code paths build this number. They disagreeing is the bug
    class that produced the original mismatch, so pin them together."""
    from app.services.marketing_service import PromotionService

    pid = _promotion(db)
    a, b = _product(db), _product(db)
    g1, g2 = _group(db, pid), _group(db, pid)
    _link(db, pid, a, g1)
    _link(db, pid, b, g1)
    _link(db, pid, a, g2)
    db.commit()

    svc = PromotionService(db)
    detail = svc.get_promotion(pid).products_count
    listed = next(
        p.products_count
        for p in svc.list_promotions(page=1, limit=200)["data"]
        if str(p.id) == str(pid)
    )
    assert detail == listed == 2
