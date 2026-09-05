"""Settle turns an n8n lane took over and never finished (AC-260).

A `delegated` turn is one the CRM handed to an n8n lane, which is expected to finish it by
calling `/complete`. When that lane dies mid-turn - the workflow errored, the worker was
redeployed, the execution was deleted - the call never comes, and the row stays
`delegated` for ever. Two things break: the trace list fills with ghosts that look like
work still in progress, and Retry cannot touch them, because R4 makes a manual retry
possible on a FAILED turn only. This sweep is what turns a lost lane into a failure an
operator can see and act on.

**In core, not in `app/services/chatbot/`.** The scheduler is core and core never imports
that package (`tests/chatbot/test_import_boundary.py`); this file touches only the model,
the settings and one literal trace record whose shape is owned by
`app/services/chatbot/trace.py`. Keeping it here is what lets the sweep keep running if
the package is ever lifted behind an HTTP boundary, because the ROW is what it settles.

Idempotent by construction: it only ever reads rows that are still `delegated`, and it
leaves them `failed`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.chatbot_turn import ChatbotTurn

logger = logging.getLogger(__name__)

# One tick's work. A backlog larger than this is a broken n8n, not a sweep problem, and
# the next tick (a minute later) takes the next batch.
SWEEP_BATCH = 200


def _ttl_minutes() -> int:
    return max(1, int(getattr(settings, "chatbot_delegated_ttl_minutes", 10) or 10))


def sweep_stalled_delegated_turns(
    db: Session,
    *,
    now: Optional[datetime] = None,
    ttl_minutes: Optional[int] = None,
) -> int:
    """Fail every `delegated` turn older than the TTL. Returns how many were settled.

    Test turns included: a clone or console turn that hangs is exactly as misleading on the
    trace screen as a live one, and D14's rule is about what a test turn WRITES elsewhere,
    not about whether its own row is kept honest.
    """
    minutes = _ttl_minutes() if ttl_minutes is None else max(1, int(ttl_minutes))
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=minutes)

    rows = (
        db.query(ChatbotTurn)
        .filter(
            ChatbotTurn.status == "delegated",
            # `started_at` is when the CRM began the turn, which is what the lane's clock
            # runs from. It is set on every row at insert; `created_at` is the fallback for
            # a row written before it was.
            func.coalesce(ChatbotTurn.started_at, ChatbotTurn.created_at) < cutoff,
        )
        .order_by(ChatbotTurn.created_at.asc())
        .limit(SWEEP_BATCH)
        .all()
    )
    if not rows:
        return 0

    error = f"n8n lane did not complete within {minutes} minutes"
    for row in rows:
        # The same record shape every stage writes (`app/services/chatbot/trace.py`), so
        # the trace screen renders this without a special case. `kind: "note"` because it
        # is something that happened TO the turn - nobody ran a ninth stage.
        note = {
            "kind": "note",
            "stage": "delegated",
            "status": "failed",
            "started_at": now.isoformat(),
            "ms": 0,
            "summary": f"Gave up waiting: {error}.",
            "why": (
                "The lane that took this turn over never reported back, so the turn is "
                "recorded as failed and can be retried."
            ),
            "facts": {"ttl_minutes": minutes, "swept_at": now.isoformat()},
            "error": error,
            "raw": None,
        }
        row.trace = list(row.trace or []) + [note]
        row.status = "failed"
        row.stage = "delegated"
        row.error = error
        row.finished_at = now
    db.commit()
    logger.warning("chatbot sweep: failed %d turn(s) stuck in delegated", len(rows))
    return len(rows)
