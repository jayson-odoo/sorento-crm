"""RESUBMITTED-STATUS for stock inquiries (stage-based: resubmitted stands in for pending_project_sales).

A resubmit after a rejection lands on ``resubmitted`` instead of ``pending_project_sales``,
and project sales can approve or reject it exactly as they would at that stage.
Plan: documentation/plans/forms/PLAN-resubmitted-status-27oct.md.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import app.services.form_sla_service as form_sla_service_mod
from app.models.access import RespondContact
from app.models.portal import PortalToken
from app.models.procurement import StockInquiry
from app.schemas.procurement import StockInquiryCreate
from app.services.portal_revision_service import PortalRevisionService
from app.services.portal_service import PortalService
from app.services.procurement_service import StockInquiryService
from app.services.stock_inquiry_pdf_service import _STATUS_LABELS as PDF_LABELS
from tests._pg_fixture import blank_session
from tests._revision_harness import seed_config, seed_contact, seed_entity, seed_system_settings


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(PortalService, "_post_submit_notify", lambda self, *a, **kw: None)
    monkeypatch.setattr(
        PortalService, "get_submission", lambda self, token, kind, sid: {"id": sid}
    )
    monkeypatch.setattr(
        form_sla_service_mod, "emit_form_event", lambda *a, **kw: None, raising=False
    )
    for name in (
        "_send_stock_inquiry_contact_message",
        "_notify_team_stock_inquiry",
        "_build_stock_inquiry_view_url",
        "_stock_inquiry_portal_or_view_url",
    ):
        monkeypatch.setattr(StockInquiryService, name, lambda self, *a, **kw: None)


def _seed_portal(db):
    contact_id = str(uuid.uuid4())
    db.add(RespondContact(id=contact_id, phone_number="+6019" + uuid.uuid4().hex[:7], name="ZZT"))
    token = PortalToken(
        id=str(uuid.uuid4()),
        token="tok_" + uuid.uuid4().hex,
        contact_id=contact_id,
        space_id="space-1",
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    inquiry = StockInquiry(
        id=str(uuid.uuid4()),
        status="draft",
        inquiry_number="ZZT-" + uuid.uuid4().hex[:6],
        contact_id=contact_id,
        space_id="space-1",
        portal_draft_at=datetime.utcnow(),
    )
    db.add_all([token, inquiry])
    db.commit()
    return token, inquiry


def _reject(db, inquiry, rejected_from="pending_project_sales"):
    inquiry.status = "rejected"
    inquiry.rejected_from = rejected_from
    inquiry.rejection_reason = "Wrong product code"
    inquiry.rejected_at = datetime.utcnow()
    db.commit()


def _inquiry(db, status):
    row = StockInquiry(id=str(uuid.uuid4()), status=status, inquiry_number="ZZT-" + uuid.uuid4().hex[:6])
    db.add(row)
    db.commit()
    return row


# ---- the submit ---------------------------------------------------------------


def test_portal_first_submit_goes_to_project_sales(db, quiet):
    token, inquiry = _seed_portal(db)
    PortalService(db).submit_draft(token, "stock_inquiry", str(inquiry.id))
    db.refresh(inquiry)
    assert inquiry.status == "pending_project_sales"


@pytest.mark.parametrize("rejected_from", ["pending_project_sales", "pending_purchasing"])
def test_portal_submit_after_rejection_is_resubmitted(db, quiet, rejected_from):
    token, inquiry = _seed_portal(db)
    svc = PortalService(db)
    svc.submit_draft(token, "stock_inquiry", str(inquiry.id))
    _reject(db, inquiry, rejected_from)

    svc.submit_draft(token, "stock_inquiry", str(inquiry.id))

    db.refresh(inquiry)
    assert inquiry.status == "resubmitted"
    assert inquiry.rejected_from is None


def test_api_resubmit_into_project_sales_is_resubmitted(db, quiet, monkeypatch):
    monkeypatch.setattr(
        StockInquiryService, "_require_complete_stock_inquiry_submission", lambda self, *a, **k: None
    )
    inquiry = _inquiry(db, "rejected")
    svc = StockInquiryService(db)
    data = StockInquiryCreate(status="pending_project_sales", remark="new code")

    svc._resubmit_rejected_inquiry(inquiry, data, require_contact_scope=False)

    db.refresh(inquiry)
    assert inquiry.status == "resubmitted"


@pytest.mark.parametrize("target", ["new", "pending_purchasing"])
def test_api_resubmit_into_another_stage_keeps_that_stage(db, quiet, monkeypatch, target):
    """`new` is not a submission yet and `pending_purchasing` skips the review stage that
    `resubmitted` stands in for, so both keep the stage the caller named."""
    monkeypatch.setattr(
        StockInquiryService, "_require_complete_stock_inquiry_submission", lambda self, *a, **k: None
    )
    inquiry = _inquiry(db, "rejected")

    StockInquiryService(db)._resubmit_rejected_inquiry(
        inquiry, StockInquiryCreate(status=target), require_contact_scope=False
    )

    db.refresh(inquiry)
    assert inquiry.status == target


def test_portal_resubmit_notifies_project_sales_as_appealed(db, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        StockInquiryService, "_notify_team_stock_inquiry", lambda self, **kw: captured.update(kw)
    )
    monkeypatch.setattr(StockInquiryService, "get_or_create_view_token", lambda self, rid: None)
    row = SimpleNamespace(id=str(uuid.uuid4()))

    PortalService(db)._post_submit_notify("stock_inquiry", row, is_resubmission=True)

    assert captured["title"] == "Stock inquiry appealed"
    assert "appealed" in captured["intro_plain"]
    assert "resubmit" not in captured["intro_plain"].lower()


# ---- project sales acts on it like pending_project_sales ----------------------


def test_project_sales_can_approve_a_resubmitted_inquiry(db, quiet):
    inquiry = _inquiry(db, "resubmitted")
    StockInquiryService(db).project_sales_approve_inquiry(str(inquiry.id))
    db.refresh(inquiry)
    assert inquiry.status == "pending_purchasing"


def test_project_sales_can_reject_a_resubmitted_inquiry(db, quiet):
    inquiry = _inquiry(db, "resubmitted")
    StockInquiryService(db).project_sales_reject_inquiry(str(inquiry.id), reason="still wrong")
    db.refresh(inquiry)
    assert inquiry.status == "rejected"
    # Reopen restores the review stage, never the transient resubmitted marker.
    assert inquiry.rejected_from == "pending_project_sales"


def test_resubmitted_is_revisable_where_pending_project_sales_is(db):
    seed_system_settings(db)
    seed_config(db, "stock_inquiry", allowed_statuses=["pending_project_sales"])
    contact = seed_contact(db)
    row = seed_entity(db, "stock_inquiry", contact, status="resubmitted")

    policy = PortalRevisionService(db).resolve_policy("stock_inquiry", row)

    assert policy.allowed is True, policy.blocked_reason


def test_pdf_label_reads_appealed():
    assert PDF_LABELS["resubmitted"] == "Appealed"
