"""Form-banner person links - StockInquiry rejection DTO (UAC REJ-1).

The stock-inquiry detail DTO exposes rejected_by_name, rejected_by_wa_phone and
rejected_at (rejected_by = users.id). Phone resolves via the shared resolver.

Run: pytest tests/test_stock_inquiry_reject_dto.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import patch

import pytest

from app.models.access import RespondContact
from app.models.procurement import StockInquiry
from app.models.user import User
from app.services.procurement_service import StockInquiryService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _user_with_phone(db, phone="60123456789", name="SIRejecter"):
    cid = str(uuid.uuid4())
    db.add(RespondContact(id=cid, phone_number=phone, name=name, respond_io_id="io", session_vars={}))
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{name}@t.com", name=name, respond_contact_id=cid))
    db.commit()
    return uid


def test_stock_inquiry_reject_dto_exposes_name_phone_and_when(db):
    uid = _user_with_phone(db)
    sid = str(uuid.uuid4())
    when = datetime(2026, 2, 1, 10, 0, 0)
    db.add(StockInquiry(
        id=sid,
        status="rejected",
        rejection_reason="out of scope",
        rejected_at=when,
        rejected_by=uid,
    ))
    db.commit()

    svc = StockInquiryService(db)
    with patch.object(svc.entity_attachment_service, "list_links", return_value=[]), patch.object(
        svc, "_build_stock_inquiry_view_url", return_value="http://view/x"
    ):
        data = svc.get_inquiry_for_response(sid)

    assert data["rejected_by_name"] == "SIRejecter"
    assert data["rejected_by_wa_phone"] == "60123456789"
    assert data["rejected_at"] == when


def test_stock_inquiry_reject_no_phone_plain(db):
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email="noph@t.com", name="NoPhone"))
    sid = str(uuid.uuid4())
    db.add(StockInquiry(id=sid, status="rejected", rejected_by=uid))
    db.commit()
    svc = StockInquiryService(db)
    with patch.object(svc.entity_attachment_service, "list_links", return_value=[]), patch.object(
        svc, "_build_stock_inquiry_view_url", return_value="http://view/x"
    ):
        data = svc.get_inquiry_for_response(sid)
    assert data["rejected_by_name"] == "NoPhone"
    assert data["rejected_by_wa_phone"] is None
