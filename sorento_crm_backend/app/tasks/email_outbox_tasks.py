"""Email outbox drainer.

Single producer of SMTP traffic. Runs on an interval (default 5s) on the worker container.
Picks pending rows, enforces guardrails, sends, marks sent/failed/deferred.

Failure backoff: 1m, 5m, 30m, 2h, 12h capped at `max_attempts`. Rows breaching that flip to
terminal `failed` with `cancel_reason='max_attempts_exceeded'`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.email_outbox import EmailEventConfig, EmailOutbox
from app.models.notification import NotificationDelivery
from app.models.user import SystemSetting
from app.services.email_rate_limiter import check as rate_check, record_send
from app.services.notification_email import (
    _smtp_config_from_settings,
    send_mime_email,
)

logger = logging.getLogger(__name__)


_BACKOFF_SECONDS = [60, 300, 1800, 7200, 43200]


def _next_backoff(attempt_count: int) -> int:
    if attempt_count <= 0:
        return _BACKOFF_SECONDS[0]
    idx = min(attempt_count - 1, len(_BACKOFF_SECONDS) - 1)
    return _BACKOFF_SECONDS[idx]


def _writeback_notification_delivery(db: Session, row: EmailOutbox, status: str, error: Optional[str]) -> None:
    """Mirror the outbox row's outcome onto the original NotificationDelivery, if any.

    Keeps the existing Outgoing Mails admin page accurate while the source of truth shifts
    to email_outbox.
    """
    meta = row.metadata_json or {}
    delivery_id = meta.get("notification_delivery_id") if isinstance(meta, dict) else None
    if not delivery_id:
        return
    delivery = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.id == delivery_id)
        .first()
    )
    if delivery is None:
        return
    delivery.status = status
    delivery.error_message = error
    if status == "sent":
        delivery.sent_at = datetime.utcnow()


#: What each attachment extension is sent as. Anything unlisted goes as a generic binary,
#: which every mail client offers to save.
_ATTACHMENT_MIME = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _fetch_attachment(provider: Optional[str], key: str, filename: Optional[str]) -> tuple:
    from app.services.storage_router import get_backend

    name = filename or key.rsplit("/", 1)[-1]
    data = get_backend(provider).download_file(key)
    ext = name[name.rfind(".") :].lower() if "." in name else ""
    return name, _ATTACHMENT_MIME.get(ext, "application/octet-stream"), data


def _attachments_for(row: EmailOutbox) -> Optional[list]:
    """Fetch the row's attachments, if it declared any.

    A failure to read an object is raised, not swallowed: an email that was supposed to carry
    a document and silently arrives without one is worse than one that retries. The outbox's
    existing backoff then applies, which is the behaviour every other send failure already gets.

    ONE file lives in the row's own columns, and that is every event but one. A container
    request sends two - the PDF and the supplier's own stock list with the quantity to load
    filled in (`supplier_notice_service`, F4) - and the second travels as
    `metadata_json["extra_attachments"]` rather than as a second set of columns nothing else
    in the system would ever fill.
    """
    out: list[tuple] = []

    key = getattr(row, "attachment_storage_key", None)
    if key:
        out.append(
            _fetch_attachment(
                getattr(row, "attachment_storage_provider", None),
                key,
                getattr(row, "attachment_filename", None),
            )
        )

    meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    for extra in meta.get("extra_attachments") or []:
        if not isinstance(extra, dict) or not extra.get("storage_key"):
            continue
        out.append(
            _fetch_attachment(
                extra.get("storage_provider"), extra["storage_key"], extra.get("filename")
            )
        )

    return out or None


def _attempt_send(row: EmailOutbox, smtp_config: Optional[dict]) -> Optional[str]:
    """Send one outbox row via SMTP. Returns None on success, error string on failure."""
    recipients_json = row.recipients_json or {}
    to_list = [row.recipient_email]
    cc_list = recipients_json.get("cc") if isinstance(recipients_json, dict) else None
    bcc_list = recipients_json.get("bcc") if isinstance(recipients_json, dict) else None
    try:
        attachments = _attachments_for(row)
    except Exception as exc:  # noqa: BLE001 - reported as a send failure, so backoff applies
        return f"attachment unavailable: {exc}"
    return send_mime_email(
        to_list=to_list,
        cc_list=cc_list,
        bcc_list=bcc_list,
        subject=row.subject,
        body_text=row.body_text or "",
        body_html=row.body_html,
        smtp_config=smtp_config,
        from_name=row.from_name,
        attachments=attachments,
    )


def drain_email_outbox() -> dict:
    """Drain a single batch of pending outbox rows. Returns a summary dict for logging."""
    db: Session = SessionLocal()
    summary = {"picked": 0, "sent": 0, "deferred_rate": 0, "deferred_disabled": 0, "failed": 0, "terminal_failed": 0, "cancelled": 0}
    try:
        settings_row = db.query(SystemSetting).first()
        smtp_config = _smtp_config_from_settings(settings_row) if settings_row else None
        batch_size = int(getattr(settings_row, "email_outbox_drain_batch_size", 20) or 20)
        global_rate = int(getattr(settings_row, "email_global_rate_per_window", 60) or 60)
        global_window = int(getattr(settings_row, "email_global_window_seconds", 60) or 60)
        per_recipient_rate = int(getattr(settings_row, "email_per_recipient_rate_per_window", 10) or 10)
        per_recipient_window = int(getattr(settings_row, "email_per_recipient_window_seconds", 3600) or 3600)

        now = datetime.utcnow()
        rows = (
            db.query(EmailOutbox)
            .filter(
                EmailOutbox.status == "pending",
                EmailOutbox.scheduled_for <= now,
            )
            .order_by(EmailOutbox.priority.asc(), EmailOutbox.created_at.asc())
            .limit(batch_size)
            .all()
        )
        if not rows:
            return summary

        cfg_index: dict[str, EmailEventConfig] = {
            c.event_key: c
            for c in db.query(EmailEventConfig)
            .filter(EmailEventConfig.event_key.in_({r.event_key for r in rows}))
            .all()
        }

        for row in rows:
            summary["picked"] += 1
            cfg = cfg_index.get(row.event_key)

            if cfg is not None and not cfg.enabled:
                row.status = "cancelled"
                row.cancel_reason = "event_disabled"
                _writeback_notification_delivery(db, row, "failed", "event_disabled")
                summary["cancelled"] += 1
                db.commit()
                continue

            event_rate_override = int(cfg.rate_per_window_override) if cfg and cfg.rate_per_window_override else None
            event_window_override = int(cfg.window_seconds_override) if cfg and cfg.window_seconds_override else None

            decision = rate_check(
                db,
                event_key=row.event_key,
                recipient_email=row.recipient_email,
                global_rate=global_rate,
                global_window_seconds=global_window,
                per_recipient_rate=per_recipient_rate,
                per_recipient_window_seconds=per_recipient_window,
                event_rate_override=event_rate_override,
                event_window_seconds_override=event_window_override,
            )
            if not decision.allowed:
                row.scheduled_for = now + timedelta(seconds=max(decision.retry_after_seconds or 30, 5))
                row.error_message = decision.reason
                summary["deferred_rate"] += 1
                db.commit()
                continue

            row.status = "sending"
            row.attempt_count = (row.attempt_count or 0) + 1
            db.commit()

            error = _attempt_send(row, smtp_config)
            if error is None:
                row.status = "sent"
                row.sent_at = datetime.utcnow()
                row.error_message = None
                _writeback_notification_delivery(db, row, "sent", None)
                record_send(
                    event_key=row.event_key,
                    recipient_email=row.recipient_email,
                    global_window_seconds=global_window,
                    per_recipient_window_seconds=per_recipient_window,
                    event_window_seconds_override=event_window_override,
                )
                summary["sent"] += 1
            else:
                row.error_message = error
                if row.attempt_count >= row.max_attempts:
                    row.status = "failed"
                    row.cancel_reason = "max_attempts_exceeded"
                    _writeback_notification_delivery(db, row, "failed", error)
                    summary["terminal_failed"] += 1
                else:
                    row.status = "pending"
                    row.scheduled_for = datetime.utcnow() + timedelta(seconds=_next_backoff(row.attempt_count))
                    summary["failed"] += 1
            db.commit()

        return summary
    except Exception as e:
        logger.exception("Email outbox drainer crashed: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
        return summary
    finally:
        db.close()
