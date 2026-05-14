"""Schema test: PromotionResponse exposes attachments inline."""
from types import SimpleNamespace

from app.schemas.marketing import PromotionResponse


def _build_promotion_namespace(attachments: list) -> SimpleNamespace:
    return SimpleNamespace(
        id="promo-1",
        description="Demo",
        start_date="2026-01-01",
        end_date="2026-12-31",
        is_active=True,
        access_levels=["dealer"],
        created_by=None,
        created_at="2026-03-22T15:40:00",
        updated_at="2026-03-22T15:48:51",
        products_count=0,
        products=None,
        promotion_groups=None,
        attachments=attachments,
    )


def test_attachments_field_defaults_to_empty_list():
    promotion = _build_promotion_namespace([])
    payload = PromotionResponse.model_validate(promotion).model_dump()
    assert payload["attachments"] == []


def test_attachments_field_serializes_inline_rows():
    attachment_row = SimpleNamespace(
        id="att-1",
        promotion_id="promo-1",
        attachment_id="file-1",
        is_primary=True,
        sort_order=0,
        created_at=None,
        created_by=None,
        synced_to_excel=False,
        last_synced_to_excel=None,
        updated_at=None,
        promotion=None,
        attachment=None,
    )
    promotion = _build_promotion_namespace([attachment_row])

    payload = PromotionResponse.model_validate(promotion).model_dump()

    assert len(payload["attachments"]) == 1
    assert payload["attachments"][0]["id"] == "att-1"
    assert payload["attachments"][0]["is_primary"] is True
