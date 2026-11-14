"""The contact's last completed chatbot exchanges, read from `chatbot.turns` (PR #1247 round 8).

Core, so the ideation capture (WA-COMPLAINT-INTAKE round 14) reads the same exchanges the parser reads
without importing `app.services.chatbot` (`tests/chatbot/test_import_boundary.py`). The package re-exports
these names from `turn_runtime` and `turn/context`, so every existing caller is unchanged.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# `console` is its own world: a console turn replays against the operator's own thread
# and must never read the customer's live reply as its "previous response" (nor the other
# way round). Every other ingress - webhook, poller, retry - is the same live stream.
_CONSOLE_INGRESS = "console"

#: How much of one exchange's text the parser reads (PR #1247 round 8). A ten-line
#: point-form question is about 250 characters; a stock answer for ten products is
#: longer, and its head is what a short reply refers to. One copy, shared by the assembler,
#: `parser.build_user_block` and the ideation extractor.
EXCHANGE_TEXT_CAP = 500


def exchange_text(value: Any) -> str:
    """One line of one exchange: newlines become " / ", at most `EXCHANGE_TEXT_CAP`."""
    text = " / ".join(part.strip() for part in str(value or "").splitlines() if part.strip())
    if len(text) > EXCHANGE_TEXT_CAP:
        return text[:EXCHANGE_TEXT_CAP] + "..."
    return text


def _envelope_text(envelope: Any) -> str | None:
    """The message text a stored envelope carries (the respond.io payload,
    `message.message.message.text`), else an attachment's description."""
    inner = envelope
    for key in ("message", "message", "message"):
        inner = inner.get(key) if isinstance(inner, dict) else None
    if not isinstance(inner, dict):
        return None
    text = inner.get("text")
    if not (isinstance(text, str) and text.strip()):
        attachment = inner.get("attachment")
        text = attachment.get("description") if isinstance(attachment, dict) else None
    return text if isinstance(text, str) and text.strip() else None


def _newest_turn_first(model: Any) -> tuple[Any, ...]:
    """Newest turn first: `created_at`, then `started_at` for rows that tie on it."""
    return (model.created_at.desc(), model.started_at.desc().nullslast())


def recent_exchanges(
    db: Session,
    *,
    contact_respond_id: str,
    ingress: str | None,
    is_test: bool,
    limit: int = 3,
    test_run_id: str | None = None,
) -> list[tuple[str, str]]:
    """The last `limit` completed exchanges with this contact, oldest first, as (what
    the contact said, what the bot answered) - the parser's "Recent exchanges" lines
    (PR #1247 round 8: the owner's "is the context too less already?").

    Read from the same rows and under the same three scopes as `previous_reply_text`,
    so the newest pair's answer IS the Previous response. A row with no reply text is
    skipped; a row whose envelope carries no text (a photo or voice note) is "(media)".
    A lookup failure is no exchanges, never a failed turn.
    """
    from app.models.chatbot_turn import ChatbotTurn

    try:
        query = db.query(ChatbotTurn.envelope, ChatbotTurn.response).filter(
            ChatbotTurn.contact_respond_id == str(contact_respond_id),
            ChatbotTurn.status == "done",
            ChatbotTurn.is_test.is_(bool(is_test)),
        )
        if str(ingress or "") == _CONSOLE_INGRESS:
            query = query.filter(ChatbotTurn.ingress == _CONSOLE_INGRESS)
            if test_run_id:
                # REPORT-SMART-L S5-1: a console Reset is a new run id; only this run's turns are history.
                query = query.filter(ChatbotTurn.envelope["test_run_id"].astext == str(test_run_id))
        else:
            query = query.filter(ChatbotTurn.ingress != _CONSOLE_INGRESS)
        rows = query.order_by(*_newest_turn_first(ChatbotTurn)).limit(limit * 2).all()
    except Exception:  # noqa: BLE001 - no history is no lines, never a failure
        logger.warning(
            "chatbot: recent exchanges lookup failed for %s", contact_respond_id, exc_info=True
        )
        return []
    pairs: list[tuple[str, str]] = []
    for envelope, response in rows:
        reply = response.get("reply") if isinstance(response, dict) else None
        answer = reply.get("text") if isinstance(reply, dict) else None
        if not (isinstance(answer, str) and answer.strip()):
            continue
        pairs.append((_envelope_text(envelope) or "(media)", answer))
        if len(pairs) == limit:
            break
    return list(reversed(pairs))
