"""The resolver honours the per-type serving policy (UAC E3, E4).

`/api/v1/system/references` resolve and `/api/v1/marketing/promotions` must agree
about which promotion answers "any promo for X?" -- they call the same helper, and
this pins that they do.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.api.v1.system.references import _build_promotions_for_products
from app.models.marketing import Promotion, PromotionGroup, PromotionProduct, PromotionType
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.marketing_service import PromotionService
from tests._pg_fixture import blank_session, unique_code


def _types(db):
    rows = {
        "standard": PromotionType(
            type_code="standard",
            type_name="Standard Promo",
            show_expired=True,
            expired_valid_until_year_end=True,
            is_default=True,
            match_priority=99,
        ),
        "special": PromotionType(
            type_code="special",
            type_name="Special Promo",
            show_expired=False,
            match_markers=["special"],
            match_priority=10,
        ),
        "a3_flyer": PromotionType(
            type_code="a3_flyer",
            type_name="A3 Flyer",
            show_expired=True,
            expired_max_age_days=180,
            match_markers=["a3"],
            match_priority=40,
        ),
    }
    db.add_all(rows.values())
    db.flush()
    return rows


def _product(db):
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT"), category_name="Resolver fixture"
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM"), uom_name="Piece")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        id=str(uuid.uuid4()),
        product_code=unique_code("SRTWC"),
        product_name="Resolver fixture",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=100,
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def _promo_with_product(db, description, *, start, end, promo_type, product, access=None):
    promotion = Promotion(
        id=str(uuid.uuid4()),
        description=description,
        start_date=start,
        end_date=end,
        is_active=True,
        access_levels=access or ["dealer"],
        promotion_type_id=promo_type.id,
        promotion_type_source="auto",
    )
    db.add(promotion)
    db.flush()
    group = PromotionGroup(promotion_id=promotion.id, group_name="Default", sort_order=0)
    db.add(group)
    db.flush()
    db.add(
        PromotionProduct(
            id=str(uuid.uuid4()),
            promotion_id=promotion.id,
            promotion_group_id=group.id,
            product_id=product.id,
        )
    )
    db.flush()
    return promotion


@pytest.fixture()
def srtwc286():
    """The captain's failing case: a live flyer plus an expired offer on one SKU."""
    with blank_session() as db:
        types = _types(db)
        product = _product(db)
        today = datetime.utcnow().date()
        flyer = _promo_with_product(
            db,
            "SORENTO A3 FLYER 2025-2026",
            start=today - timedelta(days=30),
            end=today + timedelta(days=60),
            promo_type=types["a3_flyer"],
            product=product,
        )
        july = _promo_with_product(
            db,
            "JULY SORENTO WC PROMO (END USER)",
            start=today - timedelta(days=90),
            end=today - timedelta(days=14),
            promo_type=types["standard"],
            product=product,
        )
        special = _promo_with_product(
            db,
            "SORENTO SPECIAL CLEARANCE",
            start=today - timedelta(days=60),
            end=today - timedelta(days=7),
            promo_type=types["special"],
            product=product,
        )
        yield db, product, flyer, july, special


def test_resolver_serves_the_expired_offer_alongside_the_live_flyer(srtwc286):  # E3
    db, product, flyer, july, special = srtwc286

    matches = _build_promotions_for_products(db, {product.id}, None)

    by_id = {m["uuid"]: m for m in matches}
    assert set(by_id) == {str(flyer.id), str(july.id)}

    live = by_id[str(flyer.id)]["display"]
    assert live["is_active"] is True
    assert live["is_expired"] is False
    assert live["expired_but_usable"] is False
    assert live["promotion_type_code"] == "a3_flyer"

    expired = by_id[str(july.id)]["display"]
    assert expired["is_active"] is False
    assert expired["is_expired"] is True
    assert expired["expired_but_usable"] is True
    assert expired["promotion_type_name"] == "Standard Promo"
    assert expired["end_date"] == july.end_date.isoformat()


def test_resolver_and_promotions_list_agree(srtwc286):  # E4
    db, product, flyer, july, _special = srtwc286

    resolved = {m["uuid"] for m in _build_promotions_for_products(db, {product.id}, None)}
    listed = {
        str(row.id)
        for row in PromotionService(db).list_promotions(
            product_ids=[product.id], serving_policy=True, limit=50
        )["data"]
    }

    assert resolved == listed == {str(flyer.id), str(july.id)}


def test_access_filter_scopes_the_candidate_set_before_the_policy(srtwc286):
    """An office-only promotion is not a dealer's candidate, so it cannot win."""
    db, product, flyer, july, _special = srtwc286
    july.access_levels = ["office"]
    db.flush()

    matches = _build_promotions_for_products(db, {product.id}, {"dealer"})

    assert {m["uuid"] for m in matches} == {str(flyer.id)}


def test_expired_type_still_answers_when_nothing_is_live(srtwc286):
    db, product, flyer, july, _special = srtwc286
    flyer.is_active = False
    db.flush()

    matches = _build_promotions_for_products(db, {product.id}, None)
    by_id = {m["uuid"]: m["display"] for m in matches}

    # The flyer's own type still honours it (180-day bound), and so does standard.
    assert by_id[str(flyer.id)]["expired_but_usable"] is True
    assert by_id[str(july.id)]["expired_but_usable"] is True
