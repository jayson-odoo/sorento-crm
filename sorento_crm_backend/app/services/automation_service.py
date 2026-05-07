"""Automation CRUD + run executor."""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.automation import Automation, AutomationRun
from app.models.email_template import EmailTemplate
from app.models.notification import Notification, NotificationDelivery
from app.models.user import User
from app.services import automation_recipients, automation_triggers
from app.services.email_template_service import EmailTemplateService
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)


def _resolve_owner_user_id(db: Session, automation: Automation) -> Optional[str]:
    """Pick a user_id for the underlying Notification rows.

    Prefer the automation's creator; fall back to any active protected user; then
    any active user. Returns None only if the system has no users at all.
    """
    if automation.created_by_user_id:
        u = db.query(User).filter(User.id == automation.created_by_user_id).first()
        if u is not None and not bool(getattr(u, "is_trashed", False)):
            return str(getattr(u, "id"))
    u = (
        db.query(User)
        .filter(User.is_trashed.is_(False), User.is_protected.is_(True))
        .order_by(User.created_at.asc())
        .first()
    )
    if u is None:
        u = (
            db.query(User)
            .filter(User.is_trashed.is_(False))
            .order_by(User.created_at.asc())
            .first()
        )
    return str(getattr(u, "id")) if u is not None else None


def _next_run_for_daily(run_time: Optional[time], timezone_name: str, *, after: Optional[datetime] = None) -> Optional[datetime]:
    """Compute the next UTC datetime when ``run_time`` will occur in ``timezone_name``.

    ``after`` defaults to now (UTC). Result is naive UTC for storage in
    ``automations.next_run_at`` (which uses ``DateTime(timezone=False)``).
    """
    if not run_time:
        return None
    try:
        tz = ZoneInfo(timezone_name or "Asia/Kuala_Lumpur")
    except Exception:
        tz = ZoneInfo("Asia/Kuala_Lumpur")
    after_utc = after or datetime.utcnow()
    after_aware = after_utc.replace(tzinfo=ZoneInfo("UTC"))
    after_local = after_aware.astimezone(tz)
    candidate_local = datetime.combine(after_local.date(), run_time, tzinfo=tz)
    if candidate_local <= after_local:
        candidate_local = candidate_local + timedelta(days=1)
    return candidate_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _compute_next_run(automation: Automation) -> Optional[datetime]:
    if not automation.enabled:
        return None
    if str(automation.schedule_type) != "daily":
        return None
    return _next_run_for_daily(
        automation.run_time,  # type: ignore[arg-type]
        str(automation.timezone or "Asia/Kuala_Lumpur"),
    )


