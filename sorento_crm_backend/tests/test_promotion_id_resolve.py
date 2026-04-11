"""Tests for promotion id resolution (UUID vs promo_code)."""
import uuid
from unittest.mock import MagicMock

import pytest

from app.services.error_handler import AppException
from app.services.marketing_service import _resolve_promotion_id_for_filter


def test_resolve_returns_normalized_uuid_string():
    db = MagicMock()
    u = uuid.uuid4()
    assert _resolve_promotion_id_for_filter(db, str(u)) == str(u)


def test_resolve_returns_none_for_unknown_code():
    db = MagicMock()
    db.query.return_value.filter.return_value.limit.return_value.all.return_value = []
    assert _resolve_promotion_id_for_filter(db, "NO_SUCH") is None


def test_resolve_maps_single_promo_code():
    db = MagicMock()
    row = MagicMock()
    row.id = "550e8400-e29b-41d4-a716-446655440000"
    db.query.return_value.filter.return_value.limit.return_value.all.return_value = [row]
    assert _resolve_promotion_id_for_filter(db, "DEALER_UPDATE_20260114") == row.id


def test_resolve_raises_when_ambiguous_promo_code():
    db = MagicMock()
    db.query.return_value.filter.return_value.limit.return_value.all.return_value = [
        MagicMock(id="a"),
        MagicMock(id="b"),
    ]
    with pytest.raises(AppException) as exc:
        _resolve_promotion_id_for_filter(db, "DUP")
    assert exc.value.status_code == 400
