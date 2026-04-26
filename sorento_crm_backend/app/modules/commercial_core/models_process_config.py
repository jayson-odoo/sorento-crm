"""Admin-configurable commercial process: stages, templates, reminders, checkpoints, settings."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class CommercialReminderDefault(Base):
    __tablename__ = "commercial_reminder_defaults"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    context = Column(String(80), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    rule = Column(JSONB, nullable=False, server_default="{}")
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)


class CommercialTenderCheckpointTemplate(Base):
    __tablename__ = "commercial_tender_checkpoint_templates"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    checkpoint_code = Column(String(64), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)


class CommercialProcessSettings(Base):
    __tablename__ = "commercial_process_settings"

    id = Column(String(36), primary_key=True, default="default")
    assignment = Column(JSONB, nullable=False, server_default="{}")
    reminders = Column(JSONB, nullable=False, server_default="{}")
    pricing_controls = Column(JSONB, nullable=False, server_default="{}")
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
