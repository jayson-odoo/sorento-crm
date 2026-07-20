"""Resolve the authoritative Respond-side timestamp for chat messages.

`chat_histories.sent_at` is whatever n8n supplied — historically `new Date().getTime()`,
i.e. n8n's clock at save time. Latency measured from that is meaningless (on production
rows an outgoing `sent_at` can precede the incoming it answers). This service fills
`respond_ts` from Respond itself, so both ends of the SLA share one clock.

Targeted lookup rather than polling: `GET /v2/contact/{id}/message/{messageId}` for rows
that carry a `message_id`. A 404 is meaningful in its own right — a message we believed
we sent does not exist on Respond's side — but only after enough attempts that a
transient failure has been ruled out. A 500 must never be read as "never sent".

Runs from the `chat_message_resolver` scheduled task, so its throughput and failures show
up in the run-log UI alongside every other background job.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.chat_history import ChatHistory

logger = logging.getLogger(__name__)

# After this many misses a message is concluded never to have been sent.
MAX_RESOLVE_ATTEMPTS = 5

# Respond's delivery lifecycle. Anything else is stored verbatim for triage.
_KNOWN_STATUSES = ("sent", "delivered", "read", "failed")


class MessageNotFound(Exception):
    """Respond has no such message — distinct from a transient API failure."""


def _epoch_to_naive_utc(value: Any) -> Optional[datetime]:
    """Epoch seconds *or* milliseconds -> naive UTC.

    Respond returns both depending on the endpoint; multiplying an ms value by 1000
    yields year-58xxx dates, which is how this bites.
    """
    if value is None:
        return None
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return None
    if raw <= 0:
        return None
    seconds = raw / 1000 if raw > 1e12 else raw
    try:
        return datetime.utcfromtimestamp(seconds)
    except (OverflowError, OSError, ValueError):
        return None


def _pending_rows(db: Session, limit: int) -> list[ChatHistory]:
    return (
        db.query(ChatHistory)
        .filter(
            ChatHistory.message_id.isnot(None),
            ChatHistory.respond_ts.is_(None),
            # sqlite/Postgres both need the NULL arm spelled out: a row that has never
            # been attempted has NULL, not 0, unless the server_default applied.
            (ChatHistory.resolve_attempts.is_(None))
            | (ChatHistory.resolve_attempts < MAX_RESOLVE_ATTEMPTS),
        )
        .order_by(ChatHistory.id.asc())
        .limit(limit)
        .all()
    )


def _apply_payload(row: ChatHistory, payload: dict) -> bool:
    """Write what Respond told us. Returns True if a timestamp was resolved."""
    ts = _epoch_to_naive_utc(payload.get("timestamp"))
    if ts is None:
        # No clock in the response — leave unresolved rather than substituting now(),
        # which would fabricate a latency figure.
        return False

    row.respond_ts = ts

    status = payload.get("status")
    if isinstance(status, str) and status:
        row.delivery_status = status if status in _KNOWN_STATUSES else status[:32]
    elif row.delivery_status is None:
        row.delivery_status = "sent"

    stamps = payload.get("statusTimestamps")
    if isinstance(stamps, dict):
        row.delivered_ts = _epoch_to_naive_utc(stamps.get("delivered")) or row.delivered_ts
        row.read_ts = _epoch_to_naive_utc(stamps.get("read")) or row.read_ts

    return True


def resolve_pending(
    db: Session,
    client: Any = None,
    limit: int = 200,
    now: Optional[datetime] = None,
) -> dict:
    """Resolve a batch of unresolved rows. Never raises on a single bad row."""
    if client is None:
        from app.services.integration_service import RespondClient

        client = RespondClient()

    rows = _pending_rows(db, limit)
    resolved = failed = not_sent = 0

    for row in rows:
        attempts = int(row.resolve_attempts or 0)
        try:
            try:
                payload = client.get_message(row.contact_id, row.message_id) or {}
            except Exception as exc:  # noqa: BLE001
                # RespondClient surfaces HTTP errors via raise_for_status. A 404 is the
                # "no such message" signal; every other status is transient and must not
                # be allowed to conclude that a message was never sent.
                resp = getattr(exc, "response", None)
                if resp is not None and getattr(resp, "status_code", None) == 404:
                    raise MessageNotFound(str(exc)) from exc
                raise
        except MessageNotFound:
            row.resolve_attempts = attempts + 1
            if row.resolve_attempts >= MAX_RESOLVE_ATTEMPTS:
                # Exhausted: Respond consistently has no record of it.
                row.delivery_status = "not_sent"
                not_sent += 1
            continue
        except Exception as exc:  # noqa: BLE001 - one bad row must not kill the batch
            row.resolve_attempts = attempts + 1
            failed += 1
            logger.warning(
                "chat_message_resolver: %s for chat_histories.id=%s message_id=%s",
                exc, row.id, row.message_id,
            )
            continue

        if _apply_payload(row, payload):
            resolved += 1
        else:
            row.resolve_attempts = attempts + 1

    db.commit()
    return {
        "scanned": len(rows),
        "resolved": resolved,
        "failed": failed,
        "not_sent": not_sent,
    }
