"""Sliding-window rate limiter for the email guardrail.

Uses Redis sorted sets (one entry per send, scored by unix timestamp).
On Redis failure falls back to a DB count over the same window — production
must never silently lose the cap.

Counters are bumped *after* a successful SMTP send, not at enqueue, so the drainer
can defer rows that would breach the cap without "using up" a slot.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class RateCheckResult:
    allowed: bool
    reason: Optional[str] = None
    retry_after_seconds: Optional[int] = None


def _redis_conn():
    """Lazily resolve the existing RQ Redis connection. Returns None on failure."""
    try:
        from app.services.queue_service import redis_conn
        return redis_conn
    except Exception as e:
        logger.warning("Email rate limiter: Redis connection unavailable (%s); using DB fallback.", e)
        return None


_KEY_PREFIX = "email_guardrail:v1"


def _bucket_key(scope: str, identifier: str) -> str:
    return f"{_KEY_PREFIX}:{scope}:{identifier}"


def _redis_count_and_seconds_to_oldest(key: str, window_seconds: int) -> tuple[int, int]:
    """Count entries in [now-window, now] and return seconds until the oldest expires."""
    r = _redis_conn()
    if r is None:
        return -1, 0
    now_ms = int(time.time() * 1000)
    window_ms = window_seconds * 1000
    cutoff_ms = now_ms - window_ms
    try:
        r.zremrangebyscore(key, 0, cutoff_ms)
        count = r.zcard(key)
        if count == 0:
            return 0, 0
        oldest = r.zrange(key, 0, 0, withscores=True)
        oldest_score = int(oldest[0][1]) if oldest else now_ms
        retry_after_ms = max(1, (oldest_score + window_ms) - now_ms)
        return int(count), int((retry_after_ms + 999) // 1000)
    except Exception as e:
        logger.warning("Email rate limiter: Redis error on %s (%s); falling back.", key, e)
        return -1, 0


def _db_count(db: Session, scope: str, identifier: str, window_seconds: int) -> int:
    """Count outbox rows successfully sent in the window. DB fallback path."""
    from app.models.email_outbox import EmailOutbox

    cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
    q = db.query(EmailOutbox).filter(
        EmailOutbox.status == "sent",
        EmailOutbox.sent_at != None,  # noqa: E711
        EmailOutbox.sent_at >= cutoff,
    )
    if scope == "global":
        pass
    elif scope == "recipient":
        q = q.filter(EmailOutbox.recipient_email == identifier)
    elif scope == "event":
        q = q.filter(EmailOutbox.event_key == identifier)
    else:
        return 0
    return q.count()


def check(
    db: Session,
    *,
    event_key: str,
    recipient_email: str,
    global_rate: int,
    global_window_seconds: int,
    per_recipient_rate: int,
    per_recipient_window_seconds: int,
    event_rate_override: Optional[int] = None,
    event_window_seconds_override: Optional[int] = None,
) -> RateCheckResult:
    """Check whether a send is allowed right now under the three caps.

    Returns RateCheckResult.allowed=False with a reason + retry_after_seconds when blocked.
    Order: per-event override → global → per-recipient. Stricter cap wins.
    """
    checks: list[tuple[str, str, int, int]] = []
    if event_rate_override and event_window_seconds_override:
        checks.append(("event", event_key, event_rate_override, event_window_seconds_override))
    checks.append(("global", "_all_", global_rate, global_window_seconds))
    checks.append(("recipient", recipient_email, per_recipient_rate, per_recipient_window_seconds))

    longest_retry = 0
    block_reason: Optional[str] = None
    for scope, ident, cap, window in checks:
        if cap <= 0:
            continue
        key = _bucket_key(scope, ident)
        count, retry_after = _redis_count_and_seconds_to_oldest(key, window)
        if count < 0:
            count = _db_count(db, scope, ident, window)
            retry_after = window
        if count >= cap:
            block_reason = f"{scope}_cap_exceeded:{count}/{cap}"
            longest_retry = max(longest_retry, retry_after or window)
    if block_reason:
        return RateCheckResult(allowed=False, reason=block_reason, retry_after_seconds=longest_retry)
    return RateCheckResult(allowed=True)


def record_send(
    *,
    event_key: str,
    recipient_email: str,
    global_window_seconds: int,
    per_recipient_window_seconds: int,
    event_window_seconds_override: Optional[int] = None,
) -> None:
    """Bump the per-scope counters after a successful SMTP send."""
    r = _redis_conn()
    if r is None:
        return
    now_ms = int(time.time() * 1000)
    member = f"{event_key}:{recipient_email}:{now_ms}"
    expiry_window = max(global_window_seconds, per_recipient_window_seconds, event_window_seconds_override or 0)
    try:
        pipe = r.pipeline()
        for key, window in [
            (_bucket_key("global", "_all_"), global_window_seconds),
            (_bucket_key("recipient", recipient_email), per_recipient_window_seconds),
        ]:
            pipe.zadd(key, {member: now_ms})
            pipe.expire(key, window + 60)
        if event_window_seconds_override:
            pipe.zadd(_bucket_key("event", event_key), {member: now_ms})
            pipe.expire(_bucket_key("event", event_key), event_window_seconds_override + 60)
        pipe.execute()
    except Exception as e:
        logger.warning("Email rate limiter: failed to record send (%s); DB fallback will catch up.", e)
