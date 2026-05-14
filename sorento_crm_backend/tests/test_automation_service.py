"""Integration tests for AutomationService.run_now.

Verifies that running an automation produces NotificationDelivery rows at
status='pending' (visible in /system-management/outgoing-mails) without
attempting an actual SMTP send.

These tests need the Postgres dev DB with the 174 migration applied. They are
isolated by transaction rollback, but they DO insert + read real rows.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Iterator

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.automation import Automation, AutomationRun
from app.models.email_template import EmailTemplate
from app.models.marketing import Promotion
from app.models.notification import Notification, NotificationDelivery
from app.models.user import User, UserRole, UserRoleAssignment


@pytest.fixture(autouse=True)
def _clean_automation_state():
    """Nuke prior-test rows so each test starts from a clean slate.

    AutomationService commits inside its own transaction, so the per-test
    Session rollback is not enough — we delete rows directly via the engine.
    """
    from sqlalchemy import text

    from app.database import engine

    with engine.connect() as conn:
        conn.execute(
            text(
                """
                DELETE FROM notification_deliveries WHERE notification_id IN (
                    SELECT id FROM notifications WHERE source_entity_type = 'automation_run'
                )
                """
            )
        )
        conn.execute(text("DELETE FROM notifications WHERE source_entity_type = 'automation_run'"))
        conn.execute(text("DELETE FROM automation_runs"))
        conn.execute(text("DELETE FROM automations"))
        conn.execute(text("DELETE FROM email_templates WHERE code LIKE 'tpl-%'"))
        conn.execute(text("DELETE FROM promotions WHERE name = 'Test Promo'"))
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


def _mk_user(db: Session, *, email: str | None = None, name: str = "Test User") -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=email or f"u{uuid.uuid4().hex[:8]}@test.local",
        name=name,
        status="ACTIVE",
        is_trashed=False,
    )
    db.add(user)
    db.flush()
    return user


def _mk_role(db: Session, *, slug: str | None = None) -> UserRole:
    role = UserRole(
        id=str(uuid.uuid4()),
        slug=slug or f"role-{uuid.uuid4().hex[:8]}",
        name=f"Role {uuid.uuid4().hex[:6]}",
    )
    db.add(role)
    db.flush()
    return role


def _mk_template(db: Session) -> EmailTemplate:
    t = EmailTemplate(
        id=str(uuid.uuid4()),
        code=f"tpl-{uuid.uuid4().hex[:8]}",
        name="Promotion expiry reminder",
        subject="Promo {{ promotion.code }} expiring on {{ promotion.end_date }}",
        body_html=(
            "<p>Hi {{ recipient.name }},</p>"
            "<p>Promotion <strong>{{ promotion.code }}</strong> "
            "({{ promotion.start_date }} → {{ promotion.end_date }}) "
            "expires in {{ promotion.days_until_end }} days.</p>"
            "<p><a href='{{ promotion.link }}'>Open promotion</a></p>"
        ),
        body_text=None,
        is_active=True,
    )
    db.add(t)
    db.flush()
    return t


def _mk_promotion(db: Session, *, days_until_end: int) -> Promotion:
    today = date.today()
    p = Promotion(
        id=str(uuid.uuid4()),
        description=f"Test Promo {uuid.uuid4().hex[:6].upper()}",
        start_date=today - timedelta(days=2),
        end_date=today + timedelta(days=days_until_end),
        is_active=True,
    )
    db.add(p)
    db.flush()
    return p


def _mk_automation(
    db: Session,
    *,
    template: EmailTemplate,
    creator: User | None,
    days_before: int = 7,
    user_ids: list[str] | None = None,
    role_ids: list[str] | None = None,
    extra_emails: list[str] | None = None,
    schedule_type: str = "manual",
) -> Automation:
    a = Automation(
        id=str(uuid.uuid4()),
        name="Promo expiry reminder",
        enabled=True,
        trigger_type="days_before_promotion_end",
        trigger_config={"days_before": days_before},
        action_type="send_email",
        email_template_id=str(template.id),
        recipient_config={
            "user_ids": user_ids or [],
            "role_ids": role_ids or [],
            "include_promotion_owner": False,
            "extra_emails": extra_emails or [],
        },
        schedule_type=schedule_type,
        run_time=time(9, 0) if schedule_type == "daily" else None,
        timezone="Asia/Kuala_Lumpur",
        created_by_user_id=str(creator.id) if creator else None,
    )
    db.add(a)
    db.flush()
    return a


def test_run_now_inserts_pending_email_deliveries_for_each_recipient(
    db: Session, monkeypatch
) -> None:
    from app.services.automation_service import AutomationService
    from app.services import notification_email

    # Guarantee no SMTP send happens during the run; the deliveries should remain pending.
    smtp_sent = []
    monkeypatch.setattr(
        notification_email,
        "send_notification_email",
        lambda *a, **kw: (smtp_sent.append(("single", a, kw)) or None),
    )
    monkeypatch.setattr(
        notification_email,
        "send_notification_email_multi",
        lambda *a, **kw: (smtp_sent.append(("multi", a, kw)) or None),
    )

    creator = _mk_user(db, email=f"creator-{uuid.uuid4().hex[:6]}@test.local")
    user_a = _mk_user(db, email=f"a-{uuid.uuid4().hex[:6]}@test.local", name="User A")
    user_b = _mk_user(db, email=f"b-{uuid.uuid4().hex[:6]}@test.local", name="User B")

    role = _mk_role(db)
    db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=user_b.id, role_id=role.id))
    db.flush()

    template = _mk_template(db)
    promo = _mk_promotion(db, days_until_end=7)
    db.commit()

    automation = _mk_automation(
        db,
        template=template,
        creator=creator,
        days_before=7,
        user_ids=[str(user_a.id)],
        role_ids=[str(role.id)],
        extra_emails=["external@example.com"],
    )
    db.commit()

    result = AutomationService(db).run_now(str(automation.id))

    assert result["status"] == "success"
    # 3 deduped recipients: user_a (direct), user_b (via role), free-text email
    assert int(result["recipients_attempted"]) == 3

    deliveries = (
        db.query(NotificationDelivery)
        .join(Notification, Notification.id == NotificationDelivery.notification_id)
        .filter(
            Notification.source_entity_type == "automation_run",
            Notification.source_entity_id == result["run_id"],
        )
        .all()
    )
    assert len(deliveries) == 3
    statuses = {str(d.status) for d in deliveries}
    assert statuses == {"pending"}
    channels = {str(d.channel) for d in deliveries}
    assert channels == {"email"}

    notifs = (
        db.query(Notification)
        .filter(
            Notification.source_entity_type == "automation_run",
            Notification.source_entity_id == result["run_id"],
        )
        .all()
    )
    rendered_emails = []
    for n in notifs:
        data = dict(getattr(n, "data") or {})
        rendered_emails.extend(data.get("recipient_emails") or [])
        # Each notification stores rendered HTML and the promotion description in subject.
        assert promo.description in str(n.title)
        assert data.get("body_html"), "body_html must be present for outgoing mails surface"

    assert "external@example.com" in {e.lower() for e in rendered_emails}
    assert user_a.email.lower() in {e.lower() for e in rendered_emails}
    assert user_b.email.lower() in {e.lower() for e in rendered_emails}

    # No actual SMTP send was attempted.
    assert smtp_sent == []


def test_run_now_dedupes_recipients_by_email(db: Session, monkeypatch) -> None:
    from app.services.automation_service import AutomationService
    from app.services import notification_email

    monkeypatch.setattr(notification_email, "send_notification_email", lambda *a, **kw: None)
    monkeypatch.setattr(notification_email, "send_notification_email_multi", lambda *a, **kw: None)

    creator = _mk_user(db, email=f"creator-dedupe-{uuid.uuid4().hex[:6]}@test.local")
    user = _mk_user(db, email=f"shared-{uuid.uuid4().hex[:6]}@test.local")
    role = _mk_role(db)
    db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=user.id, role_id=role.id))
    db.flush()

    template = _mk_template(db)
    _mk_promotion(db, days_until_end=7)
    db.commit()

    automation = _mk_automation(
        db,
        template=template,
        creator=creator,
        days_before=7,
        user_ids=[str(user.id)],
        role_ids=[str(role.id)],
        extra_emails=[user.email],
    )
    db.commit()

    result = AutomationService(db).run_now(str(automation.id))
    assert int(result["recipients_attempted"]) == 1


def test_run_now_with_no_matching_promotion_completes_with_zero_recipients(
    db: Session, monkeypatch
) -> None:
    from app.services.automation_service import AutomationService
    from app.services import notification_email

    monkeypatch.setattr(notification_email, "send_notification_email", lambda *a, **kw: None)
    monkeypatch.setattr(notification_email, "send_notification_email_multi", lambda *a, **kw: None)

    creator = _mk_user(db, email=f"creator2-{uuid.uuid4().hex[:6]}@test.local")
    template = _mk_template(db)
    # promotion expiring in 30 days, automation watches 7 — no match
    _mk_promotion(db, days_until_end=30)
    db.commit()

    automation = _mk_automation(
        db,
        template=template,
        creator=creator,
        days_before=7,
        extra_emails=["x@example.com"],
    )
    db.commit()

    result = AutomationService(db).run_now(str(automation.id))
    assert result["status"] == "success"
    assert int(result["recipients_attempted"]) == 0


def test_evaluate_due_only_picks_enabled_and_due(db: Session, monkeypatch) -> None:
    from app.services.automation_service import AutomationService
    from app.services import notification_email

    monkeypatch.setattr(notification_email, "send_notification_email", lambda *a, **kw: None)
    monkeypatch.setattr(notification_email, "send_notification_email_multi", lambda *a, **kw: None)

    creator = _mk_user(db, email=f"creator3-{uuid.uuid4().hex[:6]}@test.local")
    template = _mk_template(db)
    _mk_promotion(db, days_until_end=7)
    db.commit()

    disabled = _mk_automation(db, template=template, creator=creator, extra_emails=["a@x.com"])
    disabled.enabled = False
    disabled.next_run_at = datetime.utcnow() - timedelta(minutes=1)
    db.flush()

    future = _mk_automation(db, template=template, creator=creator, extra_emails=["b@x.com"])
    future.next_run_at = datetime.utcnow() + timedelta(hours=2)
    db.flush()

    due = _mk_automation(db, template=template, creator=creator, extra_emails=["c@x.com"])
    due.next_run_at = datetime.utcnow() - timedelta(minutes=1)
    db.flush()
    db.commit()

    summary = AutomationService(db).evaluate_due()
    assert summary["due"] == 1
    assert summary["ran"] == 1


def test_email_template_delete_blocked_when_referenced_by_active_automation(
    db: Session, monkeypatch
) -> None:
    from app.services.email_template_service import EmailTemplateService
    from app.services.error_handler import AppException

    creator = _mk_user(db, email=f"creator4-{uuid.uuid4().hex[:6]}@test.local")
    template = _mk_template(db)
    _ = _mk_automation(
        db,
        template=template,
        creator=creator,
        days_before=7,
        extra_emails=["x@x.com"],
    )
    db.commit()

    with pytest.raises(AppException) as exc_info:
        EmailTemplateService(db).delete(str(template.id))
    assert getattr(exc_info.value, "status_code", None) == 409
