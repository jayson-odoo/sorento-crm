"""Service-level tests for ComplaintRootCauseService + ComplaintResolutionService.

Verifies CRUD happy path, name-uniqueness 409, and 409-with-friendly-message
when delete is blocked by referencing complaints.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from sqlalchemy.orm import Session

from tests._pg_fixture import pg_session

from app.models.complaints import Complaint
from app.models.complaint_master_data import (
    ComplaintRootCause,
    ComplaintResolution,
)
from app.schemas.complaint_master_data import (
    ComplaintRootCauseCreate,
    ComplaintRootCauseUpdate,
    ComplaintResolutionCreate,
    ComplaintResolutionUpdate,
)
from app.services.complaint_master_data_service import (
    ComplaintRootCauseService,
    ComplaintResolutionService,
)
from app.services.error_handler import AppException


@pytest.fixture(autouse=True)
def _clean_state():
    from sqlalchemy import text

    from app.database import engine

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM complaints WHERE complaint_number LIKE 'TEST-RC-%'"))
        conn.execute(text("DELETE FROM complaint_root_causes WHERE name LIKE 'Test RC%'"))
        conn.execute(text("DELETE FROM complaint_resolutions WHERE name LIKE 'Test RES%'"))
        conn.commit()
    yield
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM complaints WHERE complaint_number LIKE 'TEST-RC-%'"))
        conn.execute(text("DELETE FROM complaint_root_causes WHERE name LIKE 'Test RC%'"))
        conn.execute(text("DELETE FROM complaint_resolutions WHERE name LIKE 'Test RES%'"))
        conn.commit()


@pytest.fixture
def db() -> Iterator[Session]:
    with pg_session() as s:
        yield s


def test_create_get_update_delete_root_cause(db: Session) -> None:
    service = ComplaintRootCauseService(db)
    payload = ComplaintRootCauseCreate(name="Test RC happy", description="A reason", is_active=True)
    row = service.create_root_cause(payload)
    assert row.id and row.name == "Test RC happy"

    fetched = service.get_root_cause(row.id)
    assert fetched.id == row.id

    updated = service.update_root_cause(
        row.id, ComplaintRootCauseUpdate(description="Updated reason")
    )
    assert updated.description == "Updated reason"

    listing = service.list_root_causes(query="Test RC happy")
    assert listing["pagination"]["total"] == 1
    assert listing["data"][0]["complaint_count"] == 0

    result = service.delete_root_cause(row.id)
    assert "deleted" in result["message"]
    assert db.query(ComplaintRootCause).filter(ComplaintRootCause.id == row.id).first() is None


def test_create_root_cause_rejects_duplicate_name_case_insensitive(db: Session) -> None:
    service = ComplaintRootCauseService(db)
    service.create_root_cause(ComplaintRootCauseCreate(name="Test RC dup"))

    with pytest.raises(AppException) as exc_info:
        service.create_root_cause(ComplaintRootCauseCreate(name="test rc dup"))
    assert exc_info.value.status_code == 409


def test_delete_root_cause_blocked_when_in_use_with_friendly_message(db: Session) -> None:
    service = ComplaintRootCauseService(db)
    rc = service.create_root_cause(ComplaintRootCauseCreate(name="Test RC blocked"))
    db.commit()

    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_number="TEST-RC-BLOCK",
        status="new",
        root_cause_id=rc.id,
    )
    db.add(complaint)
    db.commit()

    try:
        with pytest.raises(AppException) as exc_info:
            service.delete_root_cause(rc.id)
        assert exc_info.value.status_code == 409
        detail = exc_info.value.detail if hasattr(exc_info.value, "detail") else str(exc_info.value)
        msg = detail.get("message") if isinstance(detail, dict) else str(detail)
        assert "Cannot delete" in str(msg)
        assert "1 complaint" in str(msg)
    finally:
        db.delete(complaint)
        db.commit()


def test_create_get_update_delete_resolution(db: Session) -> None:
    service = ComplaintResolutionService(db)
    row = service.create_resolution(
        ComplaintResolutionCreate(name="Test RES happy", description="A fix")
    )
    assert row.id

    updated = service.update_resolution(
        row.id, ComplaintResolutionUpdate(description="Updated fix")
    )
    assert updated.description == "Updated fix"

    listing = service.list_resolutions(query="Test RES happy")
    assert listing["pagination"]["total"] == 1

    service.delete_resolution(row.id)
    assert db.query(ComplaintResolution).filter(ComplaintResolution.id == row.id).first() is None


def test_delete_resolution_blocked_when_in_use(db: Session) -> None:
    service = ComplaintResolutionService(db)
    res = service.create_resolution(ComplaintResolutionCreate(name="Test RES blocked"))
    db.commit()

    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_number="TEST-RC-RESBLOCK",
        status="new",
        resolution_id=res.id,
    )
    db.add(complaint)
    db.commit()

    try:
        with pytest.raises(AppException) as exc_info:
            service.delete_resolution(res.id)
        assert exc_info.value.status_code == 409
        detail = exc_info.value.detail if hasattr(exc_info.value, "detail") else str(exc_info.value)
        msg = detail.get("message") if isinstance(detail, dict) else str(detail)
        assert "Cannot delete" in str(msg)
        assert "1 complaint" in str(msg)
    finally:
        db.delete(complaint)
        db.commit()
