"""Idempotency-Key attempts for Shared Service (AutoCount) writes.

The Shared Service stores every answer under the Idempotency-Key and replays it for the same key
and body (SS `modules/autocount/write_back/operations.py`). That is what makes a timeout retry
safe, but it also replays a REFUSAL to every later press of the same intent, even once the cause
was fixed in AutoCount or in the Shared Service (AC-E2E-DB3 B3/B5, 6 Nov 2026).

A definite refusal changed nothing in AutoCount, so the next press of that intent may go as a new
attempt. Anything else (a timeout, `pending_verification`, `needs_attention`, `vendor_error`, a
key still in flight) keeps the key, so a retry replays and can never write twice.

`VENDOR_UNSUPPORTED` is asked again ONCE in the same press, on the next attempt (round 2, SS #230
turned link / unlink / relink on): a refusal SS stored before the attempt count existed would
otherwise be replayed to the first press. If the count was lost (TTL, flush) after both attempts
were refused, one press replays both and the next press heals; never a write twice.

The attempt number per intent key lives in Redis (no schema), for as long as the Shared Service
could still hold the refused answer. With Redis unreachable every press uses attempt 0, i.e. the
plain intent key: the old behaviour, never a fresh key per press.
"""
from __future__ import annotations

import functools
import hashlib
import logging
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_PREFIX = "sorento:autocount_write:attempt:"
# A choice, not a measured SS retention: if the count expires first, the next press replays the
# stored refusals and walks forward again (never a write twice).
_TTL_SECONDS = 30 * 24 * 3600
# The key was refused because another request holds or used it, not because AutoCount said no.
_NOT_A_REFUSAL_OF_THE_INTENT = ("IDEMPOTENCY_",)
# SS turned these ops on after storing the refusal (SS #230, 10 Nov 2026): a VENDOR_UNSUPPORTED
# stored before the attempt count existed would be replayed to the first press. The press asks
# again once, on the next attempt; a refusal changed nothing, so it cannot write twice.
_ASK_AGAIN_AT_ONCE = ("VENDOR_UNSUPPORTED",)


# After a store error, skip it for this long: a down Redis must not cost its timeout per line.
_DOWN_SECONDS = 60
_down_until = 0.0


@functools.lru_cache(maxsize=1)
def _client() -> Optional[Any]:
    try:
        import redis

        from app.config import settings

        return redis.from_url(settings.redis_url, socket_timeout=1, socket_connect_timeout=1)
    except Exception:  # noqa: BLE001
        return None


def attempt_store() -> Optional[Any]:
    """The process's Redis client (1 s timeouts); None when it cannot be built or just failed."""
    if time.monotonic() < _down_until:
        return None
    return _client()


def store_failed() -> None:
    """Skip the store for `_DOWN_SECONDS` after an error (shared with `po_replace_hint`)."""
    global _down_until
    _down_until = time.monotonic() + _DOWN_SECONDS


def attempt_key(base: str, attempt: int) -> str:
    """Attempt 0 is the base key unchanged; later attempts are a short hash of base + attempt."""
    if attempt <= 0:
        return base
    return hashlib.sha256(f"{base}|attempt={attempt}".encode()).hexdigest()[:64]


def is_definite_refusal(answer: Dict[str, Any]) -> bool:
    """AutoCount refused and nothing was changed, so a new attempt cannot write twice."""
    if answer.get("outcome") != "refused":
        return False
    code = str(answer.get("errorCode") or "")
    return not code.startswith(_NOT_A_REFUSAL_OF_THE_INTENT)


def send_with_attempts(
    store: Optional[Any],
    base_key: str,
    send: Callable[[str], Dict[str, Any]],
) -> Dict[str, Any]:
    """`send(key)` on this intent's current attempt; a definite refusal moves the next press on,
    and a VENDOR_UNSUPPORTED one is asked again once in this press.

    `store` is a Redis-like client (`get`, `set(ex=)`) or None; any store error falls back to
    attempt 0 and never fails the write."""
    name = f"{_PREFIX}{base_key}"
    attempt = 0
    if store is not None:
        try:
            attempt = int(store.get(name) or 0)
        except Exception:  # noqa: BLE001
            logger.warning("autocount write: attempt store unreachable, using the intent key")
            store_failed()
            store = None
    answer = send(attempt_key(base_key, attempt))
    if not is_definite_refusal(answer):
        return answer
    attempt += 1
    if str(answer.get("errorCode") or "") in _ASK_AGAIN_AT_ONCE:
        answer = send(attempt_key(base_key, attempt))
        if is_definite_refusal(answer):
            attempt += 1
        # Anything else keeps this attempt, so a retry replays it.
    if store is not None:
        try:
            store.set(name, attempt, ex=_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            logger.warning("autocount write: could not record the refusal for a new attempt")
            store_failed()
    return answer
