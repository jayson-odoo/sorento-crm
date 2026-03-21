from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.error_handler import AppException
from app.services.marketing_service import PromotionService


def _build_service_with_existing(existing_rows: list[SimpleNamespace]) -> PromotionService:
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.all.return_value = existing_rows
    db.query.return_value = query
    return PromotionService(db)


def test_promo_uniqueness_conflicts_for_same_set_different_order():
    existing = [SimpleNamespace(id="p1", access_levels=["dealer", "end_user"])]
    service = _build_service_with_existing(existing)

    with pytest.raises(AppException) as exc_info:
        service._ensure_promo_code_access_levels_unique(
            promo_code="PROMO01",
            access_levels=["end_user", "dealer"],
        )

    assert exc_info.value.status_code == 409
    assert "same access types" in str(exc_info.value.detail).lower()


def test_promo_uniqueness_allows_same_code_with_different_set():
    existing = [SimpleNamespace(id="p1", access_levels=["dealer", "end_user"])]
    service = _build_service_with_existing(existing)

    # Different set: ["dealer"] is allowed alongside ["dealer", "end_user"].
    service._ensure_promo_code_access_levels_unique(
        promo_code="PROMO01",
        access_levels=["dealer"],
    )
