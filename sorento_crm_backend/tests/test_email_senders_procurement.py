"""Producer-side tests for #1349 D4: every hand-built mail this lane owns now calls
`EmailTemplateService(db).render_code(code, context)` instead of building HTML itself.

Postgres via tests/_pg_fixture.py. AC ids: documentation/plans/email/email-layout-28sep-acceptance-criteria.md
AC-EM060..067.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.notification import Notification
from app.models.procurement import PurchaseRequestHeader
from app.models.user import User
from app.services.email_layout import has_layout
from app.services.procurement_service import PurchaseRequestService, StockInquiryService
from tests._pg_fixture import pg_session, unique_code


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


def _user(db, **kw) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=kw.pop("email", f"{unique_code('u').lower()}@example.com"),
        name=kw.pop("name", "Test User"),
        **kw,
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture(autouse=True)
def _no_rq(monkeypatch):
    """RQ isn't available in the test process; every producer under test enqueues a
    background job as a best-effort side effect it never depends on for its own
    Notification/EmailOutbox row, so a no-op here is enough."""
    monkeypatch.setattr("app.services.queue_service.enqueue_job", lambda *a, **k: None)


# --------------------------------------------------------------- 1. password reset
def test_password_reset_email_is_branded(db):  # AC-EM060
    from app.api.v1 import auth as auth_module
    from app.database import get_db
    from app.models.email_outbox import EmailOutbox

    user = _user(db, name="Aina")
    app = FastAPI()
    app.include_router(auth_module.router, prefix="/api/v1/auth")
    app.dependency_overrides[get_db] = lambda: db

    with patch("app.services.rate_limit.hit") as mock_hit:
        mock_hit.return_value.allowed = True
        client = TestClient(app)
        resp = client.post("/api/v1/auth/reset-password", json={"email": user.email})
    assert resp.status_code == 200, resp.text

    row = (
        db.query(EmailOutbox)
        .filter(EmailOutbox.event_key == "password_reset", EmailOutbox.recipient_email == user.email)
        .order_by(EmailOutbox.scheduled_for.desc())
        .first()
    )
    assert row is not None
    assert has_layout(row.body_html)
    assert row.subject == "Reset your password"
    assert "Reset your password" in row.body_html
    assert 'class="em-btn-link"' in row.body_html
    assert "change-password?token=" in row.body_html
    assert "change-password?token=" in row.body_text


# --------------------------------------------------------------- 2. user invitation
def test_user_invitation_email_is_branded(db):  # AC-EM061
    from app.api.v1.user_management import users as users_module

    user = _user(db, name="Siti")
    link = users_module._send_invitation_link_for_user(db, user)
    assert "Invitation link sent" in link

    row = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.type == "user_invitation")
        .order_by(Notification.created_at.desc())
        .first()
    )
    assert row is not None
    body_html = (row.data or {}).get("body_html") or ""
    assert has_layout(body_html)
    assert 'class="em-btn-link"' in body_html
    assert "change-password?token=" in body_html
    assert "change-password?token=" in (row.body or "")
    assert row.title == "You're invited to join Sorento" or "invited" in row.title.lower()


# --------------------------------------------------------------- 3. sign-in email updated
def test_account_email_changed_is_branded(db):  # AC-EM062
    from app.services.user_service import UserService

    user = _user(db, email="old@example.com", name="Chen")
    UserService(db)._queue_email_address_change_notification(
        user_id=str(user.id), old_email="old@example.com", new_email="new@example.com"
    )
    row = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.type == "account_email_changed")
        .order_by(Notification.created_at.desc())
        .first()
    )
    assert row is not None
    body_html = (row.data or {}).get("body_html") or ""
    assert has_layout(body_html)
    assert "old@example.com" in body_html and "new@example.com" in body_html
    assert "old@example.com" in (row.body or "") and "new@example.com" in (row.body or "")


# --------------------------------------------------------------- 4. stock inquiry created
def test_stock_inquiry_created_email_is_branded(db, monkeypatch):  # AC-EM063
    u1 = _user(db, name="Purchasing One")
    u2 = _user(db, name="Purchasing Two")
    monkeypatch.setattr(
        StockInquiryService,
        "_get_team_user_ids_for_agent_team_assignment",
        lambda self, *a, **k: [str(u1.id), str(u2.id)],
    )
    inquiry_id = str(uuid.uuid4())
    StockInquiryService(db)._notify_team_stock_inquiry(
        inquiry_id=inquiry_id,
        agent_code="lead_time_enquiries",
        team_assignment_code="purchasing",
        title="Stock Inquiry pending purchasing review",
        intro_plain="Dear Purchasing Team,\n\nA stock inquiry has been approved and is now pending purchasing review.",
        intro_html="Dear Purchasing Team,<br /><br />A stock inquiry has been approved and is now pending purchasing review.",
        event_type="pending_purchasing",
    )
    # The sender writes one row per team user: the first carries the single email to all
    # (data.body_html), the rest are in-app only. Pin the email row, never an unordered first().
    row = (
        db.query(Notification)
        .filter(
            Notification.user_id == str(u1.id),
            Notification.source_entity_type == "stock_inquiry",
            Notification.source_entity_id == inquiry_id,
            Notification.event_type == "pending_purchasing",
        )
        .first()
    )
    assert row is not None
    body_html = (row.data or {}).get("body_html") or ""
    assert has_layout(body_html)
    assert 'class="em-btn-link"' in body_html
    assert f"/procurement-management/stock-inquiries/{inquiry_id}" in body_html
    assert row.title == "Stock Inquiry pending purchasing review"
    assert f"/procurement-management/stock-inquiries/{inquiry_id}" in (row.body or "")


# --------------------------------------------------------------- 5. purchase request submitted
def test_purchase_request_submitted_email_is_branded(db, monkeypatch):  # AC-EM064
    u1 = _user(db, name="Project Sales One")
    monkeypatch.setattr(
        PurchaseRequestService,
        "_get_purchase_request_project_sales_tier1_user_ids",
        lambda self, **k: [str(u1.id)],
    )
    header_id = str(uuid.uuid4())
    PurchaseRequestService(db)._notify_team_on_external_pr_created(
        header_id,
        request_type="purchase_request",
        request_number="PR26-0319",
        project_title="HQ Renovation",
        integration_action="created",
    )
    row = (
        db.query(Notification)
        .filter(
            Notification.source_entity_type == "purchase_request",
            Notification.source_entity_id == header_id,
            Notification.event_type == "external_created",
        )
        .first()
    )
    assert row is not None
    body_html = (row.data or {}).get("body_html") or ""
    assert has_layout(body_html)
    assert 'class="em-btn-link"' in body_html
    assert "PR26-0319" in body_html and "HQ Renovation" in body_html
    assert f"/procurement-management/purchase-requests/{header_id}" in body_html
    assert row.title == "New purchase request created"
    assert "PR26-0319" in (row.body or "")


# --------------------------------------------------------------- 6/7. requester notified
def _seed_pr_header(db, requested_by_uid: str, request_type: str = "purchase_request") -> PurchaseRequestHeader:
    header = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_type=request_type,
        request_number="PR26-0777",
        project_title="Taman Melati Phase 2",
        status="submitted",
        requested_approval_by_user_id=requested_by_uid,
    )
    db.add(header)
    db.flush()
    return header


def test_requester_notified_approved_email_is_branded(db, monkeypatch):  # AC-EM065
    requester = _user(db, name="Requester One")
    header = _seed_pr_header(db, str(requester.id))
    monkeypatch.setattr(PurchaseRequestService, "get_or_create_view_token", lambda self, entity_id: "tok-fixed")

    PurchaseRequestService(db)._notify_requester_on_approved(header)

    row = (
        db.query(Notification)
        .filter(Notification.user_id == requester.id, Notification.type == "purchase_request_approved")
        .order_by(Notification.created_at.desc())
        .first()
    )
    assert row is not None
    body_html = (row.data or {}).get("body_html") or ""
    assert has_layout(body_html)
    assert 'class="em-btn-link"' in body_html
    assert "PR26-0777" in body_html and "Taman Melati Phase 2" in body_html
    assert "tok-fixed" in body_html
    assert row.title == "Purchase Request approved"
    assert "tok-fixed" in (row.body or "")
    # review S2: the bell/push body stays one line; the email text part is the template.
    assert row.body.startswith("Purchase Request PR26-0777 (Project: Taman Melati Phase 2) has been approved.")
    assert "You received this email" not in row.body
    assert "You received this email" in row.data["body_text"]


def test_requester_notified_rejected_email_is_branded(db, monkeypatch):  # AC-EM066
    requester = _user(db, name="Requester Two")
    header = _seed_pr_header(db, str(requester.id), request_type="sponsorship_form")
    monkeypatch.setattr(PurchaseRequestService, "get_or_create_view_token", lambda self, entity_id: "tok-fixed-2")

    PurchaseRequestService(db)._notify_requester_on_rejected(header)

    row = (
        db.query(Notification)
        .filter(Notification.user_id == requester.id, Notification.type == "purchase_request_rejected")
        .order_by(Notification.created_at.desc())
        .first()
    )
    assert row is not None
    body_html = (row.data or {}).get("body_html") or ""
    assert has_layout(body_html)
    assert 'class="em-btn-link"' in body_html
    assert "PR26-0777" in body_html and "Taman Melati Phase 2" in body_html
    assert "tok-fixed-2" in body_html
    assert row.title == "Sponsorship Form rejected"
    assert row.body.startswith("Sponsorship Form PR26-0777 (Project: Taman Melati Phase 2) has been rejected.")
    assert "You received this email" in row.data["body_text"]


# --------------------------------------------------------------- 8. approval link
def test_purchase_request_approval_link_email_is_branded(db):  # AC-EM067
    from app.api.v1.procurement import purchase_requests as pr_module
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.models.email_outbox import EmailOutbox

    header = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_type="purchase_request",
        request_number="PR26-0900",
        project_title="Warehouse Expansion",
        status="submitted",
    )
    db.add(header)
    db.flush()

    app = FastAPI()
    app.include_router(pr_module.router, prefix="/api/v1/procurement/purchase-requests")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4()), "name": "Admin"}
    app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": str(uuid.uuid4()), "name": "Admin"}
    client = TestClient(app)

    resp = client.post(
        f"/api/v1/procurement/purchase-requests/{header.id}/send-approval-link",
        json={"approver_email": "approver@example.com", "send_email": True, "base_url": "https://crm.example.com"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["email_sent"] is True

    row = (
        db.query(EmailOutbox)
        .filter(EmailOutbox.event_key == "purchase_request_approval_link", EmailOutbox.recipient_email == "approver@example.com")
        .order_by(EmailOutbox.scheduled_for.desc())
        .first()
    )
    assert row is not None
    assert has_layout(row.body_html)
    assert row.subject == "Purchase Request - Approval link"
    assert "Review and approve" in row.body_html and 'class="em-btn-link"' in row.body_html
    assert "PR26-0900" in row.body_html and "Warehouse Expansion" in row.body_html
    assert "/approval?token=" in row.body_html
    assert "/approval?token=" in row.body_text
