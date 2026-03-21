"""
Unit tests for ContactAccessTypeService: catalog validation, mapping resolution, default access levels.
Run with: pytest tests/test_contact_access_type_service.py -v
"""
import pytest
from unittest.mock import MagicMock, patch

from app.services.contact_access_type_service import ContactAccessTypeService
from app.services.error_handler import AppException


def test_list_active_codes_returns_fallback_when_empty():
    """When no rows in DB, list_active_codes returns fallback dealer/end_user."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    service = ContactAccessTypeService(mock_db)
    codes = service.list_active_codes()
    assert codes == ["dealer", "end_user"]


def test_list_active_codes_returns_codes_from_catalog():
    """list_active_codes returns codes from active catalog rows ordered by sort_order, code."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        ("end_user",),
        ("dealer",),
    ]
    service = ContactAccessTypeService(mock_db)
    codes = service.list_active_codes()
    assert codes == ["end_user", "dealer"]


def test_get_default_access_levels_same_as_active_codes():
    """get_default_access_levels returns same as list_active_codes (or fallback)."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        ("dealer",),
        ("end_user",),
    ]
    service = ContactAccessTypeService(mock_db)
    default = service.get_default_access_levels()
    assert default == ["dealer", "end_user"]


def test_validate_access_levels_empty_raises():
    """validate_access_levels raises when access_levels is empty."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        ("dealer",),
        ("end_user",),
    ]
    service = ContactAccessTypeService(mock_db)
    with pytest.raises(AppException) as exc_info:
        service.validate_access_levels([])
    assert exc_info.value.status_code == 400
    assert "at least one" in (exc_info.value.detail or {}).get("message", "").lower()


def test_validate_access_levels_invalid_code_raises():
    """validate_access_levels raises when a code is not in the active catalog."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        ("dealer",),
        ("end_user",),
    ]
    service = ContactAccessTypeService(mock_db)
    with pytest.raises(AppException) as exc_info:
        service.validate_access_levels(["dealer", "unknown_type"])
    assert exc_info.value.status_code == 409
    assert "unknown_type" in str(exc_info.value.detail)


def test_validate_access_levels_valid_returns_normalized():
    """validate_access_levels returns deduplicated, stripped list when all codes are valid."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        ("dealer",),
        ("end_user",),
    ]
    service = ContactAccessTypeService(mock_db)
    result = service.validate_access_levels(["  dealer  ", "end_user", "dealer"])
    assert result == ["dealer", "end_user"]


def test_resolve_respond_value_to_code_returns_none_for_empty():
    """resolve_respond_value_to_code returns None for None or blank."""
    mock_db = MagicMock()
    service = ContactAccessTypeService(mock_db)
    assert service.resolve_respond_value_to_code(None) is None
    assert service.resolve_respond_value_to_code("") is None
    assert service.resolve_respond_value_to_code("   ") is None


def test_resolve_respond_value_to_code_mapping_first():
    """resolve_respond_value_to_code uses mapping first when source_key matches."""
    mock_db = MagicMock()
    q_mapping = MagicMock()
    q_mapping.filter.return_value.first.return_value = ("dealer",)
    mock_db.query.return_value = q_mapping
    service = ContactAccessTypeService(mock_db)
    code = service.resolve_respond_value_to_code("Dealer")
    assert code == "dealer"


def test_resolve_respond_value_to_code_direct_code_when_no_mapping():
    """resolve_respond_value_to_code falls back to direct catalog code when no mapping."""
    mock_db = MagicMock()
    q_mapping = MagicMock()
    q_mapping.filter.return_value.first.return_value = None
    q_catalog = MagicMock()
    q_catalog.filter.return_value.first.return_value = ("end_user",)
    mock_db.query.side_effect = [q_mapping, q_catalog]
    service = ContactAccessTypeService(mock_db)
    code = service.resolve_respond_value_to_code("end_user")
    assert code == "end_user"


def test_resolve_respond_value_to_code_returns_none_when_unknown():
    """resolve_respond_value_to_code returns None when neither mapping nor direct code match."""
    mock_db = MagicMock()
    q_mapping = MagicMock()
    q_mapping.filter.return_value.first.return_value = None
    q_catalog = MagicMock()
    q_catalog.filter.return_value.first.return_value = None
    mock_db.query.side_effect = [q_mapping, q_catalog]
    service = ContactAccessTypeService(mock_db)
    assert service.resolve_respond_value_to_code("UnknownValue") is None


def test_list_types_for_api_returns_active_only():
    """list_types_for_api returns only active types with code, name, description, sort_order."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        ("dealer", "Dealer", "Dealer accounts", 0),
        ("end_user", "End User", None, 1),
    ]
    service = ContactAccessTypeService(mock_db)
    result = service.list_types_for_api()
    assert len(result) == 2
    assert result[0]["code"] == "dealer" and result[0]["name"] == "Dealer"
    assert result[1]["code"] == "end_user" and result[1]["name"] == "End User"
