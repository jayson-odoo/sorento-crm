"""Resolve the authoritative Respond-side timestamp for chat messages.

`chat_histories.sent_at` is whatever n8n supplied - historically `new Date().getTime()`,
i.e. n8n's clock at save time. Latency measured from that is meaningless (on production
rows an outgoing `sent_at` can precede the incoming it answers). This service fills
`respond_ts` from Respond itself, so both ends of the SLA share one clock.

Targeted lookup rather than polling: `GET /v2/contact/{id}/message/{messageId}` for rows
that carry a `message_id`, on a backoff schedule from the send. Respond 404s a message
until it dispatches it, so a 404 only becomes `not_sent` an hour after the send, and
even then a later 200 upgrades it. A 500 must never be read as "never sent".
Respond's own status timeline and the reason for a failure are stored on the row.

Runs from the `chat_message_resolver` scheduled task, so its throughput and failures show
up in the run-log UI alongside every other background job.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.chat_history import ChatHistory

logger = logging.getLogger(__name__)

# Minutes after the send at which each attempt is due. Respond answers 404 for a
# message it has accepted but not yet dispatched - on 29 Oct 2026 its outbound queue
# held four bot replies for ~25 min - so a 404 inside the first hour means "not
# visible yet", never "not sent".
RESOLVE_SCHEDULE_MINUTES = [1, 2, 5, 15, 30, 60, 240, 720, 1440]
MAX_RESOLVE_ATTEMPTS = len(RESOLVE_SCHEDULE_MINUTES)
# A 404 this long after the send writes `not_sent`, still upgradable by a later 200
# until the schedule runs out.
NOT_SENT_AFTER_MINUTES = 60
# Rows older than this are never picked up: past the schedule, and keeps a deploy of
# this code from silently backfilling every historic NULL row.
RESOLVE_LOOKBACK = timedelta(hours=48)

# Respond's delivery lifecycle, furthest step wins. `failed` outranks all of them.
_STATUS_RANK = {"pending": 0, "sent": 1, "delivered": 2, "read": 3}
_TERMINAL_STATUSES = ("read", "failed")


# How far a derived `respond_ts` may sit from the ingest-supplied `sent_at` before
# we conclude the id is not a timestamp at all. Generous: `sent_at` is n8n's own
# clock and is known to drift by seconds, but a misparse (ms read as us -> 1970,
# us read as ms -> year 58xxx) misses by decades, never by hours.
_MESSAGE_ID_CLOCK_TOLERANCE = timedelta(days=1)


class MessageNotFound(Exception):
    """Respond has no such message - distinct from a transient API failure."""


def respond_ts_from_message_id(
    message_id: Any, *, sent_at: Optional[datetime]
) -> Optional[datetime]:
    """Respond's authoritative clock, read straight out of its own message id.

    Respond mints `messageId` as the message's epoch-MICROSECOND timestamp, so the
    SLA clock arrives with the ingest payload and needs no `GET /message/{id}` call.
    Inbound WhatsApp ids land on exact seconds (trailing zeros) - that granularity
    is Respond's, not a rounding artefact of ours.

    Deliberately NOT `_epoch_to_naive_utc`: that helper reads anything above 1e12 as
    milliseconds, which turns a microsecond id into the year 58,000 - the exact trap
    its own docstring warns about.

    Returns None rather than a guess whenever the id is not a plausible timestamp;
    a NULL `respond_ts` is honest and the row simply sits out of the SLA.
    """
    if message_id is None:
        return None
    try:
        raw = int(str(message_id).strip())
    except (TypeError, ValueError):
        return None
    if raw <= 0:
        return None

    try:
        derived = datetime.utcfromtimestamp(raw / 1_000_000)
    except (OverflowError, OSError, ValueError):
        return None

    # Cross-check against the only other clock we hold. Without this, any short
    # numeric id (a test fixture, a sequence counter) would resolve to 1970 and
    # quietly poison the latency distribution with a 56-year round trip.
    if sent_at is None:
        return None
    if abs(derived - sent_at) > _MESSAGE_ID_CLOCK_TOLERANCE:
        return None
    return derived


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


def _anchor():
    """The send time a row's backoff is measured from: Respond's clock when held."""
    return func.coalesce(ChatHistory.respond_ts, ChatHistory.sent_at)


def _pending_rows(db: Session, limit: int, now: datetime) -> list[ChatHistory]:
    """Rows Respond still owes us something for AND whose next attempt is due.

    Outgoing rows are polled until a terminal status (`read` / `failed`) or until the
    schedule runs out - `not_sent` is NOT terminal, because Respond 404s a message until
    it dispatches it. Incoming rows carry `status: []`, so they only ever need the clock.
    The due check is in SQL so rows still backing off cannot fill the batch.
    """
    anchor = _anchor()
    attempts = func.coalesce(ChatHistory.resolve_attempts, 0)
    due = case(
        *[
            (attempts == i, anchor <= now - timedelta(minutes=minutes))
            for i, minutes in enumerate(RESOLVE_SCHEDULE_MINUTES)
        ],
        else_=False,
    )
    return (
        db.query(ChatHistory)
        .filter(
            ChatHistory.message_id.isnot(None),
            (
                (ChatHistory.type == "outgoing")
                & (
                    ChatHistory.delivery_status.is_(None)
                    | ChatHistory.delivery_status.notin_(_TERMINAL_STATUSES)
                )
            )
            | ChatHistory.respond_ts.is_(None),
            attempts < MAX_RESOLVE_ATTEMPTS,
            # Bounds the scan and keeps this from quietly backfilling history.
            anchor >= now - RESOLVE_LOOKBACK,
            due,
        )
        .order_by(ChatHistory.id.asc())
        .limit(limit)
        .all()
    )


def _status_entries(payload: dict) -> list[dict]:
    statuses = payload.get("status")
    if not isinstance(statuses, list):
        return []
    return [s for s in statuses if isinstance(s, dict)]


def _apply_payload(row: ChatHistory, payload: dict) -> bool:
    """Write what Respond told us. Returns True if anything was resolved.

    Respond v2 answers `status: [{value, timestamp(ms), message?}, ...]`, one entry per
    lifecycle step (pending -> sent -> delivered -> read, or failed). The furthest step
    wins; `failed` wins outright.
    """
    entries = _status_entries(payload)
    values = [e.get("value") for e in entries if isinstance(e.get("value"), str)]

    if row.respond_ts is None:
        stamps = [_epoch_to_naive_utc(e.get("timestamp")) for e in entries]
        stamps = [s for s in stamps if s is not None]
        # Earliest entry = creation; an incoming message has no entries, only its id.
        row.respond_ts = min(stamps) if stamps else respond_ts_from_message_id(
            payload.get("messageId"), sent_at=row.sent_at
        )

    if row.type != "outgoing" or not values:
        # Nothing about delivery here; resolved only if the clock is now known.
        return row.respond_ts is not None

    row.delivery_trace = entries
    if "failed" in values:
        failure = next(e for e in reversed(entries) if e.get("value") == "failed")
        row.delivery_status = "failed"
        row.delivery_error = str(failure.get("message") or "respond.io status failed")[:512]
        return True

    known = [v for v in values if v in _STATUS_RANK]
    if not known:
        return False
    row.delivery_status = max(known, key=_STATUS_RANK.__getitem__)
    row.delivery_error = None
    for entry in entries:
        ts = _epoch_to_naive_utc(entry.get("timestamp"))
        if entry.get("value") == "delivered" and ts is not None:
            row.delivered_ts = ts
        elif entry.get("value") == "read" and ts is not None:
            row.read_ts = ts
    return True


def _not_found_reason(exc: BaseException) -> str:
    """`HTTP 404: <Respond's error text>`, from the JSON `message` when there is one."""
    resp = getattr(exc, "response", None)
    text = ""
    if resp is not None:
        try:
            body = resp.json()
            if isinstance(body, dict):
                text = str(body.get("message") or body.get("error") or "")
        except Exception:  # noqa: BLE001 - a non-JSON body is still a reason
            pass
        text = text or (getattr(resp, "text", "") or "")
    return f"HTTP 404: {text.strip() or 'not found'}"[:512]


def _next_attempts(attempts: int, age: timedelta) -> int:
    """Skip to the next slot still ahead, so a late tick does not fire every minute."""
    passed = sum(1 for m in RESOLVE_SCHEDULE_MINUTES if age >= timedelta(minutes=m))
    return min(MAX_RESOLVE_ATTEMPTS, max(attempts + 1, passed))


def resolve_pending(
    db: Session,
    client: Any = None,
    limit: int = 200,
    now: Optional[datetime] = None,
) -> dict:
    """Resolve a batch of due rows. Never raises on a single bad row."""
    if client is None:
        from app.services.integration_service import RespondClient

        client = RespondClient()
    if now is None:
        now = datetime.utcnow()

    rows = _pending_rows(db, limit, now)
    resolved = failed = not_sent = 0

    for row in rows:
        attempts = int(row.resolve_attempts or 0)
        age = now - (row.respond_ts or row.sent_at)
        row.resolve_attempts = _next_attempts(attempts, age)
        try:
            try:
                payload = client.get_message(row.contact_id, row.message_id) or {}
            except Exception as exc:  # noqa: BLE001
                # RespondClient surfaces HTTP errors via raise_for_status. A 404 is the
                # "not dispatched (yet)" signal; every other status is transient and must
                # not be allowed to conclude that a message was never sent.
                resp = getattr(exc, "response", None)
                if resp is not None and getattr(resp, "status_code", None) == 404:
                    raise MessageNotFound(_not_found_reason(exc)) from exc
                raise
        except MessageNotFound as exc:
            # Logged, not silent: an unlogged 404 loop is indistinguishable from a
            # resolver that never ran, which is how a wrong workspace key hides.
            logger.warning(
                "chat_message_resolver: 404 for chat_histories.id=%s message_id=%s "
                "contact_id=%s (attempt %s/%s)",
                row.id, row.message_id, row.contact_id,
                row.resolve_attempts, MAX_RESOLVE_ATTEMPTS,
            )
            if row.type == "outgoing":
                row.delivery_error = str(exc)
                if age >= timedelta(minutes=NOT_SENT_AFTER_MINUTES):
                    # Provisional until the schedule ends: a later 200 upgrades it.
                    row.delivery_status = "not_sent"
                    not_sent += 1
            continue
        except Exception as exc:  # noqa: BLE001 - one bad row must not kill the batch
            failed += 1
            logger.warning(
                "chat_message_resolver: %s for chat_histories.id=%s message_id=%s",
                exc, row.id, row.message_id,
            )
            continue

        if _apply_payload(row, payload):
            resolved += 1

    db.commit()
    return {
        "scanned": len(rows),
        "resolved": resolved,
        "failed": failed,
        "not_sent": not_sent,
    }
