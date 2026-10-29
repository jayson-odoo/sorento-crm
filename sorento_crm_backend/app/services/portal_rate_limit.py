"""Per-contact counters for the portal's project registration (audit round 3).

A redis INCR + EXPIRE in one script (the `chatbot/direct_ingress.py` shape, so the TTL is set in
the same step as the first increment). The connection is read at call time and any redis error
FAILS OPEN: a redis blip must never refuse a registration; the counter only exists to stop a
loop or a leaked slug from filling the queue.
"""
from __future__ import annotations

import logging

from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

_SCRIPT = (
    "local c = redis.call('INCR', KEYS[1]) "
    "if c == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end "
    "return c"
)

SAVE_LIMIT = 30
SAVE_WINDOW_SECONDS = 3600
EXTRACT_LIMIT = 10
EXTRACT_WINDOW_SECONDS = 600


def hit(bucket: str, contact_id: str, limit: int, window_seconds: int) -> None:
    """Count one call; raise 429 RATE_LIMITED once the contact is over `limit` in the window."""
    from app.services import queue_service

    key = f"portal:{bucket}:{contact_id}"
    try:
        count = int(queue_service.redis_conn.eval(_SCRIPT, 1, key, window_seconds))
    except Exception:  # noqa: BLE001
        logger.warning("portal rate limit unreadable for %s", key, exc_info=True)
        return
    if count > limit:
        raise AppException(
            status_code=429,
            message="Too many requests. Please try again later.",
            code="RATE_LIMITED",
        )


def project_registration_write(contact_id: str) -> None:
    """Create, update and submit share one budget: 30 an hour."""
    hit("projreg:write", contact_id, SAVE_LIMIT, SAVE_WINDOW_SECONDS)


def project_registration_extract(contact_id: str) -> None:
    """AI extract on the registration form: 10 in ten minutes."""
    hit("projreg:extract", contact_id, EXTRACT_LIMIT, EXTRACT_WINDOW_SECONDS)


def project_registration_extract_staff(user_id: str) -> None:
    """AI extract on the staff register form: 10 in ten minutes per user."""
    hit("projreg:extract_user", user_id, EXTRACT_LIMIT, EXTRACT_WINDOW_SECONDS)
