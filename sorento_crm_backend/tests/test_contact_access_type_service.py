"""
Unit tests for ContactAccessTypeService: catalog validation, default access levels.

Allowed access type codes are whatever is active in the contact access type catalog (admin UI) - not
fixed to any two values. Tests use ``dealer`` / ``end_user`` as example rows unless stated otherwise.

The only special case in code is ``_FALLBACK_DEFAULT_CODES`` when the catalog table has no active rows yet
(bootstrap / pre-migration). That fallback is asserted in ``test_list_active_codes_returns_fallback_when_empty``.

The pivot-based contact ↔ access-type assignment (set/get/resolve by respond_io_id+space_id) is covered
in ``test_respond_contact_access_types_m2m.py`` against an in-memory SQLite session.

Run with: pytest tests/test_contact_access_type_service.py -v
"""
import pytest
from unittest.mock import MagicMock

from app.services.contact_access_type_service import ContactAccessTypeService
from app.services.error_handler import AppException


def test_list_active_codes_returns_fallback_when_empty():
    """When no active catalog rows, service uses bootstrap fallback (see contact_access_type_service._FALLBACK_DEFAULT_CODES)."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    service = ContactAccessTypeService(mock_db)
    codes = service.list_active_codes()
    assert codes == ["dealer", "end_user"]


def test_list_active_codes_returns_codes_from_catalog():
    """list_active_codes returns whatever codes are in the active catalog (ordered by sort_order, code) - not a fixed pair."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        ("end_user",),
        ("manager",),
        ("dealer",),
    ]
    service = ContactAccessTypeService(mock_db)
    codes = service.list_active_codes()
    assert codes == ["end_user", "manager", "dealer"]


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
    raw_detail = exc_info.value.detail
    msg = (
        str(raw_detail.get("message", "") or "")
        if isinstance(raw_detail, dict)
        else str(raw_detail or "")
    )
    assert "at least one" in msg.lower()


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
    """validate_access_levels returns deduplicated, stripped list when all codes are in the active catalog."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        ("dealer",),
        ("end_user",),
    ]
    service = ContactAccessTypeService(mock_db)
    result = service.validate_access_levels(["  dealer  ", "end_user", "dealer"])
    assert result == ["dealer", "end_user"]


def test_validate_access_levels_accepts_any_catalog_code():
    """Validation allows any code present in the catalog (e.g. manager) - not only legacy example codes."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        ("manager",),
        ("dealer",),
    ]
    service = ContactAccessTypeService(mock_db)
    assert service.validate_access_levels(["manager", "dealer"]) == ["manager", "dealer"]


def test_list_types_for_api_returns_active_only():
    """list_types_for_api returns only active types with code, name, description, sort_order, keywords."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        ("dealer", "Dealer", "Dealer accounts", 0, ["reseller", "shop"]),
        ("end_user", "End User", None, 1, []),
    ]
    service = ContactAccessTypeService(mock_db)
    result = service.list_types_for_api()
    assert len(result) == 2
    assert result[0]["code"] == "dealer" and result[0]["name"] == "Dealer"
    assert result[0]["keywords"] == ["reseller", "shop"]
    assert result[1]["code"] == "end_user" and result[1]["name"] == "End User"
    assert result[1]["keywords"] == []


