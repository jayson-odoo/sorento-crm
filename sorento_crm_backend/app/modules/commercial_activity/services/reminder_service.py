"""Scheduled job: in-app reminders for commercial quotation activity tasks."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import and_, exists
from sqlalchemy.orm import Session

from app.modules.commercial_activity.models import CommercialActivityTaskStatus, CommercialQuotationActivityTask
from app.models.scheduled_task import ScheduledTask
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


def run_commercial_activity_reminders(db: Session, task: ScheduledTask) -> Dict[str, Any]:
    """Fire one-shot in-app reminders; clears remind_at after send."""
    T = CommercialQuotationActivityTask
    now = datetime.utcnow()
    non_terminal = exists().where(
        and_(
            CommercialActivityTaskStatus.id == T.status_id,
            CommercialActivityTaskStatus.is_terminal.is_(False),
        )
    )
    rows = (
        db.query(T)
        .filter(
            T.deleted_at.is_(None),
            T.remind_at.isnot(None),
            T.remind_at <= now,
            T.assignee_user_id.isnot(None),
            non_terminal,
        )
        .all()
    )
    ns = NotificationService(db)
    sent = 0
    for row in rows:
        try:
            uid = str(row.assignee_user_id)
            ns.create_in_app_only(
                user_id=uid,
                type="commercial_activity",
                title=f"Reminder: {row.title}",
                body=None,
            )
            row.last_reminder_sent_at = now
            row.remind_at = None
            sent += 1
        except Exception as e:
            logger.warning("Activity reminder failed for task %s: %s", row.id, e)
    if sent:
        db.commit()
    return {"reminders_sent": sent}
