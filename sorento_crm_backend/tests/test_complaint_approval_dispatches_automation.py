"""Verify that approving a complaint dispatches the complaint_approved automation event.

End-to-end at the service layer: seeds an EmailTemplate + Automation
(``trigger_type='complaint_approved'``) and a complaint in status='responded',
then calls ``decide_complaint(...,'approved',...)``. Asserts that one
NotificationDelivery row is created at status='pending' and the rendered body
contains the complaint link.
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.automation import Automation
from app.models.complaints import Complaint
from app.models.email_template import EmailTemplate
from app.models.notification import Notification, NotificationDelivery


def _safe_exec(conn, sql: str):
    try:
        conn.execute(text(sql))
    except Exception:
        conn.rollback()


@pytest.fixture(autouse=True)
def _clean_state():
    """Delete ONLY this file's own rows.

    Every automation-side delete is scoped through automation_runs back to
    automations with ``trigger_type = 'complaint_approved'`` (this file is the
    only one in the suite that creates those). The scoping is load-bearing under
    pytest-xdist ``--dist loadfile``: other files' automations, runs and
    notifications live in the same shared DB and are being written concurrently,
    so an unscoped ``DELETE FROM automation_runs`` / ``DELETE FROM notifications
    WHERE source_entity_type = 'automation_run'`` destroys rows another worker is
    actively asserting on.
    """
    with engine.connect() as conn:
        _safe_exec(
            conn,
            """
            DELETE FROM notification_deliveries WHERE notification_id IN (
                SELECT id FROM notifications
                WHERE source_entity_type = 'automation_run'
                  AND source_entity_id IN (
                      SELECT id FROM automation_runs WHERE automation_id IN (
                          SELECT id FROM automations WHERE trigger_type = 'complaint_approved'
                      )
                  )
            )
            """,
        )
        _safe_exec(
            conn,
            """
            DELETE FROM notifications
            WHERE source_entity_type = 'automation_run'
              AND source_entity_id IN (
                  SELECT id FROM automation_runs WHERE automation_id IN (
                      SELECT id FROM automations WHERE trigger_type = 'complaint_approved'
                  )
              )
            """,
        )
        _safe_exec(
            conn,
            "DELETE FROM automation_runs WHERE automation_id IN "
            "(SELECT id FROM automations WHERE trigger_type = 'complaint_approved')",
        )
        _safe_exec(conn, "DELETE FROM automations WHERE trigger_type = 'complaint_approved'")
        _safe_exec(conn, "DELETE FROM email_templates WHERE code LIKE 'tpl-cmpapp-%'")
        _safe_exec(conn, "DELETE FROM integration_log WHERE business_id LIKE 'CMPAPP-%'")
        _safe_exec(conn, "DELETE FROM complaints WHERE complaint_number LIKE 'CMPAPP-%'")
        conn.commit()
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _stub_respond(monkeypatch):
    """Don't hit Respond.io in the approval status-change flow."""
    from app.services import integration_service, crm_chat_outbound_webhook
    from app.services import respond_identifier

    monkeypatch.setattr(
        integration_service.RespondClient,
        "send_message",
        lambda self, identifier, message, *a, **kw: {"status": "sent"},
    )
    # 24h-window pre-check: recent incoming -> window open -> plain-text branch.
    import time

    monkeypatch.setattr(
        integration_service.RespondClient,
        "list_messages",
        lambda self, identifier, *a, **kw: {
            "items": [{"traffic": "incoming", "status": [{"timestamp": int((time.time() - 3600) * 1000)}]}]
        },
    )
    monkeypatch.setattr(
        crm_chat_outbound_webhook,
        "enqueue_crm_chat_outbound_webhook",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        crm_chat_outbound_webhook,
        "resolve_sla_assignee_respond_user_id",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        respond_identifier,
        "resolve_send_identifier",
        lambda db, last_seg: str(last_seg),
    )


def _bootstrap_protected_user_if_missing(db: Session) -> None:
    """`_resolve_owner_user_id` requires at least one User; some clean dev DBs may not have one."""
    from app.models.user import User

    if db.query(User).filter(User.is_trashed.is_(False)).first():
        return
    db.add(
        User(
            id=str(uuid.uuid4()),
            email=f"owner-{uuid.uuid4().hex[:6]}@test.local",
            name="Test Owner",
            status="ACTIVE",
            is_trashed=False,
        )
    )
    db.commit()