class AutomationService:
    def __init__(self, db: Session):
        self.db = db

    # ---------- CRUD ----------
    def list(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> tuple[list[Automation], int]:
        q = self.db.query(Automation)
        if query and query.strip():
            term = f"%{query.strip()}%"
            q = q.filter(Automation.name.ilike(term))
        if enabled is not None:
            q = q.filter(Automation.enabled.is_(enabled))
        total = q.count()
        rows = (
            q.order_by(Automation.updated_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return rows, total

    def get(self, automation_id: str) -> Optional[Automation]:
        return self.db.query(Automation).filter(Automation.id == automation_id).first()

    def create(self, payload: dict[str, Any], user_id: Optional[str]) -> Automation:
        self._validate(payload)
        row = Automation(
            name=payload["name"],
            description=payload.get("description"),
            enabled=payload.get("enabled", True),
            trigger_type=payload["trigger_type"],
            trigger_config=payload.get("trigger_config") or {},
            action_type=payload.get("action_type") or "send_email",
            email_template_id=payload["email_template_id"],
            recipient_config=self._normalize_recipient_config(payload.get("recipient_config")),
            schedule_type=payload.get("schedule_type") or "manual",
            run_time=payload.get("run_time"),
            timezone=payload.get("timezone") or "Asia/Kuala_Lumpur",
            created_by_user_id=user_id,
        )
        row.next_run_at = _compute_next_run(row)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update(self, automation_id: str, payload: dict[str, Any]) -> Automation:
        row = self.get(automation_id)
        if not row:
            raise AppException(status_code=404, message="Automation not found")
        if "recipient_config" in payload and payload["recipient_config"] is not None:
            payload["recipient_config"] = self._normalize_recipient_config(payload["recipient_config"])
        for field in (
            "name",
            "description",
            "enabled",
            "trigger_type",
            "trigger_config",
            "action_type",
            "email_template_id",
            "recipient_config",
            "schedule_type",
            "run_time",
            "timezone",
        ):
            if field in payload and payload[field] is not None:
                setattr(row, field, payload[field])
        merged = {
            "trigger_type": row.trigger_type,
            "trigger_config": row.trigger_config,
            "email_template_id": row.email_template_id,
            "schedule_type": row.schedule_type,
            "run_time": row.run_time,
        }
        self._validate(merged)
        row.next_run_at = _compute_next_run(row)
        row.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(row)
        return row

    def toggle(self, automation_id: str, enabled: bool) -> Automation:
        row = self.get(automation_id)
        if not row:
            raise AppException(status_code=404, message="Automation not found")
        row.enabled = enabled
        row.next_run_at = _compute_next_run(row)
        row.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, automation_id: str) -> None:
        row = self.get(automation_id)
        if not row:
            raise AppException(status_code=404, message="Automation not found")
        self.db.delete(row)
        self.db.commit()

    # ---------- Runs ----------
    def list_runs(
        self,
        automation_id: str,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[AutomationRun], int]:
        q = self.db.query(AutomationRun).filter(AutomationRun.automation_id == automation_id)
        total = q.count()
        rows = (
            q.order_by(AutomationRun.started_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return rows, total

    def run_now(self, automation_id: str, *, run_mode: str = "manual") -> dict[str, Any]:
        automation = self.get(automation_id)
        if not automation:
            raise AppException(status_code=404, message="Automation not found")
        return self._execute(automation, run_mode=run_mode)

    def dispatch_event(
        self,
        trigger_type: str,
        *,
        context: dict[str, Any],
        source_kind: str,
        source_id: str,
    ) -> dict[str, Any]:
        """Run every enabled automation for ``trigger_type`` against a single match.

        Used by domain code (e.g. complaint approval) to fire on-event automations
        immediately, bypassing the daily ``evaluate_due`` scheduler. Failures are
        per-automation; one bad rule does not block the rest.
        """
        automations = (
            self.db.query(Automation)
            .filter(
                Automation.enabled.is_(True),
                Automation.trigger_type == trigger_type,
            )
            .all()
        )
        match = automation_triggers.TriggerMatch(
            context=dict(context or {}),
            source_kind=source_kind,
            source_id=source_id,
        )
        results: list[dict[str, Any]] = []
        for automation in automations:
            try:
                results.append(
                    self._execute(
                        automation,
                        run_mode="event",
                        prebuilt_matches=[match],
                    )
                )
            except Exception:
                logger.exception(
                    "dispatch_event(%s) failed for automation %s",
                    trigger_type,
                    automation.id,
                )
        return {"trigger_type": trigger_type, "fired": len(results), "results": results}

    def evaluate_due(self) -> dict[str, Any]:
        """Master scheduler entrypoint: run every enabled automation whose next_run_at is due."""
        now = datetime.utcnow()
        due = (
            self.db.query(Automation)
            .filter(
                Automation.enabled.is_(True),
                Automation.next_run_at.isnot(None),
                Automation.next_run_at <= now,
            )
            .all()
        )
        ran = 0
        errors = 0
        for automation in due:
            try:
                self._execute(automation, run_mode="scheduled")
                ran += 1
            except Exception:
                logger.exception("Scheduled automation %s failed", automation.id)
                errors += 1
        return {"due": len(due), "ran": ran, "errors": errors}

    # ---------- Internal ----------
    def _validate(self, payload: dict[str, Any]) -> None:
        if payload.get("trigger_type") not in {s.type for s in automation_triggers.list_specs()}:
            raise AppException(
                status_code=400,
                message=f"Unknown trigger_type: {payload.get('trigger_type')}",
            )
        template = (
            self.db.query(EmailTemplate)
            .filter(EmailTemplate.id == payload["email_template_id"])
            .first()
        )
        if not template:
            raise AppException(status_code=400, message="email_template_id does not exist")
        schedule_type = payload.get("schedule_type") or "manual"
        if schedule_type not in {"manual", "daily"}:
            raise AppException(status_code=400, message="schedule_type must be 'manual' or 'daily'")
        if schedule_type == "daily" and not payload.get("run_time"):
            raise AppException(status_code=400, message="run_time required when schedule_type='daily'")

    @staticmethod
    def _normalize_recipient_config(config: Any) -> dict[str, Any]:
        if not config:
            return {
                "user_ids": [],
                "role_ids": [],
                "include_promotion_owner": False,
                "extra_emails": [],
            }
        if hasattr(config, "model_dump"):
            data = config.model_dump()
        elif isinstance(config, dict):
            data = config
        else:
            data = {}
        return {
            "user_ids": [str(x) for x in (data.get("user_ids") or [])],
            "role_ids": [str(x) for x in (data.get("role_ids") or [])],
            "include_promotion_owner": bool(data.get("include_promotion_owner", False)),
            "extra_emails": [str(x).strip() for x in (data.get("extra_emails") or []) if str(x).strip()],
        }

    def _execute(
        self,
        automation: Automation,
        *,
        run_mode: str,
        prebuilt_matches: Optional[list["automation_triggers.TriggerMatch"]] = None,
    ) -> dict[str, Any]:
        run = AutomationRun(
            automation_id=str(automation.id),
            run_mode=run_mode,
            status="running",
            recipients_attempted=0,
            recipients_delivered=0,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        started_at = run.started_at or datetime.utcnow()
        owner_user_id = _resolve_owner_user_id(self.db, automation)

        try:
            template = (
                self.db.query(EmailTemplate)
                .filter(EmailTemplate.id == automation.email_template_id)
                .first()
            )
            if not template:
                raise AppException(status_code=400, message="Template missing")

            if prebuilt_matches is not None:
                matches = list(prebuilt_matches)
            else:
                matches = automation_triggers.fire(
                    self.db,
                    str(automation.trigger_type),
                    dict(automation.trigger_config or {}),
                    str(automation.timezone or "Asia/Kuala_Lumpur"),
                )

            template_service = EmailTemplateService(self.db)
            attempted = 0
            per_promotion: list[dict[str, Any]] = []

            for match in matches:
                recipients = automation_recipients.resolve_recipients(
                    self.db,
                    dict(automation.recipient_config or {}),
                    promotion_context=match.context,
                )
                rendered_per_recipient: list[dict[str, Any]] = []
                for recipient in recipients:
                    ctx = dict(match.context)
                    ctx["recipient"] = {
                        "name": recipient.get("name") or recipient["email"],
                        "email": recipient["email"],
                    }
                    rendered = template_service.render(template, ctx)
                    self._enqueue_email(
                        owner_user_id=owner_user_id,
                        recipient=recipient,
                        subject=rendered["subject"],
                        body_html=rendered["body_html"],
                        body_text=rendered["body_text"],
                        metadata={
                            "automation_id": str(automation.id),
                            "automation_run_id": str(run.id),
                            "promotion_id": match.source_id,
                            "source_kind": match.source_kind,
                            "source_id": match.source_id,
                            "trigger_type": str(automation.trigger_type),
                        },
                    )
                    attempted += 1
                    rendered_per_recipient.append(
                        {"email": recipient["email"], "subject": rendered["subject"]}
                    )
                per_promotion.append(
                    {
                        "source_kind": match.source_kind,
                        "source_id": match.source_id,
                        "recipients": rendered_per_recipient,
                    }
                )

            self._maybe_enqueue_worker()

            run.recipients_attempted = attempted
            run.recipients_delivered = 0  # updated by delivery worker downstream
            run.status = "success"
            run.finished_at = datetime.utcnow()
            run.duration_ms = int((run.finished_at - started_at).total_seconds() * 1000)
            run.summary = {
                "matches": len(per_promotion),
                "recipients_attempted": attempted,
                "matches_detail": per_promotion[:50],  # keep summary bounded
            }

            automation.last_run_at = datetime.utcnow()
            automation.last_status = "success"
            automation.last_error = None
            automation.next_run_at = _compute_next_run(automation)
            self.db.commit()
            self.db.refresh(run)
            return {
                "run_id": str(run.id),
                "status": "success",
                "recipients_attempted": attempted,
                "summary": run.summary,
            }
        except Exception as exc:
            self.db.rollback()
            run = (
                self.db.query(AutomationRun)
                .filter(AutomationRun.id == run.id)
                .first()
            )
            if run is not None:
                run.status = "failed"
                run.finished_at = datetime.utcnow()
                run.duration_ms = int((run.finished_at - started_at).total_seconds() * 1000)
                run.error = str(exc)
            automation_row = self.get(str(automation.id))
            if automation_row is not None:
                automation_row.last_run_at = datetime.utcnow()
                automation_row.last_status = "failed"
                automation_row.last_error = str(exc)
                automation_row.next_run_at = _compute_next_run(automation_row)
            self.db.commit()
            logger.exception("Automation %s execution failed", automation.id)
            raise

    def _enqueue_email(
        self,
        *,
        owner_user_id: Optional[str],
        recipient: dict[str, Any],
        subject: str,
        body_html: str,
        body_text: str,
        metadata: dict[str, Any],
    ) -> str:
        """Insert one Notification + email NotificationDelivery row.

        Reuses the existing ``notification_deliveries`` infra so the queued send
        appears in System Management → Outgoing Mails. The actual SMTP send is
        handled later by ``send_notification_deliveries`` against pending rows.
        """
        if owner_user_id is None:
            raise AppException(
                status_code=400,
                message="No system user available to author outgoing emails",
            )
        notif = Notification(
            user_id=owner_user_id,
            type="automation_email",
            title=subject,
            body=body_text,
            data={
                "single_email_to_all": True,
                "recipient_emails": [recipient["email"]],
                "recipient_name": recipient.get("name"),
                "body_html": body_html,
                "body_text": body_text,
                **metadata,
            },
            source_entity_type="automation_run",
            source_entity_id=metadata.get("automation_run_id"),
            event_type=(
                f"recipient:{recipient['email'].lower()}"
                f":source:{metadata.get('source_kind', 'match')}"
                f":id:{metadata.get('source_id', '')}"
            ),
        )
        self.db.add(notif)
        self.db.flush()
        delivery = NotificationDelivery(
            notification_id=str(notif.id),
            channel="email",
            status="pending",
        )
        self.db.add(delivery)
        self.db.commit()
        try:
            from app.services.queue_service import enqueue_job
            from app.tasks import notification_tasks

            enqueue_job(
                notification_tasks.send_notification_deliveries,
                str(notif.id),
                queue_name="notifications",
            )
        except Exception:
            logger.debug("Notifications queue unavailable; delivery row %s stays pending", delivery.id)
        return str(delivery.id)

    @staticmethod
    def _maybe_enqueue_worker() -> None:
        """Reserved hook (per-recipient enqueue happens in _enqueue_email)."""
        return None
