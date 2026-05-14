from types import SimpleNamespace

from app.schemas.marketing import PromotionListItemResponse


def test_promotion_list_item_response_omits_nested_payloads():
    promotion = SimpleNamespace(
        id="promo-1",
        promo_code="PROMO01",
        name="Promo 01",
        description="Short summary",
        start_date="2026-01-01T00:00:00",
        end_date="2026-12-31T00:00:00",
        is_active=True,
        access_levels=["dealer"],
        created_by=None,
        created_at="2026-03-22T15:40:00",
        updated_at="2026-03-22T15:48:51",
        products_count=4,
        products=[{"id": "line-1"}],
        promotion_groups=[{"id": "group-1"}],
    )

    payload = PromotionListItemResponse.model_validate(promotion).model_dump()

    assert payload["products_count"] == 4
    assert "products" not in payload
    assert "promotion_groups" not in payload
