"""Form-banner person links — PR rejection attribution (UAC REJ-3/REJ-4/HIST-3).

- reject_submitted + in-system approval-decision populate the new rejected_by_id
  column with a resolvable CRM user (REJ-3).
- an external-email approver (no CRM user) leaves rejected_by_id NULL -> banner
  falls back to plain text (REJ-4).
- the detail helper resolves rejected_by_name + rejected_by_wa_phone from
  rejected_by_id, and falls back to the legacy approved_by name string when the
  column is NULL on a rejected PR (HIST-3).

Run: pytest tests/test_pr_reject_dto.py -v
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.models.access import RespondContact
from app.models.procurement import PurchaseRequestHeader
from app.models.user import User
from app.services.procurement_service import PurchaseRequestService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    """A blank Postgres schema, rolled back after the test.

    Was in-memory sqlite, which additionally had to rewrite RespondContact's
    JSONB columns to generic JSON *on the shared table object* -- a global
    mutation leaking into every other test in the run. Postgres needs neither.
    """
    with blank_session() as session:
        yield session


def _user_with_phone(db, phone="60123456789", name="Rejecter"):
    cid = str(uuid.uuid4())
    db.add(RespondContact(id=cid, phone_number=phone, name=name, respond_io_id="io", session_vars={}))
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{name}@t.com", name=name, respond_contact_id=cid))
    db.commit()
    return uid


def _pr(db, **over):
    pid = str(uuid.uuid4())
    base = dict(id=pid, request_type="purchase_request", status="draft")
    base.update(over)
    db.add(PurchaseRequestHeader(**base))
    db.commit()
    return pid


# ---- REJ-3 detail helper: name + phone from rejected_by_id --------------
def test_attach_rejection_person_resolves_name_and_phone(db):
    uid = _user_with_phone(db)
    pid = _pr(db, status="rejected", approval_status="rejected", rejected_by_id=uid)
    svc = PurchaseRequestService(db)
    header = db.query(PurchaseRequestHeader).get(pid)
    svc.attach_rejection_person(header)
    assert header.rejected_by_name == "Rejecter"
    assert header.rejected_by_wa_phone == "60123456789"


# ---- REJ-4 external approver: NULL id -> name only, no phone ------------
def test_attach_rejection_person_external_email_plain_text(db):
    pid = _pr(
        db,
        status="rejected",
        approval_status="rejected",
        rejected_by_id=None,
        approved_by="external.approver@vendor.com",
    )
    svc = PurchaseRequestService(db)
    header = db.query(PurchaseRequestHeader).get(pid)
    svc.attach_rejection_person(header)
    assert header.rejected_by_wa_phone is None
    assert header.rejected_by_name == "external.approver@vendor.com"


# ---- HIST-3 legacy PR: fall back to approved_by name string ------------
def test_attach_rejection_person_legacy_name_string(db):
    pid = _pr(
        db,
        status="rejected",
        approval_status="rejected",
        rejected_by_id=None,
        approved_by="CK Lee",
    )
    svc = PurchaseRequestService(db)
    header = db.query(PurchaseRequestHeader).get(pid)
    svc.attach_rejection_person(header)
    assert header.rejected_by_name == "CK Lee"
    assert header.rejected_by_wa_phone is None


def test_attach_rejection_person_uuid_not_leaked(db):
    # approved_by holding a bare UUID must NOT surface as a name.
    pid = _pr(
        db,
        status="rejected",
        approval_status="rejected",
        rejected_by_id=None,
        approved_by=str(uuid.uuid4()),
    )
    svc = PurchaseRequestService(db)
    header = db.query(PurchaseRequestHeader).get(pid)
    svc.attach_rejection_person(header)
    assert header.rejected_by_name is None
    assert header.rejected_by_wa_phone is None


# ---- REJ-3 write path: reject_submitted stores the actor id ------------
def test_reject_submitted_sets_rejected_by_id(db):
    uid = _user_with_phone(db, name="Actor")
    pid = _pr(db, status="submitted", approval_status=None)
    svc = PurchaseRequestService(db)
    with patch.object(svc, "_notify_contact_on_approval_rejected", return_value=None), patch(
        "app.services.form_sla_service.emit_form_event", return_value=None
    ):
        svc.reject_submitted(pid, rejection_reason="not needed", actor_user_id=uid)
    header = db.query(PurchaseRequestHeader).get(pid)
    assert header.rejected_by_id == uid
    assert header.approval_status == "rejected"


# ---- REJ-3/REJ-4 approval-decision path --------------------------------
def test_apply_approval_decision_rejected_resolvable_actor(db):
    uid = _user_with_phone(db, name="Approver")
    pid = _pr(db, status="submitted", approval_status="pending")
    svc = PurchaseRequestService(db)
    header = db.query(PurchaseRequestHeader).get(pid)
    with patch.object(svc, "_notify_requester_on_rejected", return_value=None), patch.object(
        svc, "_notify_contact_on_approval_rejected", return_value=None
    ), patch("app.services.form_sla_service.emit_form_event", return_value=None):
        svc._apply_approval_decision(
            header, "rejected", approval_comments="no", actor_user_id=uid
        )
    assert db.query(PurchaseRequestHeader).get(pid).rejected_by_id == uid


def test_apply_approval_decision_rejected_external_stays_null(db):
    pid = _pr(db, status="submitted", approval_status="pending", approver_email="ext@vendor.com")
    svc = PurchaseRequestService(db)
    header = db.query(PurchaseRequestHeader).get(pid)
    with patch.object(svc, "_notify_requester_on_rejected", return_value=None), patch.object(
        svc, "_notify_contact_on_approval_rejected", return_value=None
    ), patch("app.services.form_sla_service.emit_form_event", return_value=None):
        svc._apply_approval_decision(
            header, "rejected", approved_by="ext@vendor.com", approval_comments="no",
            actor_user_id=None,
        )
    assert db.query(PurchaseRequestHeader).get(pid).rejected_by_id is None
