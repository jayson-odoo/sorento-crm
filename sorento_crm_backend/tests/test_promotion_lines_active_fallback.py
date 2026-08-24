"""Active-first + inactive fallback for the flat promotion-line list services.

PromotionProductService.list_promotion_products and
PromotionAttachmentService.list_promotion_attachments mirror the promotions list:
  active=None  -> no gate (full catalog; FE DataGrid default)
  active=True  -> active-promotion rows first; fall back to inactive when a
                  narrowing filter is present and zero active match (fallback_used)
  active=False -> inactive-promotion rows only (no fallback)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.marketing import (
    Promotion,
    PromotionAttachment,
    PromotionGroup,
    PromotionProduct,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment
from app.services.marketing_service import (
    PromotionAttachmentService,
    PromotionProductService,
)
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _seed_promotion(db, *, description: str, active: bool) -> str:
    today = datetime.utcnow().date()
    promo = Promotion(
        id=str(uuid.uuid4()),
        description=description,
        start_date=today - timedelta(days=30),
        # Active flag AND a live window for active rows; expired window for
        # inactive rows so the active_clause (flag + today-in-window) excludes them.
        end_date=today + timedelta(days=30) if active else today - timedelta(days=1),
        is_active=active,
        access_levels=["dealer"],
    )
    db.add(promo)
    db.flush()
    return promo.id


def _seed_product(db, code: str) -> str:
    # category_id / base_uom_id are real NOT NULL FKs -- create the parents that
    # sqlite let us skip.
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=f"CAT-{code}", category_name=f"Category {code}"
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


def _seed_group(db, promotion_id: str):
    # PromotionGroup.id / PromotionProduct.promotion_group_id are UUID(as_uuid=True)
    # - pass a real UUID object, not a str.
    g = PromotionGroup(
        id=uuid.uuid4(),
        promotion_id=promotion_id,
        group_name="Default Group",
    )
    db.add(g)
    db.flush()
    return g.id


def _link_product(db, promotion_id: str, product_id: str) -> str:
    line = PromotionProduct(
        id=str(uuid.uuid4()),
        promotion_id=promotion_id,
        product_id=product_id,
        promotion_group_id=_seed_group(db, promotion_id),
    )
    db.add(line)
    db.flush()
    return line.id


def _seed_attachment(db, filename: str) -> str:
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"/tmp/{filename}",
        access_levels=["dealer"],
    )
    db.add(att)
    db.flush()
    return att.id


def _link_attachment(db, promotion_id: str, attachment_id: str) -> str:
    pa = PromotionAttachment(
        id=str(uuid.uuid4()),
        promotion_id=promotion_id,
        attachment_id=attachment_id,
        is_primary=True,
        sort_order=0,
    )
    db.add(pa)
    db.flush()
    return pa.id


# ---------------- products ----------------

def test_products_active_true_prefers_active_promotion_lines(db):
    active_promo = _seed_promotion(db, description="Active Promo", active=True)
    inactive_promo = _seed_promotion(db, description="Inactive Promo", active=False)
    prod = _seed_product(db, "SKU-1")
    active_line = _link_product(db, active_promo, prod)
    _link_product(db, inactive_promo, _seed_product(db, "SKU-2"))
    db.commit()

    res = PromotionProductService(db).list_promotion_products(
        product_ids_filter=[prod], active=True
    )
    assert [l.id for l in res["data"]] == [active_line]
    assert res["fallback_used"] is False
    # Live promotion -> not expired.
    assert res["data"][0].is_expired is False


def test_products_active_true_falls_back_to_inactive_when_no_active(db):
    inactive_promo = _seed_promotion(db, description="Inactive Promo", active=False)
    prod = _seed_product(db, "SKU-ONLY-INACTIVE")
    inactive_line = _link_product(db, inactive_promo, prod)
    db.commit()

    res = PromotionProductService(db).list_promotion_products(
        product_ids_filter=[prod], active=True
    )
    assert [l.id for l in res["data"]] == [inactive_line]
    assert res["fallback_used"] is True
    # Fallback rows are inactive promotions -> flagged expired.
    assert res["data"][0].is_expired is True


def test_products_active_false_returns_inactive_only_no_fallback(db):
    active_promo = _seed_promotion(db, description="Active Promo", active=True)
    _link_product(db, active_promo, _seed_product(db, "SKU-A"))
    db.commit()

    res = PromotionProductService(db).list_promotion_products(
        promotion_ids=[active_promo], active=False
    )
    assert res["data"] == []
    assert res["fallback_used"] is False


def test_products_active_none_no_gate_returns_all(db):
    active_promo = _seed_promotion(db, description="Active Promo", active=True)
    inactive_promo = _seed_promotion(db, description="Inactive Promo", active=False)
    prod = _seed_product(db, "SKU-SHARED")
    l1 = _link_product(db, active_promo, prod)
    l2 = _link_product(db, inactive_promo, prod)
    db.commit()

    res = PromotionProductService(db).list_promotion_products(
        product_ids_filter=[prod], active=None
    )
    assert {l.id for l in res["data"]} == {l1, l2}
    assert res["fallback_used"] is False
    by_id = {l.id: l for l in res["data"]}
    assert by_id[l1].is_expired is False  # active parent
    assert by_id[l2].is_expired is True   # inactive parent


def test_products_is_expired_serializes_through_response_schema(db):
    # The custom PromotionProductResponse.model_validate must carry is_expired.
    from app.schemas.marketing import PromotionProductResponse

    inactive_promo = _seed_promotion(db, description="Inactive Promo", active=False)
    prod = _seed_product(db, "SKU-SER")
    _link_product(db, inactive_promo, prod)
    db.commit()

    res = PromotionProductService(db).list_promotion_products(
        product_ids_filter=[prod], active=True
    )
    line = res["data"][0]
    dumped = PromotionProductResponse.model_validate(line).model_dump()
    assert dumped["is_expired"] is True


# ---------------- attachments ----------------

def test_attachments_active_true_prefers_active_promotion_rows(db):
    active_promo = _seed_promotion(db, description="Active Promo", active=True)
    inactive_promo = _seed_promotion(db, description="Inactive Promo", active=False)
    att = _seed_attachment(db, "brochure.pdf")
    active_pa = _link_attachment(db, active_promo, att)
    _link_attachment(db, inactive_promo, _seed_attachment(db, "old.pdf"))
    db.commit()

    res = PromotionAttachmentService(db).list_promotion_attachments(
        attachment_ids=[att], active=True
    )
    assert [pa.id for pa in res["data"]] == [active_pa]
    assert res["fallback_used"] is False
    assert res["data"][0].is_expired is False


def test_attachments_active_true_falls_back_to_inactive(db):
    inactive_promo = _seed_promotion(db, description="Inactive Promo", active=False)
    att = _seed_attachment(db, "legacy-flyer.pdf")
    inactive_pa = _link_attachment(db, inactive_promo, att)
    db.commit()

    res = PromotionAttachmentService(db).list_promotion_attachments(
        attachment_ids=[att], active=True
    )
    assert [pa.id for pa in res["data"]] == [inactive_pa]
    assert res["fallback_used"] is True
    assert res["data"][0].is_expired is True


def test_attachments_active_false_returns_inactive_only(db):
    active_promo = _seed_promotion(db, description="Active Promo", active=True)
    _link_attachment(db, active_promo, _seed_attachment(db, "live.pdf"))
    db.commit()

    res = PromotionAttachmentService(db).list_promotion_attachments(
        promotion_ids=[active_promo], active=False
    )
    assert res["data"] == []
    assert res["fallback_used"] is False


def test_attachments_active_none_no_gate_returns_all(db):
    active_promo = _seed_promotion(db, description="Active Promo", active=True)
    inactive_promo = _seed_promotion(db, description="Inactive Promo", active=False)
    a1 = _link_attachment(db, active_promo, _seed_attachment(db, "a1.pdf"))
    a2 = _link_attachment(db, inactive_promo, _seed_attachment(db, "a2.pdf"))
    db.commit()

    res = PromotionAttachmentService(db).list_promotion_attachments(active=None)
    assert {pa.id for pa in res["data"]} == {a1, a2}
    assert res["fallback_used"] is False
