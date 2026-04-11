"""Tests for stock product_id filter resolution (UUID vs product_code)."""
import uuid
from unittest.mock import MagicMock

from app.services.inventory_service import _resolve_stock_product_id


def test_resolve_returns_normalized_uuid_string():
    db = MagicMock()
    u = uuid.uuid4()
    assert _resolve_stock_product_id(db, str(u)) == str(u)


def test_resolve_returns_none_for_unknown_code():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    assert _resolve_stock_product_id(db, "NO_SUCH_SKU") is None


def test_resolve_maps_product_code_to_id():
    db = MagicMock()
    row = MagicMock()
    row.id = "550e8400-e29b-41d4-a716-446655440000"
    db.query.return_value.filter.return_value.first.return_value = row
    assert _resolve_stock_product_id(db, "SRTWB241") == row.id
