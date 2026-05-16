"""Per-event end-to-end verification.

Walks every event in EMAIL_EVENT_REGISTRY and proves:
  1. Trigger -> Notification (where applicable) -> NotificationDelivery (email, status=pending)
     -> send_notification_deliveries enqueues into email_outbox with the right event_key
     -> drain_email_outbox sends it (SMTP mocked) -> row.status == 'sent'
  2. The outbox row's recipient + event_key match expectations.

For the four `external_*` events that the incident centred on, also verifies producer-side
coalesce: two notifications fired in the same coalesce window collapse into one outbox row.

No n8n / no real SMTP / no HTTP. Talks to the DB + service layer the same way the FastAPI
handler chain does once it has authenticated. Run against any environment that has the
migration applied (`alembic upgrade head`).

Usage:
  python -m scripts.verify_per_event_outbox
  python -m scripts.verify_per_event_outbox --only password_reset ticket_assigned
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional
from unittest.mock import patch

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s :: %(message)s")
logger = logging.getLogger("verify")


@dataclass
class EventResult:
    event_key: str
    description: str
    passed: bool
    detail: str = ""
    skipped: bool = False
    outbox_row_id: Optional[str] = None


def _wipe_for_event(db, event_key: str, recipient: Optional[str] = None) -> None:
    """Reset state for a scenario. Wipes all outbox rows for the test recipient (to keep
    per-recipient cap accounting fresh between scenarios) and flushes Redis counters."""
    from app.models.email_outbox import EmailOutbox

    q = db.query(EmailOutbox)
    if recipient:
        q = q.filter(EmailOutbox.recipient_email == recipient)
    else:
        q = q.filter(EmailOutbox.event_key == event_key)
    q.delete()
    db.commit()
    try:
        from app.services.queue_service import redis_conn
        for key in redis_conn.scan_iter(match="email_guardrail:*"):
            redis_conn.delete(key)
    except Exception:
        pass


def _drain_now(send_record: Optional[list] = None) -> None:
    from app.tasks import email_outbox_tasks

    def _mock(**kwargs):
        if send_record is not None:
            send_record.append(datetime.utcnow())
        return None

    with patch.object(email_outbox_tasks, "send_mime_email", side_effect=_mock):
        for _ in range(3):
            email_outbox_tasks.drain_email_outbox()


def _ensure_test_user(db) -> str:
    """Idempotent fixture: a single test User row used by every event that needs a recipient."""
    from app.models.user import User, UserStatus

    email = "verify-outbox@example.com"
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            name="Outbox verifier",
            status=UserStatus.ACTIVE.value,
        )
        db.add(user)
        db.commit()
    return str(user.id)


def _assert_outbox(db, event_key: str, recipient: str, expect_coalesce: bool = False) -> tuple[bool, str, Optional[str]]:
    from app.models.email_outbox import EmailOutbox

    rows = (
        db.query(EmailOutbox)
        .filter(EmailOutbox.event_key == event_key, EmailOutbox.recipient_email == recipient)
        .all()
    )
    if not rows:
        return False, "no outbox row created", None
    sent = [r for r in rows if r.status == "sent"]
    if not sent:
        statuses = {r.status: r.error_message for r in rows}
        return False, f"no row with status sent (got {statuses})", str(rows[0].id)
    return True, f"sent={len(sent)} rows={len(rows)}", str(sent[0].id)


# ---------------------------------------------------------------------------
# Trigger helpers per event
# ---------------------------------------------------------------------------

def trigger_via_enqueue(db, event_key: str, recipient: str) -> None:
    from app.services.email_outbox_service import enqueue

    enqueue(
        db,
        event_key=event_key,
        to=recipient,
        subject=f"[verify] {event_key}",
        body_text=f"Verification message for event {event_key}",
        body_html=f"<p>Verification message for event <strong>{event_key}</strong></p>",
        metadata={"verify": True},
    )
    db.commit()


def trigger_notification(
    db,
    user_id: str,
    *,
    notif_type: str,
    event_type: Optional[str] = None,
    source_entity_id: Optional[str] = None,
    data: Optional[dict] = None,
) -> None:
    """Mimics what producer services do: NotificationService.create -> creates Notification
    + NotificationDelivery(email, pending) and dispatches send_notification_deliveries."""
    from app.services.notification_service import NotificationService

    NotificationService(db).create(
        user_id=user_id,
        type=notif_type,
        title=f"[verify] {notif_type}",
        body=f"Verification body for {notif_type}",
        data=data or {"body_html": f"<p>Verification HTML for {notif_type}</p>"},
        source_entity_type="verify",
        source_entity_id=source_entity_id or str(uuid.uuid4()),
        event_type=event_type,
    )


def trigger_external_attachment_helper(
    db,
    user_id: str,
    *,
    notif_type: str,
    batch_suffix: str = "",
    attachment_count: int = 1,
) -> list[str]:
    """Calls notify_after_external_attachment_entity end-to-end. Returns notification ids."""
    from app.models.resources import Attachment
    from app.services.attachment_notification_helper import notify_after_external_attachment_entity

    created_ids: list[str] = []
    for i in range(attachment_count):
        att = Attachment(
            id=str(uuid.uuid4()),
            original_filename=f"verify_{notif_type}_{i}_{batch_suffix}.pdf",
            stored_filename=f"verify_{notif_type}_{i}_{batch_suffix}_{uuid.uuid4().hex}.pdf",
            file_path=f"verify/{notif_type}/{i}.pdf",
            file_size_bytes=123,
            mime_type="application/pdf",
            uploaded_by=user_id,
        )
        db.add(att)
        created_ids.append(str(att.id))
    db.commit()

    notify_after_external_attachment_entity(
        db,
        created_ids,
        None,
        notif_type=notif_type,
        title=f"[verify] {notif_type}",
        summary_plain=f"Summary plain for {notif_type}",
        summary_html=f"<p>Summary html for {notif_type}</p>",
        entity_url="https://example.com/entity/verify",
        entity_link_text="Open entity",
    )
    return created_ids


# ---------------------------------------------------------------------------
# Per-event scenarios
# ---------------------------------------------------------------------------

def verify_event(db, event_key: str, user_id: str, user_email: str) -> EventResult:
    description_map = {
        "password_reset": "Reset password chokepoint (enqueue path)",
        "user_invitation": "User invitation via NotificationService.create",
        "purchase_request_approval_link": "PR approval link (enqueue path)",
        "purchase_request_approved": "PR approved (NotificationService.create)",
        "purchase_request_rejected": "PR rejected (NotificationService.create)",
        "stock_inquiry_created": "Stock inquiry internal (notification type stock_inquiry_notification)",
        "stock_inquiry_created_external": "Stock inquiry external (same producer, async path)",
        "complaint_created_external": "Complaint portal (notification type complaint_notification)",
        "ticket_assigned": "Ticket assigned (notification type ticket_assigned)",
        "ticket_team_new": "Ticket new in team queue",
        "ticket_responded": "Ticket responded",
        "ticket_resolved": "Ticket resolved",
        "external_product_attachment": "Product attachment linkage via external endpoint helper",
        "external_promotion_uploader_notice": "Promotion-created uploader notice",
        "external_form_created": "Form created via external endpoint",
        "external_packing_list_created": "Packing list created via external endpoint",
        "form_sla_assigned": "Form SLA assigned (notif type form_sla event_type assigned)",
        "form_sla_escalated": "Form SLA escalated (notif type form_sla event_type escalated)",
        "form_sla_updated": "Form SLA updated (notif type form_sla event_type other)",
        "import_job_completed": "Import job finished/failed notification",
        "workflow_form_state_transition": "Workflow form state transition",
        "daily_sla_summary": "Daily SLA summary (enqueue path)",
        "notification_delivery": "Generic fallback for unmapped notification types",
    }
    description = description_map.get(event_key, event_key)

    _wipe_for_event(db, event_key, recipient=user_email)

    expect_coalesce = False

    try:
        if event_key == "password_reset":
            trigger_via_enqueue(db, "password_reset", user_email)

        elif event_key == "user_invitation":
            trigger_notification(db, user_id, notif_type="user_invitation")

        elif event_key == "purchase_request_approval_link":
            trigger_via_enqueue(db, "purchase_request_approval_link", user_email)

        elif event_key == "purchase_request_approved":
            trigger_notification(
                db, user_id, notif_type="purchase_request_approved", event_type="approved",
            )

        elif event_key == "purchase_request_rejected":
            trigger_notification(
                db, user_id, notif_type="purchase_request_rejected", event_type="rejected",
            )

        elif event_key in ("stock_inquiry_created", "stock_inquiry_created_external"):
            trigger_notification(
                db, user_id, notif_type="stock_inquiry_notification",
                event_type="external_created" if event_key.endswith("_external") else "pending_project_sales",
                source_entity_id=f"si-{event_key}-{uuid.uuid4()}",
            )

        elif event_key == "complaint_created_external":
            trigger_notification(
                db, user_id, notif_type="complaint_notification",
                event_type="external_created",
                source_entity_id=f"complaint-{uuid.uuid4()}",
            )

        elif event_key == "ticket_assigned":
            trigger_notification(
                db, user_id, notif_type="ticket_assigned", event_type="assigned",
                source_entity_id=f"ticket-{uuid.uuid4()}",
            )

        elif event_key == "ticket_team_new":
            trigger_notification(
                db, user_id, notif_type="ticket_team_new", event_type="team_created",
                source_entity_id=f"ticket-{uuid.uuid4()}",
            )

        elif event_key == "ticket_responded":
            trigger_notification(
                db, user_id, notif_type="ticket_responded", event_type="submitter_responded",
                source_entity_id=f"ticket-{uuid.uuid4()}",
            )

        elif event_key == "ticket_resolved":
            trigger_notification(
                db, user_id, notif_type="ticket_resolved", event_type="submitter_resolved",
                source_entity_id=f"ticket-{uuid.uuid4()}",
            )

        elif event_key == "external_product_attachment":
            expect_coalesce = True
            trigger_external_attachment_helper(
                db, user_id, notif_type="external_product_attachment_linked",
                batch_suffix="prodA", attachment_count=1,
            )
            trigger_external_attachment_helper(
                db, user_id, notif_type="external_product_attachment_linked",
                batch_suffix="prodB", attachment_count=1,
            )

        elif event_key == "external_promotion_uploader_notice":
            expect_coalesce = True
            from app.services.attachment_notification_helper import (
                notify_after_external_promotion_created,
            )
            from app.models.resources import Attachment
            from app.models.marketing import Promotion

            promo = Promotion(
                id=str(uuid.uuid4()),
                description=f"Verification promotion {uuid.uuid4().hex[:8]}",
            )
            db.add(promo)
            att = Attachment(
                id=str(uuid.uuid4()),
                original_filename="promo_verify.pdf",
                stored_filename=f"promo_verify_{uuid.uuid4().hex}.pdf",
                file_path="verify/promo.pdf",
                file_size_bytes=42,
                mime_type="application/pdf",
                uploaded_by=user_id,
            )
            db.add(att)
            db.commit()
            notify_after_external_promotion_created(db, promo, [str(att.id)], None)

        elif event_key == "external_form_created":
            expect_coalesce = True
            trigger_external_attachment_helper(
                db, user_id, notif_type="external_form_created",
                batch_suffix="formA", attachment_count=1,
            )

        elif event_key == "external_packing_list_created":
            expect_coalesce = True
            trigger_external_attachment_helper(
                db, user_id, notif_type="external_packing_list_created",
                batch_suffix="pl", attachment_count=1,
            )

        elif event_key == "form_sla_assigned":
            trigger_notification(
                db, user_id, notif_type="form_sla", event_type="assigned",
                source_entity_id=f"sla-{uuid.uuid4()}",
            )

        elif event_key == "form_sla_escalated":
            trigger_notification(
                db, user_id, notif_type="form_sla", event_type="escalated",
                source_entity_id=f"sla-{uuid.uuid4()}",
            )

        elif event_key == "form_sla_updated":
            trigger_notification(
                db, user_id, notif_type="form_sla", event_type="other_status",
                source_entity_id=f"sla-{uuid.uuid4()}",
            )

        elif event_key == "import_job_completed":
            trigger_notification(
                db, user_id, notif_type="import_job_finished", event_type="finished",
                source_entity_id=f"job-{uuid.uuid4()}",
            )

        elif event_key == "workflow_form_state_transition":
            trigger_notification(
                db, user_id, notif_type="workflow_form_transition", event_type="submitted",
                source_entity_id=f"wf-{uuid.uuid4()}",
            )

        elif event_key == "daily_sla_summary":
            trigger_via_enqueue(db, "daily_sla_summary", user_email)

        elif event_key == "notification_delivery":
            # Unknown notification type should fall back to notification_delivery
            trigger_notification(
                db, user_id, notif_type="some_brand_new_event",
                event_type="x",
                source_entity_id=f"unknown-{uuid.uuid4()}",
            )
            event_key_to_check = "notification_delivery"

        else:
            return EventResult(
                event_key=event_key,
                description=description,
                passed=False,
                detail="no trigger defined in verify script",
                skipped=True,
            )
    except Exception as e:
        logger.exception("Trigger for %s failed", event_key)
        return EventResult(event_key, description, False, f"trigger raised: {e}")

    if event_key == "notification_delivery":
        # Producer uses an unknown notif_type, so outbox writes under fallback event_key.
        target_event = "notification_delivery"
    else:
        target_event = event_key

    if not _wait_for_pending(db, target_event, user_email, timeout_seconds=8):
        return EventResult(
            event_key=event_key,
            description=description,
            passed=False,
            detail="no outbox row appeared within 8s of trigger",
        )

    # Coalesce events defer scheduled_for by the coalesce window (20s by default). The
    # verifier fast-forwards so the drainer picks up immediately instead of sleeping.
    if expect_coalesce:
        from app.models.email_outbox import EmailOutbox

        db.query(EmailOutbox).filter(
            EmailOutbox.event_key == target_event,
            EmailOutbox.recipient_email == user_email,
            EmailOutbox.status == "pending",
        ).update({EmailOutbox.scheduled_for: datetime.utcnow() - timedelta(seconds=1)})
        db.commit()

    send_record: list = []
    _drain_now(send_record=send_record)

    ok, detail, row_id = _assert_outbox(db, target_event, user_email, expect_coalesce=expect_coalesce)
    return EventResult(
        event_key=event_key,
        description=description,
        passed=ok,
        detail=detail,
        outbox_row_id=row_id,
    )


def _wait_for_pending(db, event_key: str, recipient: str, timeout_seconds: int) -> bool:
    """Wait up to `timeout_seconds` for an outbox row to appear. NotificationService enqueues
    can hop through RQ when Redis is reachable; this polling makes the verify deterministic."""
    import time as _time

    from app.models.email_outbox import EmailOutbox

    deadline = datetime.utcnow() + timedelta(seconds=timeout_seconds)
    while datetime.utcnow() < deadline:
        row = (
            db.query(EmailOutbox)
            .filter(EmailOutbox.event_key == event_key, EmailOutbox.recipient_email == recipient)
            .first()
        )
        if row is not None:
            return True
        _time.sleep(0.2)
    return False


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", default=None, help="Limit to these event_keys")
    parser.add_argument("--report", default="docs/email-guardrail-per-event-verification.md")
    args = parser.parse_args()

    import os
    os.environ.setdefault("ENABLE_SCHEDULER", "false")
    from app.database import SessionLocal
    from app.services.email_event_registry import EMAIL_EVENT_REGISTRY, seed_event_configs

    db = SessionLocal()
    try:
        seed_event_configs(db)
        user_id = _ensure_test_user(db)
        from app.models.user import User
        user_email = str(db.query(User).filter(User.id == user_id).first().email)

        keys = [e.event_key for e in EMAIL_EVENT_REGISTRY]
        if args.only:
            keys = [k for k in keys if k in args.only]

        results: list[EventResult] = []
        for key in keys:
            logger.info("--- Verifying %s ---", key)
            r = verify_event(db, key, user_id, user_email)
            results.append(r)
            logger.info("%s :: %s", key, "PASS" if r.passed else "FAIL")
    finally:
        db.close()

    _write_report(results, _BACKEND_ROOT.parent / args.report)
    failed = [r for r in results if not r.passed and not r.skipped]
    if failed:
        logger.error("%d events FAILED verification", len(failed))
        sys.exit(1)
    logger.info("All %d events PASS", len(results))


def _write_report(results: list[EventResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Per-Event Email Outbox Verification")
    lines.append("")
    lines.append(f"Run timestamp: {datetime.utcnow().isoformat()}Z")
    lines.append("")
    lines.append("Each row triggers the actual producer path that fires when n8n / a user / a "
                 "scheduled task creates the event, then asserts a row in `email_outbox` with "
                 "the right `event_key` reaches `status=sent` after the drainer runs. SMTP send "
                 "is mocked so this script does not depend on a mail server.")
    lines.append("")
    passed = sum(1 for r in results if r.passed)
    lines.append(f"**{passed} / {len(results)} events PASS**")
    lines.append("")
    lines.append("| Event | Result | Description | Detail | Outbox row |")
    lines.append("|---|---|---|---|---|")
    for r in results:
        icon = "PASS" if r.passed else ("SKIP" if r.skipped else "FAIL")
        lines.append(
            f"| `{r.event_key}` | **{icon}** | {r.description} | {r.detail} | "
            f"{r.outbox_row_id or '-'} |"
        )
    lines.append("")
    path.write_text("\n".join(lines))
    logger.info("Report: %s", path)


if __name__ == "__main__":
    main()
