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
    __audit_skip__ = "chat conversation state"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))

    contact_id = Column(String(128), nullable=False)
    space_id = Column(String(32), nullable=False)
    channel = Column(String(32), nullable=False)
    # Chatbot turn re-architecture (AC-1505): the episode store's own contact key,
    # `respond_contacts.id` - a SEPARATE column from `contact_id` above (that one is
    # the Phase-1-2026 n8n identity, still read by nothing this rearch writes) so the
    # two eras of this table never collide on one column's meaning.
    contact_respond_id = Column(String(128), nullable=True, index=True)

    domain = Column(String(64), nullable=True)
    intent = Column(String(64), nullable=True)
    active_entities = Column(JSONB, nullable=False, server_default="{}")
    # AC-1505's own name for the same shape `active_entities` carries - kinds and ids,
    # JSONB. A second column rather than a rename: `active_entities` is read by the
    # parked Phase 1 (2026) code path this rearch does not touch.
    entities = Column(JSONB, nullable=False, server_default="{}")
    access_levels_used = Column(ARRAY(Text), nullable=False, server_default="{}")
    tools_used = Column(ARRAY(Text), nullable=False, server_default="{}")
    result_refs = Column(JSONB, nullable=False, server_default="[]")
    pending_request = Column(JSONB, nullable=False, server_default="{}")
    # The `chatbot.turns.id`s this frame's topic spans (AC-1505).
    turn_ids = Column(ARRAY(Text), nullable=False, server_default="{}")

    summary = Column(Text, nullable=True)
    last_user_message = Column(Text, nullable=True)
    last_assistant_summary = Column(Text, nullable=True)

    status = Column(String(16), nullable=False, server_default="open")
    close_reason = Column(String(32), nullable=True)

    started_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    # AC-1505's own name for `started_at` - a second column, same reason `entities` is:
    # `started_at` stays for the parked Phase 1 (2026) reader.
    opened_at = Column(DateTime(timezone=False), nullable=True)
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
