"""Tests for promotion id resolution (UUID-only after promo_code removal)."""
import uuid
from unittest.mock import MagicMock

from app.services.marketing_service import _resolve_promotion_id_for_filter


def test_resolve_returns_normalized_uuid_string():
    db = MagicMock()
    u = uuid.uuid4()
    assert _resolve_promotion_id_for_filter(db, str(u)) == str(u)


def test_resolve_returns_none_for_blank():
    db = MagicMock()
    assert _resolve_promotion_id_for_filter(db, None) is None
    assert _resolve_promotion_id_for_filter(db, "") is None
    assert _resolve_promotion_id_for_filter(db, "   ") is None


def test_resolve_returns_none_for_non_uuid():
    db = MagicMock()
    assert _resolve_promotion_id_for_filter(db, "DEALER_UPDATE_20260114") is None
