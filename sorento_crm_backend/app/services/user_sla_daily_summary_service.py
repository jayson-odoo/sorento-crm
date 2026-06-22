"""Daily SLA performance + outstanding conversations summary per user (scheduled task)."""
from __future__ import annotations

import html
from datetime import datetime, timedelta
from typing import Any
from jose import jwt, JWTError

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.scheduled_task import ScheduledTask
from app.models.sla import ConversationSLAEventLog, ConversationSLATracking
from app.models.user import User, UserStatus
from app.services.notification_service import NotificationService
from app.services.sla_service import MALAYSIA_TZ

SUMMARY_TYPE = "user_sla_daily_summary"
SOURCE_ENTITY_TYPE = "scheduled_task_user_sla_daily_summary"
PREFERENCE_EVENT = "daily_sla_summary"


def _frontend_base() -> str:
    base = (settings.frontend_base_url or "").strip().rstrip("/")
    return base


def conversation_tracking_path(tracking_id: str) -> str:
    return f"/sla-management/conversation-sla-tracking/{tracking_id}"


def generate_unsubscribe_token(user_id: str) -> str:
    payload = {
        "sub": str(user_id),
        "kind": PREFERENCE_EVENT,
        "action": "unsubscribe",
        "exp": int((datetime.utcnow() + timedelta(days=30)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_unsubscribe_token(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise ValueError("Invalid or expired unsubscribe token") from exc
    if payload.get("kind") != PREFERENCE_EVENT or payload.get("action") != "unsubscribe":
        raise ValueError("Invalid unsubscribe token payload")
    uid = payload.get("sub")
    if not uid:
        raise ValueError("Invalid unsubscribe token subject")
    return str(uid)


def set_user_daily_summary_subscription(db: Session, user_id: str, subscribed: bool) -> bool:
    user = db.query(User).filter(User.id == str(user_id)).first()
    if not user:
        return False
    setattr(user, "daily_sla_summary_subscribed", bool(subscribed))
    db.commit()
    return True


def _count_user_events(
    db: Session,
    user_id: str,
    event_type: str,
    since: datetime,
) -> int:
    q = (
        db.query(func.count(ConversationSLAEventLog.id))
        .filter(
            ConversationSLAEventLog.event_type == event_type,
            ConversationSLAEventLog.assigned_to_id == user_id,
            ConversationSLAEventLog.event_at >= since,
        )
    )
    return int(q.scalar() or 0)


def _outstanding_trackings_for_user(db: Session, user_id: str) -> list[ConversationSLATracking]:
    return (
        db.query(ConversationSLATracking)
        .options(joinedload(ConversationSLATracking.contact))
        .filter(
            ConversationSLATracking.assigned_to_id == user_id,
            ConversationSLATracking.is_resolved.is_(False),
        )
        .order_by(ConversationSLATracking.initiated_at.desc())
        .all()
    )


def _build_bodies(
    user: User,
    summary_date_label: str,
    responded_7: int,
    resolved_7: int,
    responded_30: int,
    resolved_30: int,
    rows: list[ConversationSLATracking],
) -> tuple[str, str]:
    display_name = (user.name or user.email or "there").strip()
    base = _frontend_base()
    unsub_token = generate_unsubscribe_token(str(user.id))
    unsub_path = f"/unsubscribe/daily-sla-summary?token={unsub_token}"
    unsub_link = f"{base}{unsub_path}" if base else unsub_path

    lines = [
        f"Hi {display_name},",
        "",
        "Below is your daily summary.",
        "",
        "Performance",
        f"Over last 7 days: {responded_7} responded, {resolved_7} resolved.",
        f"Over last 30 days: {responded_30} responded, {resolved_30} resolved.",
        "",
        f"Outstanding conversations as of today ({summary_date_label}): {len(rows)}",
        "",
    ]
    if rows:
        lines.append("Name | Phone | Link")
        for tr in rows:
            c = tr.contact
            name = (c.name if c else None) or "—"
            phone = (c.phone_number if c else None) or "—"
            rel = conversation_tracking_path(str(tr.id))
            link = f"{base}{rel}" if base else rel
            lines.append(f"{name} | {phone} | {link}")
    else:
        lines.append("You have no outstanding assigned conversations.")
    lines.extend(["", "Thanks for your help in making Sorento a better place to work."])
    lines.extend(["", f"Unsubscribe from this daily summary: {unsub_link}"])
    text_body = "\n".join(lines)

    table_rows = ""
    for tr in rows:
        c = tr.contact
        name = html.escape((c.name if c else None) or "—")
        phone = html.escape((c.phone_number if c else None) or "—")
        rel = conversation_tracking_path(str(tr.id))
        href = html.escape(f"{base}{rel}" if base else rel)
        table_rows += (
            f"<tr><td style='padding:8px;border:1px solid #e5e7eb'>{name}</td>"
            f"<td style='padding:8px;border:1px solid #e5e7eb'>{phone}</td>"
            f"<td style='padding:8px;border:1px solid #e5e7eb'>"
            f"<a href=\"{href}\">Open conversation</a></td></tr>"
        )
    if not rows:
        table_rows = (
            "<tr><td colspan='3' style='padding:8px;border:1px solid #e5e7eb'>"
            "No outstanding assigned conversations.</td></tr>"
        )

    html_body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8" /></head><body style="font-family:system-ui,sans-serif;line-height:1.5;color:#111827">
<p>Hi {html.escape(display_name)},</p>
<p>Below is your daily summary.</p>
<h2 style="font-size:16px;margin-top:20px">Performance</h2>
<p>Over last 7 days: <strong>{responded_7}</strong> responded, <strong>{resolved_7}</strong> resolved.<br/>
Over last 30 days: <strong>{responded_30}</strong> responded, <strong>{resolved_30}</strong> resolved.</p>
<h2 style="font-size:16px;margin-top:20px">Outstanding conversations as of today ({html.escape(summary_date_label)})</h2>
<p><strong>{len(rows)}</strong> conversation(s).</p>
<table style="border-collapse:collapse;width:100%;max-width:640px;font-size:14px">
<thead><tr>
<th align="left" style="padding:8px;border:1px solid #e5e7eb;background:#f9fafb">Name</th>
<th align="left" style="padding:8px;border:1px solid #e5e7eb;background:#f9fafb">Phone number</th>
<th align="left" style="padding:8px;border:1px solid #e5e7eb;background:#f9fafb">Conversation SLA tracking
</th></tr></thead>
<tbody>{table_rows}</tbody>
</table>
<p style="margin-top:24px">Thanks for your help in making Sorento a better place to work.</p>
<p style="margin-top:16px">
  <a href="{html.escape(unsub_link)}"
     style="display:inline-block;padding:10px 14px;border:1px solid #d1d5db;border-radius:8px;text-decoration:none;color:#111827">
    Unsubscribe from this daily summary
  </a>
</p>
</body></html>"""

    return text_body, html_body


def run_user_sla_daily_summary(db: Session, task: ScheduledTask) -> dict[str, Any]:
    if not getattr(settings, "notifications_v1_enabled", True):
        return {"skipped": "notifications_v1_disabled"}

    meta = task.metadata_ or {}
    send_in_app = bool(meta.get("send_in_app", True))
    send_email = bool(meta.get("send_email", True))
    if not send_in_app and not send_email:
        return {"skipped": "no_channels_enabled", "users_considered": 0}

    now_m = datetime.now(MALAYSIA_TZ)
    summary_date_label = now_m.strftime("%d/%m/%Y")
    idempotency_day = now_m.strftime("%Y-%m-%d")
    manual_requested_by = getattr(task, "_manual_run_requested_by_user_id", None)
    is_manual_ad_hoc = bool(manual_requested_by)

    win7 = (datetime.utcnow() - timedelta(days=7)).replace(tzinfo=None)
    win30 = (datetime.utcnow() - timedelta(days=30)).replace(tzinfo=None)
    win24 = (datetime.utcnow() - timedelta(hours=24)).replace(tzinfo=None)

    from sqlalchemy import or_
    from app.services.respond_link_service import resolve_user_respond_io_id

    users_q = (
        db.query(User)
        .filter(
            User.is_trashed.is_(False),
            User.status == UserStatus.ACTIVE.value,
            # Email/in-app summary subscribers OR WhatsApp-summary subscribers.
            or_(
                User.daily_sla_summary_subscribed.is_(True),
                User.notify_whatsapp_summary.is_(True),
            ),
        )
    )
    users = users_q.all()

    title = f"Your daily SLA summary ({summary_date_label})"
    summary_link = f"{_frontend_base()}/sla-management/conversation-sla-tracking"

    sent_in_app = 0
    queued_email = 0
    queued_whatsapp = 0
    skipped_no_address = 0
    skipped_no_outstanding = 0

    for user in users:
        uid = str(user.id)
        responded_7 = _count_user_events(db, uid, "response", win7)
        resolved_7 = _count_user_events(db, uid, "resolution", win7)
        responded_30 = _count_user_events(db, uid, "response", win30)
        resolved_30 = _count_user_events(db, uid, "resolution", win30)
        outstanding = _outstanding_trackings_for_user(db, uid)

        text_body, html_body = _build_bodies(
            user,
            summary_date_label,
            responded_7,
            resolved_7,
            responded_30,
            resolved_30,
            outstanding,
        )
        source_id = (
            f"{uid}:{idempotency_day}:manual:{int(datetime.utcnow().timestamp())}"
            if is_manual_ad_hoc
            else f"{uid}:{idempotency_day}"
        )

        # Email/in-app go to summary subscribers; WhatsApp goes to its own subscribers.
        subscribed_email_inapp = bool(getattr(user, "daily_sla_summary_subscribed", False))
        do_in_app = send_in_app and subscribed_email_inapp
        has_email = bool(user.email and user.email.strip())
        do_email = send_email and has_email and subscribed_email_inapp
        if send_email and subscribed_email_inapp and not has_email:
            skipped_no_address += 1

        # WhatsApp: bounded template (counts + deep link), gated on the dedicated
        # toggle + a resolvable contact (TCK-30). Almost always out-of-window =>
        # template; a full free-form digest can't be a template.
        wa_ok = bool(getattr(user, "notify_whatsapp_summary", False)) and bool(
            resolve_user_respond_io_id(db, user)
        )
        escalated_24 = _count_user_events(db, uid, "escalation", win24)
        resolved_24 = _count_user_events(db, uid, "resolution", win24)
        outstanding_n = len(outstanding)

        # Nothing outstanding => nothing actionable. Skip ALL channels (email +
        # WhatsApp + in-app) so we don't send a "0 conversations" digest that just
        # annoys the recipient.
        if outstanding_n == 0:
            skipped_no_outstanding += 1
            continue

        data: dict[str, Any] = {"body_html": html_body}
        if wa_ok:
            staff_name = (user.name or user.email or "there").strip()
            # Keep the WhatsApp message minimal: greet by name, the date, the
            # outstanding count, and a link to the dashboard. Staff open the
            # system to see the detail — no escalated/resolved breakdown here.
            wa_text = (
                f"Hi {staff_name}, your daily SLA summary for {summary_date_label}: "
                f"{outstanding_n} outstanding. View your tasks: {summary_link}"
            )
            data["whatsapp_use_case"] = "sla_daily_summary"
            data["whatsapp_text"] = wa_text
            data["whatsapp_context_vars"] = {
                "contact_name": staff_name,
                "summary_date": summary_date_label,
                "today_date": summary_date_label,
                "system_url": _frontend_base(),
                "outstanding": str(outstanding_n),
                # Kept for templates already mapping these; new template should use
                # contact_name + summary_date + outstanding + portal_url.
                "escalated_last_24h": str(escalated_24),
                "resolved_last_24h": str(resolved_24),
                "portal_url": summary_link,
                "message": wa_text,
            }

        if not do_in_app and not do_email and not wa_ok:
            continue

        NotificationService(db).create_with_channel_preferences(
            user_id=uid,
            type=SUMMARY_TYPE,
            title=title,
            body=text_body,
            data=data,
            source_entity_type=SOURCE_ENTITY_TYPE,
            source_entity_id=source_id,
            event_type=SUMMARY_TYPE,
            send_in_app=do_in_app,
            send_email=do_email,
            send_web_push=False,
            send_whatsapp=wa_ok,
            whatsapp_pref_attr="notify_whatsapp_summary",
        )
        if do_in_app:
            sent_in_app += 1
        if do_email:
            queued_email += 1
        if wa_ok:
            queued_whatsapp += 1

    return {
        "active_users_scanned": len(users),
        "mode": "manual_ad_hoc" if is_manual_ad_hoc else "scheduled",
        "manual_requested_by_user_id": str(manual_requested_by) if manual_requested_by else None,
        "sent_in_app": sent_in_app,
        "queued_email": queued_email,
        "queued_whatsapp": queued_whatsapp,
        "skipped_no_email": skipped_no_address,
        "skipped_no_outstanding": skipped_no_outstanding,
        "summary_date": summary_date_label,
    }
