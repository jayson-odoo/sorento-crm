"""Tests for `_is_uuid_param` / `_validate_uuid_param` introduced for the
UUID-only domain-tool surface. See `sorento_crm_mcp/server.py`.
"""
from __future__ import annotations

import json

import pytest

from sorento_crm_mcp.server import _is_uuid_param, _validate_uuid_param


_VALID = "550e8400-e29b-41d4-a716-446655440000"
_VALID2 = "550e8400-e29b-41d4-a716-446655440001"


def test_is_uuid_param_recognises_id_suffix():
    assert _is_uuid_param("product_id")
    assert _is_uuid_param("order_id")
    assert _is_uuid_param("product_ids")
    assert _is_uuid_param("customer_ids")
    assert _is_uuid_param("attachment_ids")


def test_is_uuid_param_skips_respond_io_identifiers():
    assert not _is_uuid_param("contact_id")
    assert not _is_uuid_param("space_id")


def test_is_uuid_param_ignores_unrelated_params():
    assert not _is_uuid_param("query")
    assert not _is_uuid_param("page")
    assert not _is_uuid_param("limit")
    assert not _is_uuid_param("status")


def test_validate_accepts_none_and_empty():
    assert _validate_uuid_param("product_ids", None) is None
    assert _validate_uuid_param("product_ids", "") == ""


def test_validate_accepts_single_uuid_string():
    assert _validate_uuid_param("product_id", _VALID) == _VALID


def test_validate_accepts_list_of_uuids():
    value = [_VALID, _VALID2]
    assert _validate_uuid_param("product_ids", value) == value


def test_validate_accepts_csv_string():
    csv = f"{_VALID},{_VALID2}"
    assert _validate_uuid_param("product_ids", csv) == csv


def test_validate_accepts_json_array_string():
    arr = json.dumps([_VALID, _VALID2])
    assert _validate_uuid_param("product_ids", arr) == arr


def test_validate_rejects_non_uuid_string():
    with pytest.raises(ValueError) as excinfo:
        _validate_uuid_param("product_ids", "not-a-uuid")
    payload = json.loads(str(excinfo.value))
    assert payload["code"] == "INVALID_UUID"
    assert payload["param"] == "product_ids"
    assert "not-a-uuid" in payload["message"]


def test_validate_rejects_mixed_csv_with_one_bad_value():
    csv = f"{_VALID},bogus,{_VALID2}"
    with pytest.raises(ValueError) as excinfo:
        _validate_uuid_param("customer_ids", csv)
    payload = json.loads(str(excinfo.value))
    assert payload["code"] == "INVALID_UUID"
    assert payload["param"] == "customer_ids"


def test_validate_rejects_list_with_one_bad_value():
    with pytest.raises(ValueError):
        _validate_uuid_param("product_ids", [_VALID, "bogus"])
