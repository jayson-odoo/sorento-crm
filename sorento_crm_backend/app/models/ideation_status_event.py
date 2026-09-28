"""Cursor for the shared service's idea status-event feed (#1355).

One row per feed base URL: a ``seq`` is only meaningful on the feed that issued it,
so repointing the CRM at another shared-service instance starts from that feed's
own cursor instead of skipping every event below a foreign seq. The poller moves
``after_seq`` in the same commit as the event's integration log row.

Plan: documentation/plans/ideation/PLAN-ideation-status-update-29sep.md
"""
from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Column, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class IdeationStatusEventCursor(Base):
    __tablename__ = "ideation_status_event_cursors"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    feed_base_url = Column(Text, nullable=False)
    after_seq = Column(BigInteger, nullable=False, default=0, server_default="0")
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("feed_base_url", name="uq_ideation_status_event_cursors_feed"),
    )
