"""RESUBMITTED-STATUS: a submission after a rejection gets status ``resubmitted``.

Plan: documentation/plans/forms/PLAN-resubmitted-status-27oct.md. A first submit still
lands on ``submitted``; only a submit that answers a rejection becomes ``resubmitted``,
and staff can do everything from it that they can from ``submitted``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

import app.services.form_sla_service as form_sla_service_mod
from app.models.access import RespondContact
from app.models.complaints import Complaint
from app.models.portal import PortalToken
from app.services import submission_status
from app.services.portal_service import PortalService
from app.services.response_gate import COMPLAINT, is_response_status_allowed
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _neutralize_side_effects(monkeypatch):
    """Notifications, SLA events and the re-serialization are not under test here."""
    monkeypatch.setattr(PortalService, "_post_submit_notify", lambda self, *a, **kw: None)
    monkeypatch.setattr(
        PortalService, "get_submission", lambda self, token, kind, sid: {"id": sid}
    )
    monkeypatch.setattr(
        form_sla_service_mod, "emit_form_event", lambda *a, **kw: None, raising=False
    )


def _seed_complaint(db):
    contact_id = str(uuid.uuid4())
    contact = RespondContact(
        id=contact_id,
        phone_number="+6019" + uuid.uuid4().hex[:7],
        name="ZZT portal submitter",
    )
    token = PortalToken(
        id=str(uuid.uuid4()),
        token="tok_" + uuid.uuid4().hex,
        contact_id=contact_id,
        space_id="space-1",
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_number="ZZT-" + uuid.uuid4().hex[:8],
        status="draft",
        contact_id=contact_id,
        space_id="space-1",
        portal_draft_at=datetime.utcnow(),
    )
    db.add_all([contact, token, complaint])
    db.commit()
    return token, complaint


def _reject(db, complaint):
    """The state `ComplaintService.decide_complaint` leaves behind."""
    complaint.status = "rejected"
    complaint.rejection_reason = "Not a product issue"
    complaint.rejected_at = datetime.utcnow()
    db.commit()


# ---- the shared helper ------------------------------------------------------


def test_helper_first_submit_is_submitted():
    assert submission_status.status_on_submit(was_rejected=False) == "submitted"


def test_helper_submit_after_rejection_is_resubmitted():
    assert submission_status.status_on_submit(was_rejected=True) == "resubmitted"


def test_helper_awaiting_review_covers_both():
    assert set(submission_status.AWAITING_REVIEW) == {"submitted", "resubmitted"}


# ---- complaint, portal path ------------------------------------------------


def test_complaint_first_submit_stays_submitted(db):
    token, complaint = _seed_complaint(db)

    PortalService(db).submit_draft(token, "complaint", str(complaint.id))

    db.refresh(complaint)
    assert complaint.status == "submitted"


def test_complaint_submit_after_rejection_is_resubmitted(db):
    token, complaint = _seed_complaint(db)
    svc = PortalService(db)
    svc.submit_draft(token, "complaint", str(complaint.id))
    _reject(db, complaint)

    svc.submit_draft(token, "complaint", str(complaint.id))

    db.refresh(complaint)
    assert complaint.status == "resubmitted"


def test_complaint_rejected_twice_is_resubmitted_again(db):
    """CMP26-0219's shape: rejected, resubmitted, rejected again, resubmitted again."""
    token, complaint = _seed_complaint(db)
    svc = PortalService(db)
    svc.submit_draft(token, "complaint", str(complaint.id))
    for _ in range(2):
        _reject(db, complaint)
        svc.submit_draft(token, "complaint", str(complaint.id))
        db.refresh(complaint)
        assert complaint.status == "resubmitted"


# ---- staff can act on a resubmitted complaint ------------------------------


def test_technical_team_can_respond_to_resubmitted_complaint():
    assert is_response_status_allowed(COMPLAINT, "resubmitted")
