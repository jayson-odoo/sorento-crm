"""Admin health dashboard — one aggregation endpoint over operational tables.

`GET /api/v1/system/health/summary` returns an at-a-glance operational health
view for admins. All queries are set-based (func.count + group_by) — no N+1.

Each metric block is computed inside its own guarded helper: if a source table
or model is missing (legacy install) the block is omitted from the response
rather than 500-ing the whole dashboard. Empty tables yield zeroes, not errors.

Timestamp columns on these tables are naive UTC (``DateTime(timezone=False)``),
so the 24h window is computed as timezone-aware UTC and then stripped to naive
UTC for the SQL comparison.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_or_api_key

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------
class EmailOutboxHealth(BaseModel):
    pending: int = 0
    sent: int = 0
    failed: int = 0
    cancelled: int = 0
    failed_last_24h: int = 0


class ImportsHealth(BaseModel):
    total_last_24h: int = 0
    finished_last_24h: int = 0
    failed_last_24h: int = 0
    success_rate: float = 0.0  # percent, finished / total over the last 24h


class ScheduledTasksHealth(BaseModel):
    total: int = 0
    overdue: int = 0  # enabled AND (never scheduled OR next_run_at in the past)
    last_run_failed: int = 0


class IntegrationChannelHealth(BaseModel):
    channel: str
    success: int = 0
    failed: int = 0
    total: int = 0


class IntegrationsHealth(BaseModel):
    channels: list[IntegrationChannelHealth] = []


class AuditTrendPoint(BaseModel):
    date: str  # YYYY-MM-DD (UTC)
    count: int = 0


class AuditActivityHealth(BaseModel):
    count_last_24h: int = 0
    daily_trend: list[AuditTrendPoint] = []


class HealthSummaryResponse(BaseModel):
    generated_at: datetime
    email_outbox: Optional[EmailOutboxHealth] = None
    imports: Optional[ImportsHealth] = None
    scheduled_tasks: Optional[ScheduledTasksHealth] = None
    integrations: Optional[IntegrationsHealth] = None
    audit_activity: Optional[AuditActivityHealth] = None


# ---------------------------------------------------------------------------
# Metric builders — each guarded so a missing model omits its block
# ---------------------------------------------------------------------------
def _email_outbox_health(db: Session, cutoff: datetime) -> Optional[EmailOutboxHealth]:
    try:
        from app.models.email_outbox import EmailOutbox

        counts = dict(
            db.query(EmailOutbox.status, func.count(EmailOutbox.id))
            .group_by(EmailOutbox.status)
            .all()
        )
        failed_24h = (
            db.query(func.count(EmailOutbox.id))
            .filter(EmailOutbox.status == "failed", EmailOutbox.updated_at >= cutoff)
            .scalar()
            or 0
        )
        return EmailOutboxHealth(
            pending=int(counts.get("pending", 0)),
            sent=int(counts.get("sent", 0)),
            failed=int(counts.get("failed", 0)),
            cancelled=int(counts.get("cancelled", 0)),
            failed_last_24h=int(failed_24h),
        )
    except Exception:  # noqa: BLE001 — a missing/legacy table omits the block, never 500s
        return None


def _imports_health(db: Session, cutoff: datetime) -> Optional[ImportsHealth]:
    # NOTE: The plan's "import_logs" block wants a `finished` success status and
    # per-user scoping aggregated across users for the admin view. Only ImportJob
    # (`import_jobs`) carries a `finished` status enum + a user_id column; the
    # `import_logs` table has neither (it stores row-count rollups, no status).
    # So imports health is sourced from ImportJob, aggregated across all users.
    try:
        from app.models.job import ImportJob

        rows = (
            db.query(ImportJob.status, func.count(ImportJob.id))
            .filter(ImportJob.created_at >= cutoff)
            .group_by(ImportJob.status)
            .all()
        )
        counts = {str(status): int(n) for status, n in rows}
        total = sum(counts.values())
        finished = counts.get("finished", 0)
        failed = counts.get("failed", 0)
        success_rate = round((finished / total) * 100, 1) if total else 0.0
        return ImportsHealth(
            total_last_24h=total,
            finished_last_24h=finished,
            failed_last_24h=failed,
            success_rate=success_rate,
        )
    except Exception:  # noqa: BLE001
        return None


def _scheduled_tasks_health(db: Session, now: datetime) -> Optional[ScheduledTasksHealth]:
    try:
        from app.models.scheduled_task import ScheduledTask

        total = db.query(func.count(ScheduledTask.id)).scalar() or 0
        overdue = (
            db.query(func.count(ScheduledTask.id))
            .filter(
                ScheduledTask.enabled.is_(True),
                (ScheduledTask.next_run_at.is_(None))
                | (ScheduledTask.next_run_at < now),
            )
            .scalar()
            or 0
        )
        last_run_failed = (
            db.query(func.count(ScheduledTask.id))
            .filter(ScheduledTask.last_status == "failed")
            .scalar()
            or 0
        )
        return ScheduledTasksHealth(
            total=int(total),
            overdue=int(overdue),
            last_run_failed=int(last_run_failed),
        )
    except Exception:  # noqa: BLE001
        return None


def _integrations_health(db: Session, cutoff: datetime) -> Optional[IntegrationsHealth]:
    try:
        from app.models.integration import IntegrationLog
        from app.services.n8n_liveness_service import HEALTHCHECK_CHANNEL

        rows = (
            db.query(
                IntegrationLog.integration_channel,
                IntegrationLog.status,
                func.count(IntegrationLog.id),
            )
            .filter(
                IntegrationLog.created_at >= cutoff,
                # Liveness probes are not a business integration channel — the
                # watchdog/digest surface their status separately.
                IntegrationLog.integration_channel != HEALTHCHECK_CHANNEL,
            )
            .group_by(IntegrationLog.integration_channel, IntegrationLog.status)
            .all()
        )
        by_channel: dict[str, IntegrationChannelHealth] = {}
        for channel, status, n in rows:
            key = channel or "unknown"
            entry = by_channel.setdefault(key, IntegrationChannelHealth(channel=key))
            n = int(n)
            entry.total += n
            if status == "success":
                entry.success += n
            elif status == "failed":
                entry.failed += n
        channels = sorted(by_channel.values(), key=lambda c: c.channel)
        return IntegrationsHealth(channels=channels)
    except Exception:  # noqa: BLE001
        return None


def _audit_activity_health(db: Session, cutoff: datetime, now: datetime) -> Optional[AuditActivityHealth]:
    try:
        from app.models.audit import AuditLog

        count_24h = (
            db.query(func.count(AuditLog.id))
            .filter(AuditLog.changed_at >= cutoff)
            .scalar()
            or 0
        )
        # 7-day daily trend (UTC calendar day). func.date works on both pg + sqlite.
        seven_days_ago = (now - timedelta(days=7)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_rows = (
            db.query(func.date(AuditLog.changed_at), func.count(AuditLog.id))
            .filter(AuditLog.changed_at >= seven_days_ago)
            .group_by(func.date(AuditLog.changed_at))
            .all()
        )
        by_day: dict[str, int] = {}
        for day, n in day_rows:
            by_day[str(day)] = int(n)
        trend: list[AuditTrendPoint] = []
        for offset in range(7, -1, -1):
            day = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
            trend.append(AuditTrendPoint(date=day, count=by_day.get(day, 0)))
        return AuditActivityHealth(count_last_24h=int(count_24h), daily_trend=trend)
    except Exception:  # noqa: BLE001
        return None


@router.get("/health/summary", response_model=HealthSummaryResponse)
async def get_health_summary(
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Aggregate operational health across email outbox, imports, scheduled
    tasks, integrations, and audit activity. Read-only; safe to poll.

    Auth-only (no bespoke permission), matching the sibling admin-utility pages
    (Audit Logs, Import Logs, Integration Logs) under System Management."""
    now_aware = datetime.now(timezone.utc)
    now = now_aware.replace(tzinfo=None)  # naive UTC to match stored columns
    cutoff = now - timedelta(hours=24)

    return HealthSummaryResponse(
        generated_at=now_aware,
        email_outbox=_email_outbox_health(db, cutoff),
        imports=_imports_health(db, cutoff),
        scheduled_tasks=_scheduled_tasks_health(db, now),
        integrations=_integrations_health(db, cutoff),
        audit_activity=_audit_activity_health(db, cutoff, now),
    )
