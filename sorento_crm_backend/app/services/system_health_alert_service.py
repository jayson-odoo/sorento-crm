"""System-health watchdog + daily digest (WS3).

Two entry points, both registered as scheduled-task handlers:

- ``run_health_watchdog(db)`` — frequent (every ~10 min). Evaluates the three
  IMMEDIATE conditions and alerts admins on a transition into bad (de-duped via
  ``health_alert_state`` so a persistently-bad condition doesn't spam each tick;
  re-alerts only after ``ALERT_COOLDOWN``). Emits a recovery note on bad->ok.
- ``run_health_daily_digest(db)`` — daily. Sends admins the full health summary.

Recipients come from ``system_settings.health_notify_role_ids`` (fallback: all
superadmin/admin users). Delivery = in-app + email, gated by settings toggles and
task metadata. The actual fan-out lives in ``_notify_admins``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.health_alert_state import HealthAlertState
from app.models.integration import IntegrationLog
from app.models.scheduled_task import ScheduledTask
from app.services.n8n_liveness_service import HEALTHCHECK_CHANNEL

logger = logging.getLogger(__name__)

# Re-alert cadence for a condition that stays bad across ticks.
ALERT_COOLDOWN = timedelta(hours=6)
# A liveness probe older than this with no success => n8n considered down.
LIVENESS_STALE = timedelta(hours=3)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# De-dup state machine
# ---------------------------------------------------------------------------
def _get_state(db: Session, alert_key: str) -> HealthAlertState:
    row = db.query(HealthAlertState).filter(HealthAlertState.alert_key == alert_key).first()
    if row is None:
        row = HealthAlertState(alert_key=alert_key, state="ok")
        db.add(row)
        db.flush()
    return row


def _should_fire(row: HealthAlertState, now: datetime) -> bool:
    """Fire on transition ok->alerting, or if still alerting past the cooldown."""
    if row.state != "alerting":
        return True
    if row.last_alerted_at is None:
        return True
    return (now - row.last_alerted_at) >= ALERT_COOLDOWN


def _mark_alerting(row: HealthAlertState, now: datetime, detail: str) -> None:
    row.state = "alerting"
    row.last_alerted_at = now
    row.last_detail = detail


def _mark_ok(row: HealthAlertState, now: datetime) -> None:
    """Clear the condition. `last_alerted_at` is deliberately left intact so the
    cooldown still applies if the condition flaps straight back."""
    row.state = "ok"
    row.last_detail = None


# ---------------------------------------------------------------------------
# Condition evaluators — return (is_bad, detail)
# ---------------------------------------------------------------------------
def _eval_n8n_liveness(db: Session, now: datetime) -> tuple[bool, str]:
    """Bad if the latest n8n_healthcheck probe is failed, or no success within LIVENESS_STALE."""
    latest = (
        db.query(IntegrationLog)
        .filter(IntegrationLog.integration_channel == HEALTHCHECK_CHANNEL)
        .order_by(IntegrationLog.created_at.desc())
        .first()
    )
    if latest is None:
        return False, ""  # probe never ran yet; not an alert (the ping task seeds it)
    if latest.status == "failed":
        return True, f"n8n liveness probe FAILED ({latest.error_code or 'no callback'}) at {latest.created_at:%Y-%m-%d %H:%M} UTC"
    if latest.status == "success":
        return False, ""
    # pending/sent/processing — only bad once stale (probe fired but never confirmed)
    if latest.created_at and (now - latest.created_at) >= LIVENESS_STALE:
        return True, f"n8n liveness probe stuck '{latest.status}' since {latest.created_at:%Y-%m-%d %H:%M} UTC (no callback)"
    return False, ""


def _eval_failed_integrations(db: Session, now: datetime, threshold: int) -> tuple[bool, str]:
    """Bad if any non-healthcheck channel exceeds `threshold` failures in the last 24h."""
    cutoff = now - timedelta(hours=24)
    rows = (
        db.query(IntegrationLog.integration_channel, func.count(IntegrationLog.id))
        .filter(
            IntegrationLog.created_at >= cutoff,
            IntegrationLog.status == "failed",
            IntegrationLog.integration_channel != HEALTHCHECK_CHANNEL,
        )
        .group_by(IntegrationLog.integration_channel)
        .all()
    )
    hot = [(ch or "unknown", int(n)) for ch, n in rows if int(n) >= threshold]
    if not hot:
        return False, ""
    detail = "; ".join(f"{ch}: {n} failed/24h" for ch, n in hot)
    return True, f"Integration failure spike — {detail}"


_MALAYSIA_TZ = timezone(timedelta(hours=8))


def _humanize_delta(delta: timedelta) -> str:
    """'23m late' beats '0:23:04.184' in an email a human has to act on."""
    total = int(delta.total_seconds())
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m"
    if total < 86400:
        hours, minutes = divmod(total // 60, 60)
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days, hours = divmod(total // 3600, 24)
    return f"{days}d {hours}h" if hours else f"{days}d"


def _humanize_interval(task: ScheduledTask) -> str:
    value = int(getattr(task, "interval_value", 0) or 0)
    unit = str(getattr(task, "interval_unit", "") or "")
    if value == 1 and unit.endswith("s"):
        unit = unit[:-1]
    return f"every {value} {unit}".strip()


def _malaysia_wall_clock(dt: Optional[datetime]) -> str:
    """Naive-UTC column -> Malaysia wall clock. Recipients are in MYT."""
    if not isinstance(dt, datetime):
        return "never"
    aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    return aware.astimezone(_MALAYSIA_TZ).strftime("%d/%m/%Y %H:%M") + " MYT"


def _task_run_log_url(task: ScheduledTask) -> str:
    base = (getattr(settings, "frontend_base_url", None) or "").strip().rstrip("/")
    path = f"/system-management/scheduled-tasks/{getattr(task, 'id', '')}"
    return f"{base}{path}" if base else path


def _eval_scheduled_tasks(db: Session, now: datetime) -> tuple[bool, str]:
    """Bad if any enabled task last-run failed or is overdue past its grace period.

    Overdue comes from the shared helper in `scheduled_task_service`, the same one
    the health dashboard card calls, so the two surfaces cannot disagree. The old
    inline `next_run_at` query is gone: that column is display-only and the
    scheduler never consulted it, which is why this alert fired on healthy tasks.
    """
    from app.services.scheduled_task_service import get_overdue_tasks

    tasks = db.query(ScheduledTask).filter(ScheduledTask.enabled.is_(True)).all()
    failed = [t.key for t in tasks if (t.last_status or "") == "failed"]
    overdue = get_overdue_tasks(db, now)

    if not failed and not overdue:
        return False, ""

    parts = []
    if failed:
        parts.append("last-run failed: " + ", ".join(sorted(set(failed))))
    if overdue:
        # Itemized: the previous body was a bare list of keys, which told the
        # reader nothing about which run was late or by how much.
        items = "\n".join(
            f"  • {o.task.key} ({o.task.name}) — {_humanize_interval(o.task)}, "
            f"last run {_malaysia_wall_clock(o.task.last_run_at)}, "
            f"{_humanize_delta(o.late_by)} late — {_task_run_log_url(o.task)}"
            for o in overdue
        )
        parts.append(f"overdue ({len(overdue)}):\n{items}")

    return True, "Scheduled tasks — " + "; ".join(parts)


def _eval_chat_latency(db: Session, now: datetime, settings) -> tuple[bool, str]:
    """WhatsApp round-trip health, as three independent signals.

    A single rolling percentile is not enough. At volume, one turn that never completes
    — the shape a dropped webhook takes — never moves p99 at all, so it would degrade
    silently. Hence a hard ceiling with no minimum sample, plus an explicit
    unanswered-turn check whose subjects are absent from the distribution by definition.
    """
    from app.services import chat_latency_service as latency

    target = int(getattr(settings, "chat_latency_p99_target_seconds", 10) or 10) if settings else 10
    multiplier = int(getattr(settings, "chat_latency_ceiling_multiplier", 3) or 3) if settings else 3
    no_reply_min = int(getattr(settings, "chat_latency_no_reply_minutes", 5) or 5) if settings else 5
    min_sample = int(getattr(settings, "chat_latency_min_sample", 30) or 30) if settings else 30

    window_start = now - timedelta(hours=1)
    parts: list[str] = []

    stats = latency.compute_latency_stats(db, since=window_start)
    verdict = latency.evaluate_breach(stats, target_seconds=target, min_sample=min_sample)
    if verdict.breached:
        parts.append(f"degraded — {verdict.reason}")

    ceiling = target * multiplier
    stalled = latency.get_stalled_turns(db, since=window_start, ceiling_seconds=ceiling)
    if stalled:
        worst = max(stalled, key=lambda t: t.latency_seconds)
        parts.append(
            f"stalled turns ({len(stalled)}) past {ceiling}s ceiling — "
            f"worst {worst.latency_seconds:.0f}s on turn {worst.turn_id}"
        )

    unanswered = latency.get_unanswered_turns(db, now=now, older_than_seconds=no_reply_min * 60)
    if unanswered:
        worst = unanswered[0]
        parts.append(
            f"no reply ({len(unanswered)}) after {no_reply_min}m — "
            f"longest {worst.waiting_seconds / 60:.0f}m on turn {worst.turn_id}"
        )

    if not parts:
        return False, ""
    return True, "WhatsApp round trip — " + "; ".join(parts)


def run_chat_latency_watchdog(db: Session) -> dict:
    """Entry point for the `chat_latency_watchdog` scheduled task.

    Shares the health_alert_state de-dup machinery with the other conditions, so a
    sustained incident produces one alert plus one recovery notice rather than one per
    evaluation tick.
    """
    from app.models.user import SystemSetting

    settings = db.query(SystemSetting).first()
    if settings is not None and settings.health_alerts_enabled is False:
        return {"skipped": "alerts_disabled"}

    now = _utcnow_naive()
    is_bad, detail = _eval_chat_latency(db, now, settings)

    row = _get_state(db, "chat_latency")
    fired = recovered = False

    if is_bad:
        if _should_fire(row, now):
            _notify_admins(
                db, settings,
                subject="⚠️ System health alert: chat_latency",
                lines=[detail],
                is_alert=True,
                dedup_id=f"alert:chat_latency:{now:%Y-%m-%dT%H:%M:%S}",
            )
            _mark_alerting(row, now, detail)
            fired = True
    else:
        if row.state == "alerting":
            _notify_admins(
                db, settings,
                subject="✅ Recovered: chat_latency",
                lines=["WhatsApp round trip is back within its SLA."],
                is_alert=False,
                dedup_id=f"recovered:chat_latency:{now:%Y-%m-%dT%H:%M:%S}",
            )
            recovered = True
        _mark_ok(row, now)

    db.commit()
    return {"bad": is_bad, "detail": detail, "fired": fired, "recovered": recovered}


# ---------------------------------------------------------------------------
# Watchdog entry point
# ---------------------------------------------------------------------------
def run_health_watchdog(db: Session) -> dict:
    from app.models.user import SystemSetting

    settings = db.query(SystemSetting).first()
    if settings is not None and settings.health_alerts_enabled is False:
        return {"skipped": "alerts_disabled"}

    threshold = int(getattr(settings, "health_integration_fail_threshold", 10) or 10) if settings else 10
    now = _utcnow_naive()

    conditions = {
        "n8n_liveness": _eval_n8n_liveness(db, now),
        "integration_spike": _eval_failed_integrations(db, now, threshold),
        "scheduled_tasks": _eval_scheduled_tasks(db, now),
    }

    fired: list[str] = []
    recovered: list[str] = []
    for key, (is_bad, detail) in conditions.items():
        row = _get_state(db, key)
        if is_bad:
            if _should_fire(row, now):
                _notify_admins(
                    db, settings,
                    subject=f"⚠️ System health alert: {key}",
                    lines=[detail],
                    is_alert=True,
                    # Unique per genuine fire (health_alert_state already rate-limits
                    # via _should_fire) so each real alert produces its own notification.
                    dedup_id=f"alert:{key}:{now:%Y-%m-%dT%H:%M:%S}",
                )
                _mark_alerting(row, now, detail)
                fired.append(key)
        else:
            if row.state == "alerting":
                _notify_admins(
                    db, settings,
                    subject=f"✅ System health recovered: {key}",
                    lines=[f"{key} back to normal (was: {row.last_detail or 'n/a'})"],
                    is_alert=False,
                    dedup_id=f"recovered:{key}:{now:%Y-%m-%dT%H:%M:%S}",
                )
                recovered.append(key)
            row.state = "ok"
            row.last_detail = None

    db.commit()
    return {"fired": fired, "recovered": recovered}


# ---------------------------------------------------------------------------
# Daily digest entry point
# ---------------------------------------------------------------------------
def run_health_daily_digest(db: Session, task=None) -> dict:
    from app.models.user import SystemSetting
    from app.api.v1.system import health as health_mod

    settings = db.query(SystemSetting).first()
    if settings is not None and settings.health_digest_enabled is False:
        return {"skipped": "digest_disabled"}

    now = _utcnow_naive()
    cutoff = now - timedelta(hours=24)

    email_h = health_mod._email_outbox_health(db, cutoff)
    imports_h = health_mod._imports_health(db, cutoff)
    tasks_h = health_mod._scheduled_tasks_health(db, now)
    integ_h = health_mod._integrations_health(db, cutoff)
    audit_h = health_mod._audit_activity_health(db, cutoff, now)
    live_bad, live_detail = _eval_n8n_liveness(db, now)

    lines: list[str] = [f"System health digest — {now:%Y-%m-%d %H:%M} UTC", ""]
    lines.append(f"n8n liveness: {'⚠️ ' + live_detail if live_bad else '✅ OK'}")
    if integ_h and integ_h.channels:
        fails = [c for c in integ_h.channels if c.failed]
        lines.append("Integrations (24h): " + (
            "; ".join(f"{c.channel} {c.failed} failed/{c.total}" for c in fails) if fails else "no failures"
        ))
    if tasks_h:
        lines.append(f"Scheduled tasks: {tasks_h.total} total, {tasks_h.overdue} overdue, {tasks_h.last_run_failed} last-run failed")
    if imports_h:
        lines.append(f"Imports (24h): {imports_h.finished_last_24h}/{imports_h.total_last_24h} finished ({imports_h.success_rate}%), {imports_h.failed_last_24h} failed")
    if email_h:
        lines.append(f"Email queue: {email_h.pending} pending, {email_h.failed_last_24h} failed/24h")
    if audit_h:
        floor = int(getattr(settings, "health_audit_volume_floor", 0) or 0) if settings else 0
        flag = " ⚠️ below floor" if floor and audit_h.count_last_24h < floor else ""
        lines.append(f"Audit activity (24h): {audit_h.count_last_24h}{flag}")

    _notify_admins(
        db, settings,
        subject=f"📋 System health digest — {now:%Y-%m-%d}",
        lines=lines,
        is_alert=False,
        # The digest has no entity identity — every run is a legitimately new digest,
        # so it must NOT dedup on a stable key (that made "Run now" a silent no-op).
        # Second-granular id: each manual/scheduled fire notifies afresh; only a
        # genuine same-instant double-fire (a <1s retry) collapses — which we want.
        dedup_id=f"digest:{now:%Y-%m-%dT%H:%M:%S}",
        task=task,
    )
    db.commit()
    recipients = _resolve_recipient_user_ids(db, settings)
    return {"sent": bool(recipients), "recipients": len(recipients), "n8n_liveness_bad": live_bad}


# ---------------------------------------------------------------------------
# Notification fan-out (in-app + email to admins).
# ---------------------------------------------------------------------------
def _resolve_recipient_user_ids(db: Session, settings) -> list[str]:
    """Users to notify: the union of members of ``health_notify_role_ids`` and the
    explicitly-picked ``health_notify_user_ids``. If NEITHER is configured, fall
    back to superadmin+admin. Restricted to active, non-trashed users.
    """
    from app.models.user import User, UserRole, UserRoleAssignment, UserStatus

    role_ids = list(getattr(settings, "health_notify_role_ids", None) or []) if settings else []
    explicit_user_ids = list(getattr(settings, "health_notify_user_ids", None) or []) if settings else []

    # Fallback only when nothing at all was chosen (no roles AND no individual users).
    if not role_ids and not explicit_user_ids:
        roles = db.query(UserRole.id).filter(UserRole.slug.in_(["superadmin", "admin"])).all()
        role_ids = [str(r[0]) for r in roles]

    candidate_ids: set[str] = {str(uid) for uid in explicit_user_ids if uid}
    if role_ids:
        uid_rows = (
            db.query(UserRoleAssignment.user_id)
            .filter(UserRoleAssignment.role_id.in_(role_ids))
            .distinct()
            .all()
        )
        candidate_ids.update(str(r[0]) for r in uid_rows if r and r[0])
    candidate_ids = list(candidate_ids)
    if not candidate_ids:
        return []
    active = (
        db.query(User.id)
        .filter(
            User.id.in_(candidate_ids),
            User.is_trashed.is_(False),
            User.status == UserStatus.ACTIVE.value,
        )
        .all()
    )
    return [str(u[0]) for u in active]


def _notify_admins(
    db, settings, *, subject: str, lines: list[str], is_alert: bool, dedup_id: str, task=None
) -> None:
    """Fan out an in-app + email notification to the resolved admin recipients.

    ``dedup_id`` becomes the notification ``source_entity_id`` — the dedup key is
    ``(user_id, source_entity_type, source_entity_id, event_type)`` with NO time
    window, so a CONSTANT id would let each user receive this notification only
    once ever (the daily digest would fire once and never again). Callers pass a
    period/condition-scoped id (e.g. ``digest:2026-07-13``) so repeats within the
    same period stay idempotent while a new day / new fire notifies afresh.
    """
    from app.services.notification_service import NotificationService

    recipients = _resolve_recipient_user_ids(db, settings)
    if not recipients:
        logger.warning("[health-notify] no recipients for: %s", subject)
        return

    meta = (getattr(task, "metadata_", None) or {}) if task is not None else {}
    send_in_app = bool(meta.get("send_in_app", True))
    send_email = bool(meta.get("send_email", True))
    body = "\n".join(lines)
    ns = NotificationService(db)
    for uid in recipients:
        try:
            ns.create_with_channel_preferences(
                user_id=uid,
                type="system_health",
                title=subject,
                body=body,
                data={"lines": lines, "is_alert": is_alert},
                source_entity_type="system_health",
                source_entity_id=dedup_id,
                event_type="health_alert" if is_alert else "health_digest",
                send_in_app=send_in_app,
                send_email=send_email,
            )
        except Exception as e:  # best-effort per recipient
            logger.warning("[health-notify] send failed for user %s (%s): %s", uid, subject, e)
