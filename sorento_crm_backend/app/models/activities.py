"""Activities & Notes — generic per-entity activity feed, internal notes, mentions.

Any consuming module (tickets, complaints, leads, etc.) registers an adapter in
``app.services.activities_registry`` and references its rows via
``(entity_type, entity_id)``.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


class ActivityEvent(Base):
    """One row in the entity's Activities feed.

    ``kind`` = ``system`` (auto, e.g. status changes), ``user_update`` (composer post)
    or ``call`` (S4/AC-M34: a phone call, manual or from Respond.io's ``On Call
    ended``). A call is neither of the first two — no software did it, and it is not a
    composer post: it carries structured fields (direction, outcome, duration, next
    action) in ``system_payload`` that no composer produces.

    System rows store a fixed ``system_template`` + ``system_payload`` so the FE can
    render localized phrasing; user rows store rendered ``body_html`` + plaintext.
    """

    __tablename__ = "activity_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=False)
    kind = Column(String(20), nullable=False, default="user_update")
    body_html = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)
    system_template = Column(String(100), nullable=True)
    system_payload = Column(JSONB, nullable=True)
    # ``users.id``, which is VARCHAR. This column was uuid, which is the same
    # model-versus-column type drift that broke ``user_sessions.id`` on prod: every
    # user id happens to be uuid-shaped today only because ``User.id`` defaults to
    # uuid4, and nothing enforces it. Widened by S4, which is the first writer here
    # that does not come from an authenticated staff session.
    actor_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_activity_events_entity", "entity_type", "entity_id", "created_at"),
        Index("ix_activity_events_actor", "actor_id"),
    )


class InternalNote(Base):
    """Private note scoped to ``author_id`` only — never visible to other users."""

    __tablename__ = "internal_notes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=False)
    author_id = Column(UUID(as_uuid=False), nullable=False)
    body_html = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_internal_notes_entity_author", "entity_type", "entity_id", "author_id", "created_at"),
    )


class ActivityMention(Base):
    """@-mention from an ActivityEvent.user_update; drives notifications."""

    __tablename__ = "activity_mentions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    activity_event_id = Column(
        UUID(as_uuid=False),
        ForeignKey("activity_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    mentioned_user_id = Column(UUID(as_uuid=False), nullable=False)
    seen_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_activity_mentions_user_unseen", "mentioned_user_id", "seen_at"),
        Index("ix_activity_mentions_event", "activity_event_id"),
    )
