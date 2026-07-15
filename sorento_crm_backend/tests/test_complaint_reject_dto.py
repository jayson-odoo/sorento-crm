"""Form-banner person links — Complaint rejection DTO (UAC REJ-2 / PR-4).

Complaint.rejected_by holds a respond_user_id (NOT a users.id). The detail DTO
exposes rejected_by_name (resolved via respond_user_id) + rejected_by_wa_phone
(via the respond_user_id phone path) + rejected_at.

Run: pytest tests/test_complaint_reject_dto.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.access import RespondContact
from app.models.complaints import Complaint
from app.models.user import User
from app.services.complaints_service import ComplaintService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.types import JSON as GenericJSON

    for col in list(RespondContact.__table__.columns):
        if isinstance(col.type, JSONB):
            col.type = GenericJSON()
            col.server_default = None

    Base.metadata.create_all(
        engine,
        tables=[RespondContact.__table__, User.__table__, Complaint.__table__],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _serialize(svc, complaint):
    """Call the detail serializer with list-path overrides so only the rejecter
    fields (under test) are computed live."""
    return svc._serialize_complaint(
        complaint,
        links_override=[],
        view_url_override="http://view/x",
        assigned_to_name_override=None,
        handled_by_name_override=None,
        handled_by_wa_phone_override=None,
        last_responded_by_name_override=None,
    )


def test_complaint_reject_dto_resolves_via_respond_user_id(db):
    cid = str(uuid.uuid4())
    db.add(RespondContact(id=cid, phone_number="60111222333", name="CX", respond_io_id="io", session_vars={}))
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email="cx@t.com", name="Complaint Rejecter", respond_contact_id=cid, respond_user_id="respond-xyz"))
    comp_id = str(uuid.uuid4())
    when = datetime(2026, 3, 1, 9, 0, 0)
    db.add(Complaint(
        id=comp_id,
        status="rejected",
        rejection_reason="invalid",
        rejected_at=when,
        rejected_by="respond-xyz",  # respond_user_id, not users.id
    ))
    db.commit()

    svc = ComplaintService(db)
    data = _serialize(svc, db.query(Complaint).get(comp_id))
    assert data["rejected_by_name"] == "Complaint Rejecter"
    assert data["rejected_by_wa_phone"] == "60111222333"
    assert data["rejected_at"] == when


def test_complaint_reject_dto_no_rejecter(db):
    comp_id = str(uuid.uuid4())
    db.add(Complaint(id=comp_id, status="new"))
    db.commit()
    svc = ComplaintService(db)
    data = _serialize(svc, db.query(Complaint).get(comp_id))
    assert data["rejected_by_name"] is None
    assert data["rejected_by_wa_phone"] is None
