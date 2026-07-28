"""HARD BLOCKER (UAC-response-attachments.md D2 / UAC-complaint-root-cause D2-adjacent).

The attachment sentence composed for the outgoing Respond.io message must NEVER
be persisted into ``stock_inquiries.purchasing_response`` /
``complaints.technical_team_response``. Those columns must read back EXACTLY
what staff typed, byte for byte, while the message pushed onto the ``respond_io``
RQ queue DOES carry the sentence.

The external Respond.io call is decoupled through ``queue_service.enqueue_job``
(see PLAN-response-attachments-and-portal-nav.md); we stub it to capture the
payload without a worker, mirroring test_complaint_do_notify.py.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.complaints import Complaint
from app.models.entity_attachment import EntityAttachmentLink
from app.models.procurement import StockInquiry
from app.models.resources import Attachment
from app.schemas.complaints import ComplaintUpdate
from app.schemas.procurement import StockInquiryUpdate
from app.services.complaints_service import ComplaintService
from app.services.procurement_service import StockInquiryService

SI_PREFIX = "RATS-SI-"
CX_PREFIX = "RATS-CX-"


def _safe_exec(conn, sql: str) -> None:
    try:
        conn.execute(text(sql))
    except Exception:
        conn.rollback()


@pytest.fixture(autouse=True)
def _clean_state():
    def _wipe(conn):
        _safe_exec(
            conn,
            "DELETE FROM entity_attachment_links WHERE entity_id IN "
            "(SELECT id::text FROM stock_inquiries WHERE inquiry_number LIKE 'RATS-SI-%') "
            "OR entity_id IN (SELECT id::text FROM complaints WHERE complaint_number LIKE 'RATS-CX-%')",
        )
        _safe_exec(
            conn,
            "DELETE FROM attachments WHERE original_filename LIKE 'rats-staff-%'",
        )
        _safe_exec(conn, "DELETE FROM stock_inquiries WHERE inquiry_number LIKE 'RATS-SI-%'")
        _safe_exec(conn, "DELETE FROM complaints WHERE complaint_number LIKE 'RATS-CX-%'")
        conn.commit()

    with engine.connect() as conn:
        _wipe(conn)
    yield
    with engine.connect() as conn:
        _wipe(conn)


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _patch_enqueue(monkeypatch, captured: list) -> None:
    from app.services import queue_service
    from app.services import respond_identifier

    def fake_enqueue(fn, *args, **kw):  # noqa: ANN001
        captured.append({"fn": getattr(fn, "__name__", str(fn)), "args": args})

        class _Job:
            id = "job-1"

        return _Job()

    monkeypatch.setattr(queue_service, "enqueue_job", fake_enqueue)
    monkeypatch.setattr(
        respond_identifier, "resolve_send_identifier", lambda db, last_seg: str(last_seg)
    )


def _response_attachment_type_id(db: Session) -> str:
    """The `response_attachment` type. The sentence counts THIS type only, so a
    staff file linked through the manual Linked Attachments panel is never
    announced to the customer."""
    from app.models.resources import AttachmentType
    from app.services.entity_attachment_service import RESPONSE_ATTACHMENT_TYPE_CODE

    row = (
        db.query(AttachmentType)
        .filter(AttachmentType.code == RESPONSE_ATTACHMENT_TYPE_CODE)
        .first()
    )
    if row is None:
        row = AttachmentType(
            id=str(uuid.uuid4()),
            code=RESPONSE_ATTACHMENT_TYPE_CODE,
            type_name="Response Attachment",
            allowed_extensions="jpg,jpeg,png,pdf",
            max_file_size_mb=100,
        )
        db.add(row)
        db.flush()
    return row.id


def _stage_staff_attachments(db: Session, entity_type: str, entity_id: str, count: int) -> None:
    """Seed ``count`` staff response attachments already linked to the entity, as
    the "Edit ... response" popup would have staged them (UAC C1-C3) before
    Update & Reply is clicked."""
    type_id = _response_attachment_type_id(db)
    for i in range(count):
        att = Attachment(
            id=str(uuid.uuid4()),
            original_filename=f"rats-staff-{i}.jpg",
            stored_filename=f"rats-staff-{i}.jpg",
            file_path=f"https://cdn.test/rats-staff-{i}.jpg",
            uploaded_by=str(uuid.uuid4()),
            uploader_kind="user",
            attachment_type_id=type_id,
        )
        db.add(att)
        db.flush()
        db.add(
            EntityAttachmentLink(
                entity_type=entity_type,
                entity_id=str(entity_id),
                attachment_id=att.id,
            )
        )
    db.commit()


# --------------------------------------------------------------------------
# Stock inquiry: update_inquiry_and_reply
# --------------------------------------------------------------------------


def _mk_inquiry(db: Session, number: str) -> StockInquiry:
    # contact_id/space_id are set to non-None dummy values (matching no real
    # RespondContact row) so update_inquiry_and_reply's respond_inbox_url
    # rebuild sees "unresolvable" (None) and leaves the pre-set inbox URL
    # below untouched, instead of nulling it out (its "both None" branch).
    row = StockInquiry(
        id=str(uuid.uuid4()),
        inquiry_number=number,
        status="pending_purchasing",
        contact_id="rats-fake-contact",
        space_id="rats-space-1",
        respond_inbox_url="https://app.respond.io/space/1/inbox/555000",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _do_purchasing_reply(svc: StockInquiryService, inquiry_id: str, bare_text: str) -> None:
    """Mirror the FE's real two-call "Update & Reply" choreography exactly
    (StockInquiryDetail.tsx sendPurchasingUpdateAndReplyViaRespond):

      1. Plain PUT (``update_inquiry``) persists the BARE reply text into
         ``purchasing_response`` -- this is the only place it is ever written.
      2. POST .../update-and-reply (``update_inquiry_and_reply``) sends the
         FE-composed message (preamble + link) but deliberately does NOT
         touch the column (it was already correct from step 1).

    A single call to ``update_inquiry_and_reply`` alone never persists
    anything into ``purchasing_response`` -- see the finding in the test
    report; this helper matches the shipped FE behaviour so the hard blocker
    is exercised faithfully end to end.
    """
    svc.update_inquiry(inquiry_id, StockInquiryUpdate(purchasing_response=bare_text))
    full_message = f"There is a response to your stock inquiry: {bare_text}"
    svc.update_inquiry_and_reply(
        inquiry_id,
        StockInquiryUpdate(purchasing_response=full_message),
        respond_user_id="555000",
    )


def test_stock_inquiry_reply_with_attachments_column_stays_clean(db: Session, monkeypatch) -> None:
    captured: list = []
    _patch_enqueue(monkeypatch, captured)

    inquiry = _mk_inquiry(db, f"{SI_PREFIX}0001")
    _stage_staff_attachments(db, "stock_inquiry", str(inquiry.id), 2)

    reply_text = "The item is back in stock next Tuesday."
    svc = StockInquiryService(db)
    _do_purchasing_reply(svc, str(inquiry.id), reply_text)

    db.expire_all()
    refreshed = db.query(StockInquiry).filter(StockInquiry.id == inquiry.id).first()
    # Hard blocker: column holds EXACTLY the staff-typed text, byte for byte --
    # no preamble, no link, no attachment sentence.
    assert refreshed.purchasing_response == reply_text
    assert "attachment" not in refreshed.purchasing_response.lower()

    # The outgoing message DOES carry the composed sentence naming the count.
    assert len(captured) == 1
    outgoing_text = captured[0]["args"][2]  # send_stock_inquiry_respond_message(inquiry_id, identifier, message_text, ...)
    assert reply_text in outgoing_text
    assert "2 attachments" in outgoing_text


def test_stock_inquiry_reply_with_zero_attachments_no_sentence(db: Session, monkeypatch) -> None:
    captured: list = []
    _patch_enqueue(monkeypatch, captured)

    inquiry = _mk_inquiry(db, f"{SI_PREFIX}0002")
    reply_text = "No stock available at the moment."
    svc = StockInquiryService(db)
    _do_purchasing_reply(svc, str(inquiry.id), reply_text)

    db.expire_all()
    refreshed = db.query(StockInquiry).filter(StockInquiry.id == inquiry.id).first()
    assert refreshed.purchasing_response == reply_text

    outgoing_text = captured[0]["args"][2]
    assert "attachment" not in outgoing_text.lower()
    assert outgoing_text.endswith(reply_text) or reply_text in outgoing_text


def test_stock_inquiry_reply_single_attachment_singular_wording(db: Session, monkeypatch) -> None:
    captured: list = []
    _patch_enqueue(monkeypatch, captured)

    inquiry = _mk_inquiry(db, f"{SI_PREFIX}0003")
    _stage_staff_attachments(db, "stock_inquiry", str(inquiry.id), 1)

    reply_text = "Photo attached for reference."
    svc = StockInquiryService(db)
    _do_purchasing_reply(svc, str(inquiry.id), reply_text)

    db.expire_all()
    refreshed = db.query(StockInquiry).filter(StockInquiry.id == inquiry.id).first()
    assert refreshed.purchasing_response == reply_text

    outgoing_text = captured[0]["args"][2]
    assert "1 attachment" in outgoing_text
    # Never the plural form for count 1.
    assert "1 attachments" not in outgoing_text


def test_FINDING_update_inquiry_and_reply_alone_never_persists_purchasing_response(
    db: Session, monkeypatch
) -> None:
    """FINDING (not asserted as a hard-blocker failure, pinned for visibility):
    ``update_inquiry_and_reply`` never writes ``purchasing_response`` itself --
    it always pops the field from the update payload (see the "do not persist
    the reply payload" comment in procurement_service.py). The real UI flow
    (StockInquiryDetail.tsx) works around this by issuing a PLAIN ``update_inquiry``
    PUT with the bare text immediately before the POST .../update-and-reply
    call (see ``_do_purchasing_reply`` above), so the column ends up correct in
    practice.

    But called on its own -- e.g. a future API/MCP integration, or a FE
    regression that drops the first PUT -- the column is left completely
    untouched (None on a fresh row), unlike the complaint equivalent
    (``update_complaint_and_reply``), which stores ``stored_body`` itself and
    needs no companion call. This asymmetry is worth the product owner's
    attention; reported alongside this test rather than fixed (tests-only
    ownership for this task).
    """
    captured: list = []
    _patch_enqueue(monkeypatch, captured)

    inquiry = _mk_inquiry(db, f"{SI_PREFIX}0004")
    assert inquiry.purchasing_response is None

    reply_text = "Single-call reply, no prior plain PUT."
    StockInquiryService(db).update_inquiry_and_reply(
        str(inquiry.id),
        StockInquiryUpdate(purchasing_response=reply_text),
        respond_user_id="555000",
    )

    db.expire_all()
    refreshed = db.query(StockInquiry).filter(StockInquiry.id == inquiry.id).first()
    # Pinning current (surprising) behaviour: the column is NOT the reply text,
    # and not even set at all -- it stays exactly as it was before the call.
    assert refreshed.purchasing_response is None
    # The message was still sent, so the omission is silent (no error, no toast).
    assert len(captured) == 1
    assert reply_text in captured[0]["args"][2]


# --------------------------------------------------------------------------
# Complaint: update_complaint_and_reply
# --------------------------------------------------------------------------


def _mk_complaint(db: Session, number: str) -> Complaint:
    # Same "both non-None but unresolvable" trick as _mk_inquiry so the
    # respond_inbox_url rebuild in update_complaint_and_reply leaves the
    # pre-set inbox URL below untouched.
    c = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=number,
        status="new",
        contact_id="rats-fake-contact",
        space_id="rats-space-1",
        respond_inbox_url="https://app.respond.io/space/1/inbox/555111",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_complaint_reply_with_attachments_column_stays_clean(db: Session, monkeypatch) -> None:
    captured: list = []
    _patch_enqueue(monkeypatch, captured)

    complaint = _mk_complaint(db, f"{CX_PREFIX}0001")
    _stage_staff_attachments(db, "complaint", str(complaint.id), 3)

    reply_text = "The unit was inspected and a replacement part is on the way."
    ComplaintService(db).update_complaint_and_reply(
        str(complaint.id),
        ComplaintUpdate(technical_team_response=reply_text),
        respond_user_id="555111",
    )

    db.expire_all()
    refreshed = db.query(Complaint).filter(Complaint.id == complaint.id).first()
    assert refreshed.technical_team_response == reply_text
    assert "attachment" not in refreshed.technical_team_response.lower()

    assert len(captured) == 1
    outgoing_text = captured[0]["args"][2]  # send message args include the display message
    assert reply_text in outgoing_text
    assert "3 attachments" in outgoing_text


def test_complaint_reply_with_zero_attachments_no_sentence(db: Session, monkeypatch) -> None:
    captured: list = []
    _patch_enqueue(monkeypatch, captured)

    complaint = _mk_complaint(db, f"{CX_PREFIX}0002")
    reply_text = "This has been escalated to the factory."
    ComplaintService(db).update_complaint_and_reply(
        str(complaint.id),
        ComplaintUpdate(technical_team_response=reply_text),
        respond_user_id="555111",
    )

    db.expire_all()
    refreshed = db.query(Complaint).filter(Complaint.id == complaint.id).first()
    assert refreshed.technical_team_response == reply_text

    outgoing_text = captured[0]["args"][2]
    assert "attachment" not in outgoing_text.lower()
