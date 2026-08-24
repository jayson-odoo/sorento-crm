"""Single chokepoint for outbound email.

Every caller (auth flows, notification deliveries, attachment-linkage helpers, etc.) must use
`enqueue` (one-off) or `enqueue_or_merge` (coalesce window). `notification_email.send_*` is
private to the drainer worker.

Coalesce semantics: when a row with the same `coalesce_key` is already pending and its
`scheduled_for` is in the future, merge the new payload into that row (append attachment_ids,
rebuild body) instead of creating a second outbox row. Guarantees one outbox row = one outgoing
email - never coalesces after-the-fact at drain time, preserving traceability.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.email_outbox import EmailEventConfig, EmailOutbox
from app.services.email_event_registry import get_event_def

logger = logging.getLogger(__name__)


class UnknownEmailEvent(Exception):
    """Raised when a caller uses an event_key that is not in EMAIL_EVENT_REGISTRY."""


def _resolve_event_config(db: Session, event_key: str) -> tuple[EmailEventConfig, Any]:
    """Returns (DB config row, registry EventDef). Raises UnknownEmailEvent if not seeded."""
    evt_def = get_event_def(event_key)
    if evt_def is None:
        raise UnknownEmailEvent(
            f"Event '{event_key}' is not in EMAIL_EVENT_REGISTRY. Add it to "
            "app/services/email_event_registry.py before enqueueing."
        )
    cfg = (
        db.query(EmailEventConfig)
        .filter(EmailEventConfig.event_key == event_key)
        .first()
    )
    if cfg is None:
        cfg = EmailEventConfig(
            event_key=event_key,
            display_name=evt_def.display_name,
            description=evt_def.description,
            enabled=True,
        )
        db.add(cfg)
        db.flush()
    return cfg, evt_def


def _effective_priority(cfg: EmailEventConfig, evt_def: Any, override: Optional[int]) -> int:
    if override is not None:
        return override
    if cfg.priority_override is not None:
        return int(cfg.priority_override)
    return int(evt_def.priority)


def _effective_coalesce_seconds(cfg: EmailEventConfig, evt_def: Any) -> Optional[int]:
    if cfg.coalesce_window_seconds_override is not None:
        return int(cfg.coalesce_window_seconds_override)
    return evt_def.coalesce_window_seconds


def enqueue(
    db: Session,
    *,
    event_key: str,
    to: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    from_name: Optional[str] = None,
    priority: Optional[int] = None,
    metadata: Optional[dict] = None,
    scheduled_for: Optional[datetime] = None,
    max_attempts: int = 5,
    coalesce_key: Optional[str] = None,
    attachment_filename: Optional[str] = None,
    attachment_storage_provider: Optional[str] = None,
    attachment_storage_key: Optional[str] = None,
) -> str:
    """Write a row to email_outbox. Returns row id. Drainer dispatches asynchronously.

    Disabled events still create a row (so operators can see what would have been sent and
    what got cancelled at drain time) - the drainer marks it `cancelled` with reason
    `event_disabled` rather than skipping silently.
    """
    cfg, evt_def = _resolve_event_config(db, event_key)
    eff_priority = _effective_priority(cfg, evt_def, priority)

    recipients_json = None
    if cc or bcc:
        recipients_json = {"to": [to], "cc": cc or [], "bcc": bcc or []}

    row = EmailOutbox(
        event_key=event_key,
        recipient_email=to,
        recipients_json=recipients_json,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        from_name=from_name,
        metadata_json=metadata or {},
        priority=eff_priority,
        status="pending",
        scheduled_for=scheduled_for or datetime.utcnow(),
        attempt_count=0,
        max_attempts=max_attempts,
        coalesce_key=coalesce_key,
        attachment_filename=attachment_filename,
        attachment_storage_provider=attachment_storage_provider,
        attachment_storage_key=attachment_storage_key,
    )
    db.add(row)
    db.flush()
    return str(row.id)


def enqueue_or_merge(
    db: Session,
    *,
    event_key: str,
    to: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    from_name: Optional[str] = None,
    metadata: Optional[dict] = None,
    coalesce_id: Optional[str] = None,
    merge_metadata_list_keys: Optional[list[str]] = None,
    rebuild_body: Optional[callable] = None,  # type: ignore[valid-type]
    priority: Optional[int] = None,
    max_attempts: int = 5,
) -> tuple[str, bool]:
    """Coalesce-aware enqueue. Returns (outbox_id, merged_into_existing).

    Uses the event's `coalesce_window_seconds` to defer the first row; subsequent calls within
    the window merge into that row instead of creating new rows.

    `coalesce_id` is the optional batch identifier (e.g. an upload batch UUID from the FE).
    When None, falls back to `(event_key, recipient_email)` keyed on a fresh window.

    `merge_metadata_list_keys` (e.g. `["attachment_ids"]`) names list keys whose values are
    de-duplicated and concatenated on merge.

    `rebuild_body` is an optional callable `(merged_metadata) -> (body_text, body_html)`
    invoked after metadata is merged so the visible email reflects the full coalesced set.
    """
    cfg, evt_def = _resolve_event_config(db, event_key)
    coalesce_seconds = _effective_coalesce_seconds(cfg, evt_def)

    if not coalesce_seconds:
        new_id = enqueue(
            db,
            event_key=event_key,
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            from_name=from_name,
            metadata=metadata,
            priority=priority,
            max_attempts=max_attempts,
        )
        return new_id, False

    coalesce_key = f"{event_key}:{to}:{coalesce_id}" if coalesce_id else f"{event_key}:{to}"
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=coalesce_seconds)

    existing = (
        db.query(EmailOutbox)
        .filter(
            EmailOutbox.coalesce_key == coalesce_key,
            EmailOutbox.status == "pending",
            EmailOutbox.created_at >= cutoff,
        )
        .order_by(EmailOutbox.created_at.desc())
        .first()
    )

    if existing is not None:
        merged_meta: dict = dict(existing.metadata_json or {})
        incoming_meta: dict = dict(metadata or {})
        for k, v in incoming_meta.items():
            if merge_metadata_list_keys and k in merge_metadata_list_keys and isinstance(v, list):
                base_list = list(merged_meta.get(k) or [])
                seen = set(str(x) for x in base_list)
                for item in v:
                    s = str(item)
                    if s not in seen:
                        base_list.append(item)
                        seen.add(s)
                merged_meta[k] = base_list
            else:
                merged_meta[k] = v
        existing.metadata_json = merged_meta
        if rebuild_body is not None:
            new_text, new_html = rebuild_body(merged_meta)
            existing.body_text = new_text
            existing.body_html = new_html
        if existing.scheduled_for < now + timedelta(seconds=coalesce_seconds):
            existing.scheduled_for = now + timedelta(seconds=coalesce_seconds)
        db.flush()
        return str(existing.id), True

    eff_priority = _effective_priority(cfg, evt_def, priority)
    row = EmailOutbox(
        event_key=event_key,
        recipient_email=to,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        from_name=from_name,
        metadata_json=metadata or {},
        priority=eff_priority,
        status="pending",
        scheduled_for=now + timedelta(seconds=coalesce_seconds),
        attempt_count=0,
        max_attempts=max_attempts,
        coalesce_key=coalesce_key,
    )
    db.add(row)
    db.flush()
    return str(row.id), False


def cancel(db: Session, outbox_id: str, reason: str) -> bool:
    row = db.query(EmailOutbox).filter(EmailOutbox.id == outbox_id).first()
    if row is None or row.status in ("sent", "cancelled"):
        return False
    row.status = "cancelled"
    row.cancel_reason = reason
    db.commit()
    return True


def retry(db: Session, outbox_id: str) -> bool:
    row = db.query(EmailOutbox).filter(EmailOutbox.id == outbox_id).first()
    if row is None or row.status not in ("failed", "cancelled"):
        return False
    row.status = "pending"
    row.cancel_reason = None
    row.error_message = None
    row.scheduled_for = datetime.utcnow()
    db.commit()
    return True
