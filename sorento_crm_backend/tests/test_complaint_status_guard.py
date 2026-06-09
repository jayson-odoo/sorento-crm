"""Editing/saving a complaint's technical response must not regress its status.

Lifecycle: submitted -> responded -> approved|rejected ; approved -> processed_by_cs|closed.
'Save only' (update_complaint) may move new/submitted/updated -> 'updated', but must
leave a decided/terminal complaint (approved/rejected/processed_by_cs/closed) untouched.
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
def test_edit_response_does_not_regress_decided_status(db: Session, terminal: str) -> None:
    c = _seed(db, terminal)
    out = _edit_response(db, c.id, "edited note after decision")
    assert out.status == terminal  # unchanged
    assert (out.technical_team_response or "").strip() != ""


def test_edit_response_moves_submitted_to_updated(db: Session) -> None:
    c = _seed(db, "submitted")
    out = _edit_response(db, c.id, "first response draft")
    assert out.status == "updated"


def test_edit_response_keeps_responded(db: Session) -> None:
    c = _seed(db, "responded")
    out = _edit_response(db, c.id, "tweaked response")
    assert out.status == "responded"  # not bumped back to 'updated'
