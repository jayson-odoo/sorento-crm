"""Product rows this endpoint builds itself also carry their brand.

The resolver stamps the matches it produces, but `references.py` builds product
rows of its own - the through-promotion expansion and the spec search - as plain
dicts that never pass through the resolver. Those are exactly the rows a
promotion-scoped enquiry reads, so they need the same brand the code-lookup path
now emits, or the same product routes two different ways depending on how it was
found.
"""
from __future__ import annotations

import uuid

import pytest

from app.api.v1.system.references import (
    _build_product_resolutions_from_promotions,
    _stamp_brand_on_products,
)
from app.models.base import set_company_scope
from app.models.marketing import Promotion, PromotionGroup, PromotionProduct
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners

from ._pg_fixture import blank_session, unique_code

CODE = "ZZTCBS301-WH"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, None)
        yield session


def _seed(db, *, with_brand: bool) -> tuple[str, str | None, str]:
    cat, uom = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(ProductCategory(id=cat, category_code=unique_code("C")[:50], category_name="C"))
    db.add(UnitOfMeasure(id=uom, uom_code=unique_code("U")[:20], uom_name="Each"))
    bid = None
    if with_brand:
        bid = str(uuid.uuid4())
        db.add(
            Brand(
                id=bid,
                brand_code=unique_code("CABANA")[:50],
                brand_name=unique_code("Cabana")[:150],
                company_id=DEFAULT_COMPANY_ID,
            )
        )
    pid = str(uuid.uuid4())
    db.add(
        Product(
            id=pid, product_code=CODE, product_name=CODE, category_id=cat, base_uom_id=uom,
            list_price=10, is_active=True, company_id=DEFAULT_COMPANY_ID, brand_id=bid,
        )
    )
    promo_id = str(uuid.uuid4())
    db.add(
        Promotion(
            id=promo_id,
            description=unique_code("PROMO")[:100],
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    db.flush()
    group_id = uuid.uuid4()
    db.add(
        PromotionGroup(
            id=group_id,
            promotion_id=promo_id,
            group_name="G",
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    db.flush()
    db.add(
        PromotionProduct(
            id=str(uuid.uuid4()),
            promotion_id=promo_id,
            promotion_group_id=group_id,
            product_id=pid,
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    db.flush()
    db.commit()
    return pid, bid, promo_id


def test_through_promotion_products_carry_brand(db):
    pid, bid, promo_id = _seed(db, with_brand=True)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    rows = _build_product_resolutions_from_promotions(db, "cabana", {promo_id})
    assert rows, "the promotion expansion returned no products"
    _stamp_brand_on_products(db, {"resolutions": [{"matches": rows}]})

    row = next(r for r in rows if r["uuid"] == pid)
    assert (row["display"].get("brand") or {}).get("brand_id") == bid


def test_a_promotion_product_with_no_brand_says_so_explicitly(db):
    pid, _, promo_id = _seed(db, with_brand=False)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    rows = _build_product_resolutions_from_promotions(db, "cabana", {promo_id})
    _stamp_brand_on_products(db, {"resolutions": [{"matches": rows}]})

    row = next(r for r in rows if r["uuid"] == pid)
    assert "brand" in row["display"]
    assert row["display"]["brand"] is None


def test_a_row_that_already_has_a_brand_is_left_alone(db):
    """The brand-access path already emits brand. Re-stamping must not
    overwrite it - the sweep fills gaps, it does not re-decide."""
    pid, _, _ = _seed(db, with_brand=True)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    sentinel = {"brand_id": "kept", "brand_code": "KEPT", "brand_name": "Kept"}
    payload = {
        "resolutions": [
            {"matches": [{"entity_type": "product", "uuid": pid, "display": {"brand": sentinel}}]}
        ]
    }

    _stamp_brand_on_products(db, payload)

    assert payload["resolutions"][0]["matches"][0]["display"]["brand"] == sentinel


def test_non_product_rows_are_untouched(db):
    payload = {
        "resolutions": [
            {"matches": [{"entity_type": "promotion", "uuid": str(uuid.uuid4()), "display": {}}]}
        ]
    }

    _stamp_brand_on_products(db, payload)

    assert payload["resolutions"][0]["matches"][0]["display"] == {}
