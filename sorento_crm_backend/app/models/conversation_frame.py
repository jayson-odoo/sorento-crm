"""Conversation frame: per-topic structured snapshot of an n8n chatbot exchange.

A frame represents a contiguous span of turns the user spent on a single topic
(domain + intent), holding the structured working memory the agent needs to
answer follow-ups without re-asking (e.g. selected access_levels, resolved
entities, tool results). Frames are opened on the first turn of a new topic,
updated as the user continues, and closed on topic-switch / role-switch /
idle. On close a summary is embedded via the existing embedding pipeline
(`source_type='conversation_frame'`) so prior frames can be retrieved via
vector search when the user references earlier context.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


class ConversationFrame(Base):
    __tablename__ = "conversation_frames"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))

    contact_id = Column(String(128), nullable=False)
    space_id = Column(String(32), nullable=False)
    channel = Column(String(32), nullable=False)

    domain = Column(String(64), nullable=True)
    intent = Column(String(64), nullable=True)
    active_entities = Column(JSONB, nullable=False, server_default="{}")
    access_levels_used = Column(ARRAY(Text), nullable=False, server_default="{}")
    tools_used = Column(ARRAY(Text), nullable=False, server_default="{}")
    result_refs = Column(JSONB, nullable=False, server_default="[]")
    pending_request = Column(JSONB, nullable=False, server_default="{}")

    summary = Column(Text, nullable=True)
    last_user_message = Column(Text, nullable=True)
    last_assistant_summary = Column(Text, nullable=True)

    status = Column(String(16), nullable=False, server_default="open")
    close_reason = Column(String(32), nullable=True)

    started_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    last_activity_at = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    closed_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_conversation_frames_contact_status", "contact_id", "status"),
        Index("ix_conversation_frames_contact_closed_at", "contact_id", "closed_at"),
        Index("ix_conversation_frames_contact_space_channel", "contact_id", "space_id", "channel"),
    )
