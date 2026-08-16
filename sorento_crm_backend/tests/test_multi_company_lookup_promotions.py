"""AC-B1/AC-B2/AC-B4 for `crm_marketing_promotions_list`
(PromotionService.list_promotions) and `crm_marketing_promotion_products_list`
(PromotionService.list_promotion_products). Modelled on
tests/test_attachment_company_stamp_in_list.py. Postgres only.
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.marketing_service import PromotionProductService, PromotionService

from tests._mc_lookup_seed import (
    MOCHA_ID,
    product,
    promotion,
    promotion_group,
    promotion_product,
    seed_mocha,
)
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        seed_mocha(session)
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
        yield session


# =============================================================================
# marketing_promotions_list
# =============================================================================


def test_promotions_list_ac_b1_found_in_both_companies(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    promo_sorento = promotion(db, company_id=DEFAULT_COMPANY_ID)
    promo_mocha = promotion(db, company_id=MOCHA_ID)
    grp_sorento = promotion_group(db, company_id=DEFAULT_COMPANY_ID, promotion_id=promo_sorento.id)
    grp_mocha = promotion_group(db, company_id=MOCHA_ID, promotion_id=promo_mocha.id)
    promotion_product(
        db, company_id=DEFAULT_COMPANY_ID, promotion_id=promo_sorento.id,
        promotion_group_id=grp_sorento.id, product_id=p_sorento.id,
    )
    promotion_product(
        db, company_id=MOCHA_ID, promotion_id=promo_mocha.id,
        promotion_group_id=grp_mocha.id, product_id=p_mocha.id,
    )
    db.commit()

    result = PromotionService(db).list_promotions(product_ids=[p_sorento.id, p_mocha.id])

    assert result["empty"] is False
    assert len(result["data"]) == 2
    names = {getattr(row, "company_name", None) for row in result["data"]}
    assert names == {"Sorento", "Mocha"}
    assert result.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


def test_promotions_list_ac_b2_none_in_either_company(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    # No promotion covers either product.
    db.commit()

    result = PromotionService(db).list_promotions(product_ids=[p_sorento.id, p_mocha.id])

    assert result["data"] == []
    assert result["empty"] is True
    assert result.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


def test_promotions_list_ac_b4_single_company_lookup_is_unlabelled(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    promo_sorento = promotion(db, company_id=DEFAULT_COMPANY_ID)
    grp_sorento = promotion_group(db, company_id=DEFAULT_COMPANY_ID, promotion_id=promo_sorento.id)
    promotion_product(
        db, company_id=DEFAULT_COMPANY_ID, promotion_id=promo_sorento.id,
        promotion_group_id=grp_sorento.id, product_id=p_sorento.id,
    )
    db.commit()

    result = PromotionService(db).list_promotions(product_ids=[p_sorento.id])

    assert result["empty"] is False
    assert len(result["data"]) == 1
    assert getattr(result["data"][0], "company_name", None) is None
    assert result.get("lookup_companies") is None


# =============================================================================
# marketing_promotion_products_list
# =============================================================================


def test_promotion_products_list_ac_b1_found_in_both_companies(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    promo_sorento = promotion(db, company_id=DEFAULT_COMPANY_ID)
    promo_mocha = promotion(db, company_id=MOCHA_ID)
    grp_sorento = promotion_group(db, company_id=DEFAULT_COMPANY_ID, promotion_id=promo_sorento.id)
    grp_mocha = promotion_group(db, company_id=MOCHA_ID, promotion_id=promo_mocha.id)
    promotion_product(
        db, company_id=DEFAULT_COMPANY_ID, promotion_id=promo_sorento.id,
        promotion_group_id=grp_sorento.id, product_id=p_sorento.id,
    )
    promotion_product(
        db, company_id=MOCHA_ID, promotion_id=promo_mocha.id,
        promotion_group_id=grp_mocha.id, product_id=p_mocha.id,
    )
    db.commit()

    result = PromotionProductService(db).list_promotion_products(
        product_ids_filter=[p_sorento.id, p_mocha.id]
    )

    assert result["empty"] is False
    assert len(result["data"]) == 2
    names = {getattr(row, "company_name", None) for row in result["data"]}
    assert names == {"Sorento", "Mocha"}
    assert result.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


def test_promotion_products_list_ac_b2_none_in_either_company(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    db.commit()

    result = PromotionProductService(db).list_promotion_products(
        product_ids_filter=[p_sorento.id, p_mocha.id]
    )

    assert result["data"] == []
    assert result["empty"] is True
    assert result.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


def test_promotion_products_list_ac_b2_stale_promotion_filter_still_names_both(db):
    """F1 (review round): `crm_marketing_promotion_products_list` exposes BOTH
    `promotion_ids` and `product_ids`, so an agent can hand us a stale promotion
    reference alongside a two-company product set. That early return fires with
    the product set already known, and must still name both companies."""
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    db.commit()

    result = PromotionProductService(db).list_promotion_products(
        product_ids_filter=[p_sorento.id, p_mocha.id],
        promotion_ids=["ZZT-PROMO-THAT-IS-GONE"],
    )

    assert result["data"] == []
    assert result["empty"] is True
    assert result.get("lookup_companies") == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


def test_promotion_products_list_ac_b4_single_company_lookup_is_unlabelled(db):
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    promo_sorento = promotion(db, company_id=DEFAULT_COMPANY_ID)
    grp_sorento = promotion_group(db, company_id=DEFAULT_COMPANY_ID, promotion_id=promo_sorento.id)
    promotion_product(
        db, company_id=DEFAULT_COMPANY_ID, promotion_id=promo_sorento.id,
        promotion_group_id=grp_sorento.id, product_id=p_sorento.id,
    )
    db.commit()

    result = PromotionProductService(db).list_promotion_products(
        product_ids_filter=[p_sorento.id]
    )

    assert result["empty"] is False
    assert len(result["data"]) == 1
    assert getattr(result["data"][0], "company_name", None) is None
    assert result.get("lookup_companies") is None
