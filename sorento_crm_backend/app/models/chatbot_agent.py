"""`chatbot.agent_conversations` - one running conversation of the read-only agent (AGENTIC-P1).

The turns themselves are `chatbot.turns` rows (`ingress = "agent"`); this table holds only
what a turn row cannot: the conversation boundary ("New conversation" inserts a row) and the
running summary the compaction folds older turns into. A contact's current conversation is
its newest row. Nothing is deleted.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class AgentConversation(Base):
    __tablename__ = "agent_conversations"
    __audit_skip__ = "agent conversation boundary, the turn rows are the trail"
    __table_args__ = (
        Index("ix_agent_conversations_contact", "contact_respond_id"),
        {"schema": "chatbot"},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    # The respond.io contact id, as on `chatbot.turns`. Not an FK: same reason as the turn.
    contact_respond_id = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    summary = Column(Text, nullable=True)
    # `created_at` of the last turn folded into `summary`.
    summary_through = Column(DateTime(timezone=True), nullable=True)
    summary_tokens = Column(Integer, nullable=True)
