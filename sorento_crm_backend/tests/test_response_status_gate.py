"""Response gating by status (UAC-portal-submission-revisions section O).

The two stage-output responses in the system - ``purchasing_response`` on a
stock inquiry and ``technical_team_response`` on a complaint - may only be
written while the record is still in the stage that asked for them. Neither path
had a status guard before this, so these tests pin a NEW restriction on live
behaviour:

* refused outside the allowed statuses, on BOTH types, on the plain update path
  and on the update-and-reply path (AC O1);
* still allowed inside them (unchanged behaviour);
* a save that carries the response back UNCHANGED (the edit forms post the whole
  entity) is not a response write, so it keeps working at any status;
* and the regression that matters most: **ordinary chat on a closed / rejected
  record still succeeds** (AC O2). The chat send is a different endpoint
  (``/{entity_id}/conversation/send-message``) that never touches the entity,
  and it must stay open at every status.

Postgres only, on an empty scratch schema, seeding its own rows.

Run: venv/bin/pytest tests/test_response_status_gate.py -q
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.complaints import Complaint
from app.models.procurement import StockInquiry
from app.schemas.complaints import ComplaintUpdate
from app.schemas.procurement import StockInquiryUpdate
from app.services.complaints_service import ComplaintService
from app.services.error_handler import AppException
from app.services.procurement_service import StockInquiryService
from tests._pg_fixture import blank_session

MARKER = "ZZT-RESPGATE"

# A ':' in the last segment passes straight through resolve_send_identifier, so
# the chat resolver finds a sendable identifier without a RespondContact row.
INBOX_URL = "https://app.respond.io/space/364817/inbox/id:60123"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _inquiry(db, *, status: str, purchasing_response=None) -> StockInquiry:
    row = StockInquiry(
        id=str(uuid.uuid4()),
        inquiry_number=f"{MARKER}-{uuid.uuid4().hex[:6]}",
        salesperson=f"{MARKER} salesperson",
        product_code=f"{MARKER}-P",
        status=status,
        purchasing_response=purchasing_response,
        # A contact with no space_id keeps _build_respond_inbox_url from
        # recomputing (and blanking) the seeded URL on every save.
        contact_id=f"{MARKER}-contact",
        respond_inbox_url=INBOX_URL,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _complaint(db, *, status: str, technical_team_response=None) -> Complaint:
    row = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"{MARKER}-{uuid.uuid4().hex[:6]}",
        customer_name=f"{MARKER} customer",
        status=status,
        technical_team_response=technical_team_response,
        # A contact with no space_id keeps _build_respond_inbox_url from
        # recomputing (and blanking) the seeded URL on every save.
        contact_id=f"{MARKER}-contact",
        respond_inbox_url=INBOX_URL,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ------------------------------------------------------ stock inquiry: refused


@pytest.mark.parametrize("status", ["new", "pending_project_sales", "rejected", "voided"])
def test_stock_inquiry_response_write_refused_outside_response_stage(db, status):
    """Rewriting the purchasing response outside pending_purchasing / responded is a 422."""
    inquiry = _inquiry(db, status=status, purchasing_response="original answer")
    service = StockInquiryService(db)

    with pytest.raises(AppException) as ei:
        service.update_inquiry(
            str(inquiry.id),
            StockInquiryUpdate(purchasing_response="a brand new answer"),
        )

    assert ei.value.status_code == 422
    message = ei.value.detail["message"]
    assert "purchasing response" in message
    # One sentence that names the state and says what to do instead.
    assert "Chat Records" in message
    assert "—" not in message and "–" not in message  # no em/en dashes

    db.rollback()
    db.refresh(inquiry)
    assert inquiry.purchasing_response == "original answer"


@pytest.mark.parametrize("status", ["new", "pending_project_sales", "rejected", "voided"])
def test_stock_inquiry_update_and_reply_refused_outside_response_stage(db, status):
    """The reply path is a response write in full (it stamps last_responded_*)."""
    inquiry = _inquiry(db, status=status, purchasing_response="original answer")
    service = StockInquiryService(db)

    with patch.object(
        StockInquiryService, "_enqueue_stock_inquiry_respond_message"
    ) as enqueue:
        with pytest.raises(AppException) as ei:
            service.update_inquiry_and_reply(
                str(inquiry.id),
                StockInquiryUpdate(purchasing_response="a brand new answer"),
                respond_user_id="zzt-user",
            )

    assert ei.value.status_code == 422
    # Nothing was sent and nothing was stamped.
    assert enqueue.call_count == 0
    db.rollback()
    db.refresh(inquiry)
    assert inquiry.last_responded_by is None
    assert inquiry.last_responded_at is None
    assert inquiry.status == status


# ------------------------------------------------------ stock inquiry: allowed


@pytest.mark.parametrize("status", ["pending_purchasing", "responded"])
def test_stock_inquiry_response_write_allowed_in_response_stage(db, status):
    inquiry = _inquiry(db, status=status, purchasing_response="original answer")
    service = StockInquiryService(db)

    updated = service.update_inquiry(
        str(inquiry.id),
        StockInquiryUpdate(purchasing_response="a brand new answer"),
    )

    assert updated.purchasing_response == "a brand new answer"


@pytest.mark.parametrize("status", ["pending_purchasing", "responded"])
def test_stock_inquiry_update_and_reply_allowed_in_response_stage(db, status):
    inquiry = _inquiry(db, status=status, purchasing_response="the answer")
    service = StockInquiryService(db)

    with patch.object(
        StockInquiryService, "_enqueue_stock_inquiry_respond_message"
    ) as enqueue:
        updated = service.update_inquiry_and_reply(
            str(inquiry.id),
            StockInquiryUpdate(purchasing_response="the answer"),
            respond_user_id="zzt-user",
        )

    assert enqueue.call_count == 1
    assert updated.status == "responded"
    assert updated.last_responded_by == "zzt-user"
    assert updated.last_responded_at is not None


def test_stock_inquiry_unchanged_response_still_saves_when_rejected(db):
    """The edit form posts the whole entity, response column included. Re-posting
    the SAME response is not a response write, so an ordinary field edit on a
    rejected inquiry must keep working."""
    inquiry = _inquiry(db, status="rejected", purchasing_response="original answer")
    service = StockInquiryService(db)

    updated = service.update_inquiry(
        str(inquiry.id),
        StockInquiryUpdate(
            purchasing_response="original answer",
            remark=f"{MARKER} edited remark",
        ),
    )

    assert updated.remark == f"{MARKER} edited remark"
    assert updated.purchasing_response == "original answer"


# ---------------------------------------------------------- complaint: refused


@pytest.mark.parametrize("status", ["approved", "rejected", "processed_by_cs", "closed"])
def test_complaint_response_write_refused_outside_response_stage(db, status):
    complaint = _complaint(db, status=status, technical_team_response="original answer")
    service = ComplaintService(db)

    with pytest.raises(AppException) as ei:
        service.update_complaint(
            str(complaint.id),
            ComplaintUpdate(technical_team_response="a brand new answer"),
        )

    assert ei.value.status_code == 422
    message = ei.value.detail["message"]
    assert "technical team response" in message
    assert "Chat Records" in message

    db.rollback()
    db.refresh(complaint)
    assert complaint.technical_team_response == "original answer"


@pytest.mark.parametrize("status", ["approved", "rejected", "processed_by_cs", "closed"])
def test_complaint_update_and_reply_refused_outside_response_stage(db, status):
    complaint = _complaint(db, status=status, technical_team_response="original answer")
    service = ComplaintService(db)

    with pytest.raises(AppException) as ei:
        service.update_complaint_and_reply(
            str(complaint.id),
            ComplaintUpdate(technical_team_response="a brand new answer"),
            respond_user_id="zzt-user",
        )

    assert ei.value.status_code == 422
    db.rollback()
    db.refresh(complaint)
    assert complaint.technical_team_response == "original answer"
    assert complaint.last_responded_by is None
    assert complaint.status == status


# ---------------------------------------------------------- complaint: allowed


@pytest.mark.parametrize("status", ["new", "submitted", "updated", "responded"])
def test_complaint_response_write_allowed_in_response_stage(db, status):
    complaint = _complaint(db, status=status, technical_team_response="original answer")
    service = ComplaintService(db)

    updated = service.update_complaint(
        str(complaint.id),
        ComplaintUpdate(technical_team_response="a brand new answer"),
    )

    assert updated.technical_team_response == "a brand new answer"


def test_complaint_update_and_reply_allowed_in_response_stage(db):
    complaint = _complaint(db, status="submitted")
    service = ComplaintService(db)

    updated = service.update_complaint_and_reply(
        str(complaint.id),
        ComplaintUpdate(technical_team_response=f"{MARKER} reply body"),
        respond_user_id="zzt-user",
    )

    assert updated.status == "responded"
    assert updated.technical_team_response == f"{MARKER} reply body"
    assert updated.last_responded_by == "zzt-user"


def test_complaint_unchanged_response_still_saves_when_closed(db):
    """Same as the stock inquiry case: re-posting the stored response verbatim is
    not a response write, so editing other fields on a closed complaint works."""
    complaint = _complaint(db, status="closed", technical_team_response="original answer")
    service = ComplaintService(db)

    updated = service.update_complaint(
        str(complaint.id),
        ComplaintUpdate(
            technical_team_response="original answer",
            customer_name=f"{MARKER} renamed customer",
        ),
    )

    assert updated.customer_name == f"{MARKER} renamed customer"
    assert updated.technical_team_response == "original answer"


def test_complaint_legacy_preamble_response_posted_back_bare_still_saves(db):
    """The case the plain "unchanged" test misses.

    ``_normalize_complaint_reply_body_for_storage`` strips the legacy composed
    customer message, and it only ever ran on WRITE - so every row stored before it
    landed still carries the preamble. The detail page and the edit form both render
    the STRIPPED text (``displayComplaintTechnicalResponse``), so the form posts back
    the bare body. Comparing that against the raw stored value reads as a rewrite,
    and an office user editing the customer's address on an approved complaint got a
    422 about a response they never touched.
    """
    stored = (
        "There has been an update regarding your complaint "
        "https://crm.example.test/view?token=abc: the part was replaced"
    )
    complaint = _complaint(db, status="approved", technical_team_response=stored)
    service = ComplaintService(db)

    updated = service.update_complaint(
        str(complaint.id),
        ComplaintUpdate(
            technical_team_response="the part was replaced",
            customer_address=f"{MARKER} new address",
        ),
    )

    assert updated.customer_address == f"{MARKER} new address"
    assert updated.technical_team_response == "the part was replaced"


def test_complaint_legacy_preamble_row_still_refuses_a_real_rewrite(db):
    """The gate is normalized on both sides, not disabled: a genuinely different
    answer on a legacy row is still refused."""
    stored = (
        "There has been an update regarding your complaint "
        "https://crm.example.test/view?token=abc: the part was replaced"
    )
    complaint = _complaint(db, status="approved", technical_team_response=stored)
    service = ComplaintService(db)

    with pytest.raises(AppException) as ei:
        service.update_complaint(
            str(complaint.id),
            ComplaintUpdate(technical_team_response="we replaced the whole unit"),
        )

    assert ei.value.status_code == 422
    db.rollback()
    db.refresh(complaint)
    assert complaint.technical_team_response == stored


# ------------------------------------------------- the regression that matters
# Ordinary chat is NOT gated. Messaging a contact about a closed / rejected
# record keeps working exactly as before (AC O2).


def _chat_app(db, *, business_table, resolver, chat_use_case):
    from app.api.v1._respond_chat_template_routes import build_chat_template_router
    from app.database import get_db
    from app.dependencies import get_current_user

    app = FastAPI()
    app.include_router(
        build_chat_template_router(
            business_table=business_table,
            resolver=resolver,
            chat_use_case=chat_use_case,
        ),
        prefix="/entity",
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: {
        "id": str(uuid.uuid4()),
        "name": "Jay Tan",
    }
    return app


def _precheck_ok(*_a, **_k):
    return {
        "sent_as": "text",
        "window_state": {"open": True, "last_incoming_at": None},
    }


class _FakeJob:
    id = "zzt-job"


@pytest.mark.parametrize("status", ["rejected", "voided"])
def test_plain_chat_send_still_works_on_a_dead_stock_inquiry(db, status):
    from app.api.v1.procurement.stock_inquiries import (
        _resolve_stock_inquiry_chat_contact,
    )

    inquiry = _inquiry(db, status=status, purchasing_response="original answer")
    app = _chat_app(
        db,
        business_table="stock_inquiries",
        resolver=_resolve_stock_inquiry_chat_contact,
        chat_use_case="stock_inquiry_chat",
    )

    with patch(
        "app.services.respond_chat_template_service.precheck_chat_send", _precheck_ok
    ), patch(
        "app.services.queue_service.enqueue_job", return_value=_FakeJob()
    ) as enqueue:
        resp = TestClient(app).post(
            f"/entity/{inquiry.id}/conversation/send-message",
            json={"text": "Hi, just following up on this one."},
        )

    assert resp.status_code == 200
    assert resp.json()["sent_as"] == "text"
    assert enqueue.call_count == 1

    # The chat send never touches the entity: same status, same response, no
    # last_responded stamp.
    db.refresh(inquiry)
    assert inquiry.status == status
    assert inquiry.purchasing_response == "original answer"
    assert inquiry.last_responded_by is None
    assert inquiry.last_responded_at is None


@pytest.mark.parametrize("status", ["closed", "rejected", "processed_by_cs"])
def test_plain_chat_send_still_works_on_a_dead_complaint(db, status):
    from app.api.v1.complaints.complaints import _resolve_complaint_chat_contact

    complaint = _complaint(db, status=status, technical_team_response="original answer")
    app = _chat_app(
        db,
        business_table="complaints",
        resolver=_resolve_complaint_chat_contact,
        chat_use_case="complaint_chat",
    )

    with patch(
        "app.services.respond_chat_template_service.precheck_chat_send", _precheck_ok
    ), patch(
        "app.services.queue_service.enqueue_job", return_value=_FakeJob()
    ) as enqueue:
        resp = TestClient(app).post(
            f"/entity/{complaint.id}/conversation/send-message",
            json={"text": "Hi, one more update for you."},
        )

    assert resp.status_code == 200
    assert enqueue.call_count == 1

    db.refresh(complaint)
    assert complaint.status == status
    assert complaint.technical_team_response == "original answer"
    assert complaint.last_responded_by is None


# ------------------------------------------------------------- the gate itself


def test_unknown_entity_type_is_not_gated():
    """Only the known response surfaces carry this restriction."""
    from app.services import response_gate

    assert response_gate.is_response_status_allowed("something_new", "closed") is True
    assert response_gate.response_blocked_reason("something_new", "closed") is None


@pytest.mark.parametrize(
    "entity_type", ["purchase_request", "sponsorship_form", "ticket"]
)
@pytest.mark.parametrize("status", ["closed", "rejected", "voided", "processed_by_cs"])
def test_types_with_no_response_surface_are_never_gated(entity_type, status):
    """PR / SF / ticket expose an update-and-reply too, but none of them STORES a
    response: purchase_requests has no response column, and the payload's only
    extra field is a transient ``reply_message``. Gating them would block chat on
    a closed record, which AC O2 forbids. Pinned so nobody later "finishes the
    set" by adding them."""
    from app.services import response_gate

    assert entity_type in response_gate.NO_RESPONSE_SURFACE
    assert entity_type not in response_gate.ALLOWED_RESPONSE_STATUSES
    assert entity_type not in response_gate.RESPONSE_FIELDS
    assert response_gate.is_response_status_allowed(entity_type, status) is True
    assert response_gate.response_blocked_reason(entity_type, status) is None


