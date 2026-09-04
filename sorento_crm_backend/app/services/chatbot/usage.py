"""Recording what a chatbot turn spent on the LLM (SEC2).

Every other LLM call in this system reports into `ai_assistant_usage_logs`. The chatbot
parser runs once per live turn, at production volume, and was the one that did not - so
the bill existed and the table did not show it. `feature = "chatbot_parser"` keeps it
separable from the assistant's own rows.

**Live turns only.** A dry run is a clone or a console turn: it costs a real token spend,
but attributing it to the customer's usage would make every rehearsal look like traffic.
D14 says a test envelope writes nothing outside `chatbot.turns`, and this obeys that.

Never raises. A telemetry write that can fail a customer's turn is worse than a missing
row, and the row it would have written is a number, not the answer.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

FEATURE = "chatbot_parser"


def record_parser_usage(
    db: Session,
    *,
    usage: dict[str, Any],
    response_time_ms: int,
    contact_respond_id: str,
    answered: bool,
) -> None:
    """One `ai_assistant_usage_logs` row for one parser call."""
    try:
        from app.models.access import RespondContact
        from app.models.ai_assistant import AIAssistantUsageLog

        # `contact_id` on this table is the INTERNAL respond_contacts.id, not the
        # respond.io id the envelope carries (the FK is to respond_contacts.id).
        internal_id = (
            db.query(RespondContact.id)
            .filter(RespondContact.respond_io_id == contact_respond_id)
            .scalar()
        )
        db.add(
            AIAssistantUsageLog(
                user_id=None,
                contact_id=internal_id,
                feature=FEATURE,
                provider=usage.get("provider"),
                model=usage.get("model"),
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
                tool_calls_count=0,
                response_time_ms=int(response_time_ms),
                was_answered=bool(answered),
            )
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 - telemetry must never fail a customer's turn
        logger.warning("chatbot: parser usage log failed: %s", exc, exc_info=True)
        try:
            db.rollback()
        except Exception:  # pragma: no cover - defensive
            pass
