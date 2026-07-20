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
from types import SimpleNamespace

from app.services.integration_outcome import (
    OUTCOME_BENIGN,
    OUTCOME_FAILED,
    OUTCOME_SUCCESS,
    classify,
)
from app.services.integration_failure_signature import top_failures
from typing import Optional

from fastapi import APIRouter, Depends, Query
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
    # Lifetime totals — these are backlog/ledger figures, not windowed. Rendering
    # them without the windowed count is what made 63 all-time failures read as a
    # live incident.
    pending: int = 0
    sent: int = 0
    failed: int = 0
    cancelled: int = 0
    # Failures whose rows were created inside the selected window.
    failed_in_window: int = 0
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


class FailureSignatureOut(BaseModel):
    signature: str
    sample_message: str
    status_code: Optional[int] = None
    count: int = 0
    # Literal substrings shared by the whole group, AND-ed by the log-list
    # drill-down. A list, not one substring — see integration_failure_signature.
    filter_terms: list[str] = []


class IntegrationChannelHealth(BaseModel):
    channel: str
    success: int = 0
    failed: int = 0
    # Logged as a failure but expected — e.g. an idempotency race. Broken out so a
    # benign outcome stops reading as an incident.
    benign: int = 0
    # Still in progress (pending/processing/queued). Previously counted in `total`
    # but rendered in no bucket, which is why a channel could show 0/0 of 13.
    in_flight: int = 0
    total: int = 0
    # The distinct faults behind `failed`, worst first. A count alone says
    # something broke; this says what, without leaving the dashboard.
    top_failures: list[FailureSignatureOut] = []


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
def _email_outbox_health(db: Session, cutoff: datetime, window_end: datetime) -> Optional[EmailOutboxHealth]:
    try:
        from app.models.email_outbox import EmailOutbox

        counts = dict(
            db.query(EmailOutbox.status, func.count(EmailOutbox.id))
            .group_by(EmailOutbox.status)
            .all()
        )
        failed_24h = (
            db.query(func.count(EmailOutbox.id))
            .filter(
                EmailOutbox.status == "failed",
                EmailOutbox.created_at >= cutoff,
                EmailOutbox.created_at <= window_end,
            )
            .scalar()
            or 0
        )
        return EmailOutboxHealth(
            pending=int(counts.get("pending", 0)),
            sent=int(counts.get("sent", 0)),
            failed=int(counts.get("failed", 0)),
            cancelled=int(counts.get("cancelled", 0)),
            failed_in_window=int(failed_24h),
            failed_last_24h=int(failed_24h),
        )
    except Exception:  # noqa: BLE001 — a missing/legacy table omits the block, never 500s
        return None


def _imports_health(db: Session, cutoff: datetime, window_end: datetime) -> Optional[ImportsHealth]:
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

        from app.services.scheduled_task_service import get_overdue_tasks

        total = db.query(func.count(ScheduledTask.id)).scalar() or 0
        # Shared with the watchdog alert (system_health_alert_service) so the card
        # and the email can never disagree. Derived from last_run_at + interval,
        # not from the display-only next_run_at this used to read.
        overdue = len(get_overdue_tasks(db, now))
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


def _integrations_health(db: Session, cutoff: datetime, window_end: datetime) -> Optional[IntegrationsHealth]:
    try:
        from app.models.integration import IntegrationLog
        from app.services.n8n_liveness_service import HEALTHCHECK_CHANNEL

        rows = (
            db.query(
                IntegrationLog.integration_channel,
                IntegrationLog.status,
                IntegrationLog.error_message,
                IntegrationLog.status_code,
                func.count(IntegrationLog.id),
            )
            .filter(
                IntegrationLog.created_at >= cutoff,
                IntegrationLog.created_at <= window_end,
                # Liveness probes are not a business integration channel — the
                # watchdog/digest surface their status separately.
                IntegrationLog.integration_channel != HEALTHCHECK_CHANNEL,
            )
            .group_by(
                IntegrationLog.integration_channel,
                IntegrationLog.status,
                IntegrationLog.error_message,
                IntegrationLog.status_code,
            )
            .all()
        )
        by_channel: dict[str, IntegrationChannelHealth] = {}
        # Only rows classified FAILED feed the signature list — a benign row
        # carries an error_message too, and surfacing it as a "fault to chase"
        # would undo the classification work upstream.
        failed_rows: dict[str, list[SimpleNamespace]] = {}
        for channel, status, error_message, status_code, n in rows:
            key = channel or "unknown"
            entry = by_channel.setdefault(key, IntegrationChannelHealth(channel=key))
            n = int(n)
            entry.total += n
            outcome = classify(
                SimpleNamespace(
                    integration_channel=key,
                    status=status,
                    error_message=error_message,
                )
            )
            if outcome == OUTCOME_SUCCESS:
                entry.success += n
            elif outcome == OUTCOME_FAILED:
                entry.failed += n
                failed_rows.setdefault(key, []).append(
                    SimpleNamespace(
                        status_code=status_code, error_message=error_message, count=n
                    )
                )
            elif outcome == OUTCOME_BENIGN:
                entry.benign += n
            else:
                entry.in_flight += n

        for key, entry in by_channel.items():
            entry.top_failures = [
                FailureSignatureOut(
                    signature=f.signature,
                    sample_message=f.sample_message,
                    status_code=f.status_code,
                    count=f.count,
                    filter_terms=f.filter_terms,
                )
                for f in top_failures(failed_rows.get(key, []))
            ]
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
    date_from: Optional[datetime] = Query(
        None, description="Window start. Filters on each record's created_at."
    ),
    date_to: Optional[datetime] = Query(None, description="Window end."),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Aggregate operational health across email outbox, imports, scheduled
    tasks, integrations, and audit activity. Read-only; safe to poll.

    Auth-only (no bespoke permission), matching the sibling admin-utility pages
    (Audit Logs, Import Logs, Integration Logs) under System Management."""
    now_aware = datetime.now(timezone.utc)
    now = now_aware.replace(tzinfo=None)  # naive UTC to match stored columns

    # Windowed metrics honour the caller's range and filter on `created_at`.
    # Point-in-time figures (queue backlogs, task counts) are always "as of now" —
    # a date range cannot meaningfully apply to a live backlog, and the response
    # labels them so the UI can say so rather than implying they were filtered.
    if date_from is not None or date_to is not None:
        cutoff = (date_from or (now - timedelta(days=365))).replace(tzinfo=None)
        window_end = (date_to or now).replace(tzinfo=None)
    else:
        cutoff = now - timedelta(hours=24)
        window_end = now

    return HealthSummaryResponse(
        generated_at=now_aware,
        email_outbox=_email_outbox_health(db, cutoff, window_end),
        imports=_imports_health(db, cutoff, window_end),
        scheduled_tasks=_scheduled_tasks_health(db, now),
        integrations=_integrations_health(db, cutoff, window_end),
        audit_activity=_audit_activity_health(db, cutoff, now),
    )
