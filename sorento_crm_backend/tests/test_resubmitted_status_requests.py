"""RESUBMITTED-STATUS for purchase requests / sponsorship forms (one table, two status columns).

A portal resubmit after a rejection lands on ``status='resubmitted'`` and behaves like
``submitted`` everywhere: the display status, the list filter, revision eligibility and
the team notification wording. Plan: documentation/plans/forms/PLAN-resubmitted-status-27oct.md.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import app.services.form_sla_service as form_sla_service_mod
from app.models.access import RespondContact
from app.models.portal import PortalToken
from app.models.procurement import PurchaseRequestHeader
from app.services.form_action_notify import _pr_display_status
from app.services.portal_revision_service import PortalRevisionService
from app.services.portal_service import PortalService
from app.services.procurement_service import PurchaseRequestService
from app.services.record_context_service import _pr_display_status as _bubble_display_status
from tests._pg_fixture import blank_session
from tests._revision_harness import (
    seed_config,
    seed_contact,
    seed_entity,
    seed_system_settings,
)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def no_side_effects(monkeypatch):
    monkeypatch.setattr(
        PortalService, "_assign_document_number_if_missing", lambda self, kind, row: None
    )
    monkeypatch.setattr(PortalService, "_post_submit_notify", lambda self, *a, **kw: None)
    monkeypatch.setattr(
        PortalService, "get_submission", lambda self, token, kind, sid: {"id": sid}
    )
    monkeypatch.setattr(
        form_sla_service_mod, "emit_form_event", lambda *a, **kw: None, raising=False
    )


def _seed(db, kind="purchase_request"):
    contact_id = str(uuid.uuid4())
    contact = RespondContact(
        id=contact_id, phone_number="+6019" + uuid.uuid4().hex[:7], name="ZZT submitter"
    )
    token = PortalToken(
        id=str(uuid.uuid4()),
        token="tok_" + uuid.uuid4().hex,
        contact_id=contact_id,
        space_id="space-1",
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    header = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_type=kind,
        status="draft",
        source="portal",
        contact_id=contact_id,
        space_id="space-1",
        requested_by_contact_id=contact_id,  # required on submit (FORM-REQUIRED-SERVER)
        portal_draft_at=datetime.utcnow(),
    )
    db.add_all([contact, token, header])
    db.commit()
    return token, header


def _reject(db, header):
    """What `reject_submitted` / `_apply_approval_decision('rejected')` leave behind."""
    header.approval_status = "rejected"
    header.status = "rejected"
    header.approval_comments = "Wrong customer"
    db.commit()


# ---- the submit ---------------------------------------------------------------


@pytest.mark.parametrize("kind", ["purchase_request", "sponsorship_form"])
def test_first_submit_is_submitted(db, no_side_effects, monkeypatch, kind):
    from app.services import sponsorship_link_service

    monkeypatch.setattr(sponsorship_link_service, "assert_project_requirement", lambda *a, **k: None)
    monkeypatch.setattr(PortalService, "_require_sponsorship_unit_prices", lambda self, row: None)
    token, header = _seed(db, kind)

    PortalService(db).submit_draft(token, kind, str(header.id))

    db.refresh(header)
    assert header.status == "submitted"


@pytest.mark.parametrize("kind", ["purchase_request", "sponsorship_form"])
def test_submit_after_rejection_is_resubmitted(db, no_side_effects, monkeypatch, kind):
    from app.services import sponsorship_link_service

    monkeypatch.setattr(sponsorship_link_service, "assert_project_requirement", lambda *a, **k: None)
    monkeypatch.setattr(PortalService, "_require_sponsorship_unit_prices", lambda self, row: None)
    token, header = _seed(db, kind)
    svc = PortalService(db)
    svc.submit_draft(token, kind, str(header.id))
    _reject(db, header)

    svc.submit_draft(token, kind, str(header.id))

    db.refresh(header)
    assert header.status == "resubmitted"
    assert header.approval_status is None


def test_resubmit_notifies_the_team_as_resubmitted(db, monkeypatch):
    captured = {}

    def _fake_notify(self, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(PurchaseRequestService, "_notify_team_on_external_pr_created", _fake_notify)
    monkeypatch.setattr(PurchaseRequestService, "get_or_create_view_token", lambda self, rid: None)
    row = SimpleNamespace(
        id=str(uuid.uuid4()), request_type="purchase_request", request_number="PR-1", project_title="X"
    )

    PortalService(db)._post_submit_notify("purchase_request", row, is_resubmission=True)

    assert captured["integration_action"] == "resubmitted"


@pytest.mark.parametrize(
    "request_type,expected_title",
    [
        ("purchase_request", "Purchase request appealed"),
        ("sponsorship_form", "Sponsorship form appealed"),
    ],
)
def test_resubmitted_notification_wording(db, monkeypatch, request_type, expected_title):
    from app.services.email_template_service import EmailTemplateService

    seen = {}

    def _render(self, code, ctx):
        seen.update(ctx)
        return {"subject": ctx["heading"], "body_text": ctx["intro"], "body_html": ctx["intro"]}

    monkeypatch.setattr(EmailTemplateService, "render_code", _render)
    monkeypatch.setattr(
        PurchaseRequestService, "_get_purchase_request_project_sales_tier1_user_ids", lambda self: []
    )
    # No team configured returns before rendering; give it one user with no email.
    from app.models.user import User

    user = User(
        id=str(uuid.uuid4()),
        email=f"zzt-{uuid.uuid4().hex[:6]}@example.invalid",
        name="ZZT Handler",
        status="ACTIVE",
    )
    db.add(user)
    db.commit()
    monkeypatch.setattr(
        PurchaseRequestService,
        "_get_purchase_request_project_sales_tier1_user_ids",
        lambda self: [str(user.id)],
    )
    _token, header = _seed(db, request_type)

    PurchaseRequestService(db)._notify_team_on_external_pr_created(
        header_id=str(header.id),
        request_type=request_type,
        integration_action="resubmitted",
    )

    assert seen["heading"] == expected_title
    # Owner, 28 Oct: every form calls a send-back after a rejection an appeal.
    assert "appealed" in seen["intro"]
    assert "resubmit" not in (seen["heading"] + seen["intro"]).lower()


# ---- reading it ---------------------------------------------------------------


def test_display_status_reads_appealed():
    header = SimpleNamespace(status="resubmitted", approval_status=None)
    assert _pr_display_status(header) == "Appealed"
    assert _bubble_display_status("resubmitted", None) == "Appealed"


def test_approval_decision_still_wins_over_resubmitted():
    header = SimpleNamespace(status="resubmitted", approval_status="pending")
    assert _pr_display_status(header) == "Pending Approval"


def test_list_filter_resubmitted(db):
    _t1, plain = _seed(db)
    plain.status = "submitted"
    plain.portal_draft_at = None
    _t2, again = _seed(db)
    again.status = "resubmitted"
    again.portal_draft_at = None
    db.commit()

    result = PurchaseRequestService(db).list_requests(approval_status="resubmitted", limit=500)

    ids = {str(r["id"]) if isinstance(r, dict) else str(r.id) for r in result["data"]}
    assert str(again.id) in ids
    assert str(plain.id) not in ids


@pytest.mark.parametrize("kind", ["purchase_request", "sponsorship_form"])
def test_resubmitted_is_revisable_where_submitted_is(db, kind):
    seed_system_settings(db)
    seed_config(db, kind, allowed_statuses=["submitted"])
    contact = seed_contact(db)
    row = seed_entity(db, kind, contact, status="resubmitted")

    policy = PortalRevisionService(db).resolve_policy(kind, row)

    assert policy.allowed is True, policy.blocked_reason