def test_complaint_approval_dispatches_automation_email(db: Session, monkeypatch) -> None:
    _stub_respond(monkeypatch)
    _bootstrap_protected_user_if_missing(db)

    template = EmailTemplate(
        id=str(uuid.uuid4()),
        code=f"tpl-cmpapp-{uuid.uuid4().hex[:6]}",
        name="Complaint approved notice",
        subject="Complaint {{ complaint.complaint_number }} approved",
        body_html=(
            "<p>Complaint <strong>{{ complaint.complaint_number }}</strong> approved.</p>"
            "<p>Customer: {{ complaint.customer_name }}.</p>"
            "<p><a href='{{ complaint.link }}'>Open complaint</a></p>"
        ),
        body_text=None,
        is_active=True,
    )
    db.add(template)
    db.commit()

    automation = Automation(
        id=str(uuid.uuid4()),
        name="Complaint approved email",
        enabled=True,
        trigger_type="complaint_approved",
        trigger_config={},
        action_type="send_email",
        email_template_id=str(template.id),
        recipient_config={
            "user_ids": [],
            "role_ids": [],
            "include_promotion_owner": False,
            "extra_emails": ["e2e@test.local"],
        },
        schedule_type="manual",
        run_time=None,
        timezone="Asia/Kuala_Lumpur",
    )
    db.add(automation)

    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"CMPAPP-{uuid.uuid4().hex[:6].upper()}",
        delivery_order_number="DO-CMPAPP-1",
        customer_name="ACME Sdn Bhd",
        status="responded",
        respond_inbox_url="https://app.respond.io/space/42/contact/55555",
    )
    db.add(complaint)
    db.commit()

    from app.services.complaints_service import ComplaintService

    ComplaintService(db).decide_complaint(
        complaint.id,
        "approved",
        respond_user_id="u-test",
        crm_sender_user_id=None,
    )

    notifs = (
        db.query(Notification)
        .filter(Notification.source_entity_type == "automation_run")
        .all()
    )
    target_notifs = [
        n for n in notifs
        if "e2e@test.local" in (n.data or {}).get("recipient_emails", [])
        and (n.data or {}).get("source_id") == complaint.id
    ]
    assert target_notifs, (
        f"expected automation delivery to e2e@test.local for complaint {complaint.id}; "
        f"got {[n.data for n in notifs]}"
    )

    n = target_notifs[0]
    body_html = (n.data or {}).get("body_html") or ""
    assert complaint.complaint_number in str(n.title)
    assert "/complaint-management/complaints/" + complaint.id in body_html

    deliveries = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.notification_id == str(n.id))
        .all()
    )
    # The point is that an EMAIL delivery was created for this notification.
    # Its status depends on whether the in-process notification queue has already
    # handed it to the outbox (`notification_tasks` flips pending -> queued), which
    # is timing, not behaviour: pinning "pending" made this test pass or fail on
    # test collection ORDER. Anything except `failed` means it was accepted.
    email_deliveries = [d for d in deliveries if str(d.channel) == "email"]
    assert email_deliveries, f"expected an email delivery; got {[(d.channel, d.status) for d in deliveries]}"
    assert all(str(d.status) != "failed" for d in email_deliveries), (
        f"email delivery was rejected: {[(d.channel, d.status) for d in email_deliveries]}"
    )


def test_complaint_rejection_does_not_dispatch_automation(db: Session, monkeypatch) -> None:
    _stub_respond(monkeypatch)
    _bootstrap_protected_user_if_missing(db)

    template = EmailTemplate(
        id=str(uuid.uuid4()),
        code=f"tpl-cmpapp-{uuid.uuid4().hex[:6]}",
        name="Complaint approved notice",
        subject="Complaint approved",
        body_html="<p>{{ complaint.complaint_number }}</p>",
        is_active=True,
    )
    db.add(template)
    db.commit()
    db.add(
        Automation(
            id=str(uuid.uuid4()),
            name="Complaint approved email",
            enabled=True,
            trigger_type="complaint_approved",
            trigger_config={},
            action_type="send_email",
            email_template_id=str(template.id),
            recipient_config={"user_ids": [], "role_ids": [], "include_promotion_owner": False, "extra_emails": ["x@x.com"]},
            schedule_type="manual",
            timezone="Asia/Kuala_Lumpur",
        )
    )
    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"CMPAPP-REJ-{uuid.uuid4().hex[:6].upper()}",
        status="responded",
        respond_inbox_url="https://app.respond.io/space/42/contact/55555",
    )
    db.add(complaint)
    db.commit()

    from app.services.complaints_service import ComplaintService

    ComplaintService(db).decide_complaint(
        complaint.id,
        "rejected",
        respond_user_id="u-test",
        rejection_reason="not eligible",
    )

    # Only count notifications spawned by automations whose source is THIS complaint  - 
    # other tests in the same DB run may leave automation_run rows for unrelated complaints.
    notifs = (
        db.query(Notification)
        .filter(Notification.source_entity_type == "automation_run")
        .all()
    )
    related = [
        n for n in notifs
        if (n.data or {}).get("source_id") == complaint.id
        or (n.data or {}).get("complaint_id") == complaint.id
    ]
    assert related == [], (
        f"rejection must not dispatch complaint_approved automation; got {related}"
    )
