"""Service-level tests for the customer-service 'resolve' action on complaints.

Resolve closes an approved complaint: status approved -> resolved, stamps
resolved_at/by, and emits the 'resolved' form-SLA event (best-effort). Only an
approved complaint can be resolved; resolving again is idempotent.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine
from tests._pg_fixture import pg_session
from app.models.complaints import Complaint
from app.services.complaints_service import ComplaintService


@pytest.fixture(autouse=True)
def _clean_state():
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM complaints WHERE complaint_number LIKE 'CMPRES-%'"))
            conn.commit()
        except Exception:
            conn.rollback()
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    with pg_session() as s:
        yield s


def _seed(db: Session, status: str) -> Complaint:
    c = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"CMPRES-{uuid.uuid4().hex[:6]}",
        status=status,
        customer_name="ACME",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_process_by_cs_approved_complaint(db: Session) -> None:
    c = _seed(db, "approved")
    out = ComplaintService(db).mark_processed_by_cs(c.id, crm_sender_user_id="u-cs")
    assert out.status == "processed_by_cs"
    assert out.resolved_at is not None
    assert out.resolved_by == "u-cs"


def test_process_by_cs_rejected_when_not_approved(db: Session) -> None:
    c = _seed(db, "responded")
    with pytest.raises(Exception):
        ComplaintService(db).mark_processed_by_cs(c.id, crm_sender_user_id="u-cs")
    db.rollback()
    refetched = db.query(Complaint).filter(Complaint.id == c.id).first()
    assert refetched.status == "responded"


def test_process_by_cs_is_idempotent(db: Session) -> None:
    c = _seed(db, "approved")
    svc = ComplaintService(db)
    svc.mark_processed_by_cs(c.id, crm_sender_user_id="u-cs")
    out = svc.mark_processed_by_cs(c.id, crm_sender_user_id="u-cs2")
    # Still processed_by_cs; first actor retained.
    assert out.status == "processed_by_cs"
    assert out.resolved_by == "u-cs"


def test_close_approved_complaint(db: Session) -> None:
    c = _seed(db, "approved")
    out = ComplaintService(db).close_complaint(
        c.id, note="Customer unreachable", crm_sender_user_id="u-cs"
    )
    assert out.status == "closed"
    assert out.resolved_at is not None
    assert out.resolved_by == "u-cs"


def test_close_rejected_when_not_approved(db: Session) -> None:
    c = _seed(db, "responded")
    with pytest.raises(Exception):
        ComplaintService(db).close_complaint(c.id, crm_sender_user_id="u-cs")
    db.rollback()
    assert db.query(Complaint).filter(Complaint.id == c.id).first().status == "responded"


def test_close_is_idempotent(db: Session) -> None:
    c = _seed(db, "approved")
    svc = ComplaintService(db)
    svc.close_complaint(c.id, crm_sender_user_id="u-cs")
    out = svc.close_complaint(c.id, crm_sender_user_id="u-cs2")
    assert out.status == "closed"
    assert out.resolved_by == "u-cs"
