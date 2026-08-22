"""Editing/saving a complaint's technical response must not regress its status.

Lifecycle: submitted -> responded -> approved|rejected ; approved -> processed_by_cs|closed.
'Save only' (update_complaint) may move new/submitted/updated -> 'updated', but must
leave a decided/terminal complaint (approved/rejected/processed_by_cs/closed) untouched.

Superseded in part by the response gate (UAC-portal-submission-revisions O1): on a
decided/terminal complaint the response can no longer be edited at all, so
"the save does not regress the status" became "the save is refused". The status
is still untouched, which is what this file exists to protect. See
tests/test_response_status_gate.py for the full gate.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.complaints import Complaint
from app.schemas.complaints import ComplaintUpdate
from app.services.complaints_service import ComplaintService
from app.services.error_handler import AppException


@pytest.fixture(autouse=True)
def _clean():
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM complaints WHERE complaint_number LIKE 'CMPSG-%'"))
            conn.commit()
        except Exception:
            conn.rollback()
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _seed(db: Session, status: str) -> Complaint:
    c = Complaint(id=str(uuid.uuid4()), complaint_number=f"CMPSG-{uuid.uuid4().hex[:6]}", status=status)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _edit_response(db: Session, cid: str, text_value: str) -> Complaint:
    return ComplaintService(db).update_complaint(
        cid, ComplaintUpdate(technical_team_response=text_value)
    )


@pytest.mark.parametrize("terminal", ["approved", "rejected", "processed_by_cs", "closed"])
def test_edit_response_refused_on_decided_status(db: Session, terminal: str) -> None:
    """The response is stage output, so a decided complaint refuses the edit (422)
    rather than accepting it without a status move. The status stays put either way."""
    c = _seed(db, terminal)
    with pytest.raises(AppException) as ei:
        _edit_response(db, c.id, "edited note after decision")
    assert ei.value.status_code == 422

    db.rollback()
    db.refresh(c)
    assert c.status == terminal  # unchanged
    assert c.technical_team_response is None  # the edit never landed


def test_edit_response_moves_submitted_to_updated(db: Session) -> None:
    c = _seed(db, "submitted")
    out = _edit_response(db, c.id, "first response draft")
    assert out.status == "updated"


def test_edit_response_keeps_responded(db: Session) -> None:
    c = _seed(db, "responded")
    out = _edit_response(db, c.id, "tweaked response")
    assert out.status == "responded"  # not bumped back to 'updated'
