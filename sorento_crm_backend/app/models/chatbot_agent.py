"""`chatbot.agent_conversations` - one running conversation of the read-only agent (AGENTIC-P1).

The turns themselves are `chatbot.turns` rows (`ingress = "agent"`); this table holds only
what a turn row cannot: the conversation boundary ("New conversation" inserts a row) and the
running summary the compaction folds older turns into. A contact's current conversation is
its newest row. Nothing is deleted.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    # Who the conversation was started for, and a digest of the contact's reveal grants then.
    # A different user or grant set starts a new conversation (history is not carried across).
    user_id = Column(String, nullable=True)
    grants_hash = Column(String(64), nullable=True)


class AgentAction(Base):
    """`chatbot.agent_actions` - one proposal of write steps the agent made for a contact's user
    (AGENTIC-P3). `steps` holds each step's tool, args, the record as it was (`before`), the line the
    user confirmed, and its outcome; the domain writes are audited by their own listeners."""

    __tablename__ = "agent_actions"
    __audit_skip__ = "agent action ledger, the domain writes carry their own audit rows"
    __table_args__ = (
        Index("ix_agent_actions_contact", "contact_respond_id"),
        {"schema": "chatbot"},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    conversation_id = Column(UUID(as_uuid=False), nullable=False)
    # The proposing turn, and the turn that confirmed it when that was a chat turn.
    turn_id = Column(UUID(as_uuid=False), nullable=False)
    confirm_turn_id = Column(UUID(as_uuid=False), nullable=True)
    contact_respond_id = Column(String(64), nullable=False)
    user_id = Column(String, nullable=False)
    # Who confirmed or cancelled: the console operator, else the linked user (a chat decision).
    decided_by_user_id = Column(String, nullable=True)
    # proposed | executing | executed | partial | rejected | cancelled | expired
    status = Column(String(16), nullable=False, default="proposed")
    steps = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    # console | chat
    via = Column(String(16), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    decided_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
