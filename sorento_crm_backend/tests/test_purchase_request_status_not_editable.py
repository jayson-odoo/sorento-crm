"""No update path may walk a purchase request's or stock inquiry's status.

``PurchaseRequestHeaderUpdate`` / ``StockInquiryUpdate`` both expose ``status``,
and ``update_request`` used to apply the whole payload with a bare ``setattr`` -
so any caller who could edit a form could also move it between lifecycle states,
bypassing the workflow actions that own those transitions (set-pending-approval /
approval-decision / reject-submitted / process / close / void).

It bites the revision feature directly: a contact revision sets the status back
to the restart stage, and an office tab that was mid-edit could stomp it straight
back to the state the revision superseded.

**A refused move is a 422, never a silent drop.** Popping ``status`` fixed the
stomp but answered an n8n / MCP caller who had been moving the lifecycle through
this endpoint with ``200`` and nothing changed, which is the worst failure mode
available. The refusal is scoped to a status that would actually MOVE the record:
a payload echoing the CURRENT status changes nothing, so a read-modify-write of
the whole entity keeps saving - the same rule the response gate in these services
uses (only a real change is a write). Neither frontend edit form posts ``status``
at all, so no office save is affected.

**The guard covers update-and-reply too.** ``PurchaseRequestUpdateAndReply``
inherits ``status`` from the header update schema, and that path applied the whole
payload with a bare ``setattr`` - so the fence on the PUT path had a gate left
open beside it, reachable by anyone who could reply to a conversation (the route
also accepts an API key). On the stock inquiry reply path the unconditional flip
to ``responded`` made a supplied status inert, but only as long as the flip's
condition and the response gate agreed about the current status, which they did
not for a non-canonically-cased value. Both are closed here, with ``responded``
accepted on the inquiry reply as the echo of where that call lands.

Postgres only, on an empty scratch schema, seeding its own rows under a marker.

Run: venv/bin/pytest tests/test_purchase_request_status_not_editable.py -q
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.models.procurement import PurchaseRequestHeader, StockInquiry
from app.schemas.procurement import (
    PurchaseRequestHeaderUpdate,
    PurchaseRequestUpdateAndReply,
    StockInquiryUpdate,
)
from app.services.error_handler import AppException
from app.services.procurement_service import PurchaseRequestService, StockInquiryService
from tests._pg_fixture import blank_session

MARKER = "ZZT-PRSTATUS"

# A ':' in the last segment passes straight through resolve_send_identifier, so the
# reply path finds a sendable identifier without seeding a RespondContact row.
INBOX_URL = "https://app.respond.io/space/364817/inbox/id:60123"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _request(db, *, status="submitted", request_type="purchase_request") -> PurchaseRequestHeader:
    row = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_number=f"{MARKER}-{uuid.uuid4().hex[:6]}",
        request_type=request_type,
        status=status,
        source="portal",
        customer_name=f"{MARKER} customer",
        project_title=f"{MARKER} project",
        purpose=f"{MARKER} purpose",
        requested_by=f"{MARKER} requester",
        # A contact with no space_id keeps _build_respond_inbox_url from
        # recomputing (and blanking) the seeded URL on every save.
        contact_id=f"{MARKER}-contact",
        respond_inbox_url=INBOX_URL,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _inquiry(db, *, status="pending_purchasing") -> StockInquiry:
    row = StockInquiry(
        id=str(uuid.uuid4()),
        inquiry_number=f"{MARKER}-SI-{uuid.uuid4().hex[:6]}",
        status=status,
        salesperson=f"{MARKER} salesperson",
        product_code=f"{MARKER}-P",
        contact_id=f"{MARKER}-contact",
        respond_inbox_url=INBOX_URL,
        purchasing_response=f"{MARKER} the answer",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ------------------------------------------------------- the move is refused


@pytest.mark.parametrize("attempted", ["approved", "processed_by_cs", "closed", "draft"])
def test_update_request_refuses_a_status_move(db, attempted):
    row = _request(db, status="submitted")

    with pytest.raises(AppException) as ei:
        PurchaseRequestService(db).update_request(
            str(row.id),
            PurchaseRequestHeaderUpdate(status=attempted, project_title=f"{MARKER} edited"),
        )

    assert ei.value.status_code == 422
    message = ei.value.detail["message"]
    assert "purchase request" in message
    # The sentence ends with what to do instead.
    assert "action" in message
    assert "-" not in message and " - " not in message  # no em/en dashes

    # Nothing landed: the whole save is refused, not half-applied.
    db.rollback()
    db.refresh(row)
    assert row.status == "submitted"
    assert row.project_title == f"{MARKER} project"


def test_a_revision_restart_status_survives_a_concurrent_office_save(db):
    """The case this defect actually breaks.

    A revision has just put the form back to ``submitted``; an office tab still
    holding ``approved`` saves an unrelated field. The status must stay where the
    revision left it - and the stale tab is told, rather than being led to believe
    its edit went through untouched.
    """
    row = _request(db, status="submitted")

    with pytest.raises(AppException) as ei:
        PurchaseRequestService(db).update_request(
            str(row.id),
            PurchaseRequestHeaderUpdate(status="approved", purpose=f"{MARKER} edited purpose"),
        )

    assert ei.value.status_code == 422
    db.rollback()
    db.refresh(row)
    assert row.status == "submitted"


def test_the_same_rule_holds_for_a_sponsorship_form(db):
    """One table, one update path, one rule - and the sentence names the right type."""
    row = _request(db, status="submitted", request_type="sponsorship_form")

    with pytest.raises(AppException) as ei:
        PurchaseRequestService(db).update_request(
            str(row.id), PurchaseRequestHeaderUpdate(status="closed")
        )

    assert "sponsorship form" in ei.value.detail["message"]
    db.rollback()
    db.refresh(row)
    assert row.status == "submitted"


def test_the_stock_inquiry_path_is_treated_identically(db):
    """``update_inquiry`` pops ``status`` for the same reason, so it carries the same
    refusal - one schema/behaviour mismatch fixed in both places, never one."""
    inquiry = _inquiry(db, status="pending_purchasing")

    with pytest.raises(AppException) as ei:
        StockInquiryService(db).update_inquiry(
            str(inquiry.id), StockInquiryUpdate(status="closed", remark=f"{MARKER} edited")
        )

    assert ei.value.status_code == 422
    assert "stock inquiry" in ei.value.detail["message"]
    db.rollback()
    db.refresh(inquiry)
    assert inquiry.status == "pending_purchasing"
    assert inquiry.remark is None


# ---------------------------------------------- echoing the current status saves


def test_a_payload_echoing_the_current_status_still_saves(db):
    """A read-modify-write round trip posts the status it just read. That moves
    nothing, so it is not a status change and must not break an ordinary edit."""
    row = _request(db, status="submitted")

    updated = PurchaseRequestService(db).update_request(
        str(row.id),
        PurchaseRequestHeaderUpdate(status="submitted", project_title=f"{MARKER} edited"),
    )

    assert updated.status == "submitted"
    assert updated.project_title == f"{MARKER} edited"


def test_a_payload_echoing_the_current_status_still_saves_for_a_stock_inquiry(db):
    inquiry = _inquiry(db, status="pending_purchasing")

    updated = StockInquiryService(db).update_inquiry(
        str(inquiry.id),
        StockInquiryUpdate(status="pending_purchasing", remark=f"{MARKER} edited"),
    )

    assert updated.status == "pending_purchasing"
    assert updated.remark == f"{MARKER} edited"


def test_a_save_that_omits_status_is_untouched(db):
    """The overwhelmingly common case: the edit forms never post ``status``."""
    row = _request(db, status="approved")

    updated = PurchaseRequestService(db).update_request(
        str(row.id), PurchaseRequestHeaderUpdate(purpose=f"{MARKER} edited purpose")
    )

    assert updated.status == "approved"
    assert updated.purpose == f"{MARKER} edited purpose"


def test_a_number_posted_back_with_its_revision_suffix_is_stored_bare(db):
    """UAC N2: the stored number never carries the revision.

    ``request_number`` is user-assignable and the edit form posts it back, so a
    surface that renders ``PR-26-0012-R2`` must not be able to bake that suffix
    into the column the suffix was derived from.
    """
    row = _request(db, status="submitted")
    bare = row.request_number

    updated = PurchaseRequestService(db).update_request(
        str(row.id), PurchaseRequestHeaderUpdate(request_number=f"{bare}-R2")
    )

    assert updated.request_number == bare


# ------------------------------------------- the reply path carries the same rule
# ``POST /{id}/update-and-reply`` is an office edit plus a chat send. It applied
# the whole payload with a bare setattr, so it walked the lifecycle exactly as the
# PUT used to - a documented hole beside a guard is not a guard.


class _FakeSend:
    """Stand-in for ``send_text_or_template``: records the send, never leaves the
    process. Returns the shape the caller destructures."""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, db, *, identifier, text, use_case, context_vars):
        self.calls.append({"identifier": identifier, "text": text})
        return {
            "request_payload": {"message": {"type": "text", "text": text}},
            "response": {"messageId": "zzt-msg"},
        }


def _reply(db, header_id: str, payload: PurchaseRequestUpdateAndReply, send: _FakeSend):
    """Run the PR/SF reply path with only the external hop stubbed."""
    with patch(
        "app.services.respond_messaging_service.send_text_or_template", send
    ), patch(
        "app.services.respond_messaging_service.build_context_vars", return_value={}
    ), patch(
        "app.services.crm_chat_outbound_webhook.enqueue_crm_chat_outbound_webhook"
    ):
        return PurchaseRequestService(db).update_request_and_reply(
            header_id, payload, respond_user_id="zzt-user"
        )


@pytest.mark.parametrize("attempted", ["approved", "processed_by_cs", "closed", "draft"])
def test_update_and_reply_refuses_a_status_move(db, attempted):
    """The bypass, closed: same refusal, same sentence, nothing saved, nothing sent."""
    row = _request(db, status="submitted")
    send = _FakeSend()

    with pytest.raises(AppException) as ei:
        _reply(
            db,
            str(row.id),
            PurchaseRequestUpdateAndReply(
                status=attempted,
                project_title=f"{MARKER} edited",
                reply_message=f"{MARKER} here is your number",
            ),
            send,
        )

    assert ei.value.status_code == 422
    message = ei.value.detail["message"]
    assert "purchase request" in message
    assert "action" in message
    assert "-" not in message and " - " not in message  # no em/en dashes

    # Refused before anything ran: no reply left the building, no field landed.
    assert send.calls == []
    db.rollback()
    db.refresh(row)
    assert row.status == "submitted"
    assert row.project_title == f"{MARKER} project"


def test_update_and_reply_cannot_stomp_a_revision_restart_status(db):
    """The defect in its own words.

    A revision has just set the form back to ``submitted``. An office tab still
    holding ``approved`` replies to the contact. Before this guard the reply
    applied that stale status, undoing the revision - and the reply went out, so
    the contact was told about a version nobody was working on.
    """
    row = _request(db, status="submitted")
    send = _FakeSend()

    with pytest.raises(AppException) as ei:
        _reply(
            db,
            str(row.id),
            PurchaseRequestUpdateAndReply(
                status="approved", reply_message=f"{MARKER} an update for you"
            ),
            send,
        )

    assert ei.value.status_code == 422
    assert send.calls == []
    db.rollback()
    db.refresh(row)
    assert row.status == "submitted"


def test_update_and_reply_names_a_sponsorship_form_correctly(db):
    """One table, two document types, and the sentence names the right one on this
    path too."""
    row = _request(db, status="submitted", request_type="sponsorship_form")

    with pytest.raises(AppException) as ei:
        _reply(
            db,
            str(row.id),
            PurchaseRequestUpdateAndReply(
                status="closed", reply_message=f"{MARKER} an update for you"
            ),
            _FakeSend(),
        )

    assert "sponsorship form" in ei.value.detail["message"]
    db.rollback()
    db.refresh(row)
    assert row.status == "submitted"


def test_update_and_reply_echoing_the_current_status_still_saves_and_still_replies(db):
    """The guard must not break the read-modify-write caller: a payload posting back
    the status it just read moves nothing, so the edit saves AND the reply sends."""
    row = _request(db, status="submitted")
    send = _FakeSend()

    updated = _reply(
        db,
        str(row.id),
        PurchaseRequestUpdateAndReply(
            status="submitted",
            project_title=f"{MARKER} edited",
            reply_message=f"{MARKER} here is your number",
        ),
        send,
    )

    assert updated.status == "submitted"
    assert updated.project_title == f"{MARKER} edited"
    assert [call["text"] for call in send.calls] == [f"{MARKER} here is your number"]


def test_update_and_reply_that_omits_status_is_untouched(db):
    """What the frontend actually posts: no ``status`` at all."""
    row = _request(db, status="approved")
    send = _FakeSend()

    updated = _reply(
        db,
        str(row.id),
        PurchaseRequestUpdateAndReply(
            purpose=f"{MARKER} edited purpose",
            reply_message=f"{MARKER} an update for you",
        ),
        send,
    )

    assert updated.status == "approved"
    assert updated.purpose == f"{MARKER} edited purpose"
    assert len(send.calls) == 1


# ----------------------------------------- the stock inquiry reply path, verified
# It setattrs the payload and THEN forces ``status = "responded"``, so a supplied
# status was inert - but only while the flip's condition and the response gate
# agree about the current status. They did not: the gate compares a stripped,
# lower-cased value and the flip read the raw column, so a row holding a
# non-canonical status passed the gate, skipped the flip, and let the payload
# through. Both halves are pinned here.


def _si_reply(db, inquiry_id: str, payload: StockInquiryUpdate):
    with patch.object(
        StockInquiryService, "_enqueue_stock_inquiry_respond_message"
    ) as enqueue:
        result = StockInquiryService(db).update_inquiry_and_reply(
            inquiry_id, payload, respond_user_id="zzt-user"
        )
    return result, enqueue


@pytest.mark.parametrize("attempted", ["closed", "rejected", "voided", "new"])
def test_inquiry_update_and_reply_refuses_a_status_move(db, attempted):
    inquiry = _inquiry(db, status="pending_purchasing")

    with pytest.raises(AppException) as ei:
        _si_reply(
            db,
            str(inquiry.id),
            StockInquiryUpdate(status=attempted, remark=f"{MARKER} edited"),
        )

    assert ei.value.status_code == 422
    assert "stock inquiry" in ei.value.detail["message"]
    db.rollback()
    db.refresh(inquiry)
    assert inquiry.status == "pending_purchasing"
    assert inquiry.remark is None
    assert inquiry.last_responded_by is None


@pytest.mark.parametrize("supplied", ["pending_purchasing", "responded"])
def test_inquiry_update_and_reply_accepts_the_echo_and_its_own_destination(db, supplied):
    """Two statuses move nothing on this path: the current one (read-modify-write)
    and ``responded``, which is where the reply itself lands the inquiry. Refusing
    the second would turn away a caller asking for exactly what the call does."""
    inquiry = _inquiry(db, status="pending_purchasing")

    updated, enqueue = _si_reply(
        db,
        str(inquiry.id),
        StockInquiryUpdate(status=supplied, remark=f"{MARKER} edited"),
    )

    assert enqueue.call_count == 1
    assert updated.status == "responded"
    assert updated.remark == f"{MARKER} edited"
    assert updated.last_responded_by == "zzt-user"


def test_inquiry_update_and_reply_always_lands_on_responded(db):
    """The flip is derived through the response gate's own normalizer now, so the
    branch that skipped it - the only path a payload status could survive - cannot
    be reached from a status the gate lets through."""
    inquiry = _inquiry(db, status="responded")

    updated, enqueue = _si_reply(
        db, str(inquiry.id), StockInquiryUpdate(remark=f"{MARKER} edited")
    )

    assert enqueue.call_count == 1
    assert updated.status == "responded"


def test_the_flip_condition_and_the_response_gate_read_the_same_status(db):
    """The divergence itself, at the source.

    ``assert_response_write_allowed`` normalizes; the flip used a raw ``in``
    against the same tuple. Any value the gate admits must also fire the flip, or
    a payload ``status`` reaches the entity on the difference between them.
    """
    from app.services.response_gate import (
        ALLOWED_RESPONSE_STATUSES,
        is_response_status_allowed,
        response_blocked_reason,
    )

    for status in ("Responded", " pending_purchasing ", "PENDING_PURCHASING"):
        assert response_blocked_reason("stock_inquiry", status) is None
        assert is_response_status_allowed("stock_inquiry", status) is True
        # Exactly the mismatch that used to skip the flip.
        assert status not in ALLOWED_RESPONSE_STATUSES["stock_inquiry"]
