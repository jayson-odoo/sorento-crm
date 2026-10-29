"""Turn-row seeding for the agent memory tests (not a test module)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.chatbot_turn import ChatbotTurn

BASE = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def at(minute: int) -> datetime:
    return BASE + timedelta(minutes=minute)


def seed_turn(db, conv, *, minute: int, text: str, reply: str, digest=None, ingress: str = "agent") -> ChatbotTurn:
    """One finished agent turn of `conv`, created at BASE + `minute` minutes."""
    row = ChatbotTurn(
        id=str(uuid.uuid4()),
        contact_respond_id=conv.contact_respond_id,
        ingress=ingress,
        is_test=True,
        status="done",
        envelope={"text": text, "agent_conversation_id": str(conv.id)},
        response={"reply_text": reply, "tool_digest": digest or [], "status": "answered", "limit_hit": None},
        created_at=at(minute),
    )
    db.add(row)
    db.flush()
    return row