def test_purchase_requests_table_has_no_response_column():
    """The evidence behind NO_RESPONSE_SURFACE, asserted rather than trusted. If a
    response column is ever added to purchase_requests this fails, and whoever
    adds it has to decide whether it needs gating."""
    from app.models.procurement import PurchaseRequestHeader

    columns = set(PurchaseRequestHeader.__table__.columns.keys())
    assert "purchasing_response" not in columns
    assert "technical_team_response" not in columns
    assert "last_responded_by" not in columns
    assert "last_responded_at" not in columns


@pytest.mark.parametrize("request_type", ["purchase_request", "sponsorship_form"])
@pytest.mark.parametrize("status", ["closed", "rejected", "voided", "processed_by_cs"])
def test_plain_chat_send_still_works_on_a_dead_purchase_request(
    db, request_type, status
):
    """The same regression guard as the other two types, on the surface the
    response gate deliberately does NOT cover."""
    from app.api.v1._respond_chat_template_routes import build_chat_template_router
    from app.api.v1.procurement.purchase_requests import (
        _resolve_purchase_request_chat_contact,
        _resolve_purchase_request_chat_use_case,
    )
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.models.procurement import PurchaseRequestHeader

    header = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_type=request_type,
        request_number=f"{MARKER}-{uuid.uuid4().hex[:6]}",
        customer_name=f"{MARKER} customer",
        status=status,
        contact_id=f"{MARKER}-contact",
        respond_inbox_url=INBOX_URL,
    )
    db.add(header)
    db.commit()
    db.refresh(header)

    app = FastAPI()
    app.include_router(
        build_chat_template_router(
            business_table="purchase_requests",
            resolver=_resolve_purchase_request_chat_contact,
            chat_use_case_resolver=_resolve_purchase_request_chat_use_case,
        ),
        prefix="/entity",
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: {
        "id": str(uuid.uuid4()),
        "name": "Jay Tan",
    }

    with patch(
        "app.services.respond_chat_template_service.precheck_chat_send", _precheck_ok
    ), patch(
        "app.services.queue_service.enqueue_job", return_value=_FakeJob()
    ) as enqueue:
        resp = TestClient(app).post(
            f"/entity/{header.id}/conversation/send-message",
            json={"text": "Hi, an update on this request."},
        )

    assert resp.status_code == 200
    assert enqueue.call_count == 1

    db.refresh(header)
    assert header.status == status


def test_blank_and_whitespace_response_compare_equal():
    """None, '' and '   ' are the same stored answer, so swapping one for another
    is not a response write."""
    from app.services import response_gate

    assert response_gate.response_text_changed(None, "") is False
    assert response_gate.response_text_changed("  answer  ", "answer") is False
    assert response_gate.response_text_changed(None, "answer") is True
