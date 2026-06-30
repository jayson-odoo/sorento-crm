"""Bug A2 — non-UUID path ids must 404, not 500.

`validate_uuid_path` is the reusable guard called at the top of detail GET
handlers so a malformed `{id}` returns a clean 404 instead of leaking a DB-cast
500.
"""
import pytest
from fastapi import HTTPException

from app.services.uuid_path_param import validate_uuid_path


def test_valid_uuid_passes_and_returns_canonical():
    val = "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"
    out = validate_uuid_path(val, resource="Campaign")
    assert out == val.lower()


def test_non_uuid_raises_404():
    with pytest.raises(HTTPException) as ei:
        validate_uuid_path("new", resource="Campaign")
    assert ei.value.status_code == 404


def test_garbage_raises_404():
    with pytest.raises(HTTPException) as ei:
        validate_uuid_path("not-a-uuid", resource="Form")
    assert ei.value.status_code == 404


def test_empty_raises_404():
    with pytest.raises(HTTPException) as ei:
        validate_uuid_path("", resource="Batch")
    assert ei.value.status_code == 404
