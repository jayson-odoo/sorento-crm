"""Automation models: rule-driven scheduled email sends."""
import uuid
from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Time,
    Text,
    Integer,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class Automation(Base):
    __tablename__ = "automations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)

    trigger_type = Column(String(80), nullable=False)
    trigger_config = Column(JSONB, nullable=False, default=dict)

    action_type = Column(String(80), nullable=False, default="send_email")
    email_template_id = Column(
        UUID(as_uuid=False),
        ForeignKey("email_templates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    recipient_config = Column(JSONB, nullable=False, default=dict)

    # When true (default), a multi-match scheduled run (only the
    # days_before_promotion_end trigger today) sends ONE combined email per
    # recipient listing every matched promotion, instead of one email per match.
    group_matches = Column(Boolean, nullable=False, default=True)

    schedule_type = Column(String(20), nullable=False, default="manual")  # manual | daily
    run_time = Column(Time, nullable=True)
    timezone = Column(String(80), nullable=False, default="Asia/Kuala_Lumpur")

    last_run_at = Column(DateTime(timezone=False), nullable=True)
    last_status = Column(String(20), nullable=True)
    last_error = Column(Text, nullable=True)
    next_run_at = Column(DateTime(timezone=False), nullable=True, index=True)

    created_by_user_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    runs = relationship(
        "AutomationRun",
        back_populates="automation",
        order_by="AutomationRun.started_at.desc()",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_automations_enabled_next_run_at", "enabled", "next_run_at"),
    )


class AutomationRun(Base):
    __tablename__ = "automation_runs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    automation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("automations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_mode = Column(String(20), nullable=False, default="manual")  # manual | scheduled
    started_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=False), nullable=True)
    status = Column(String(20), nullable=False, default="running")  # running | success | partial | failed
    duration_ms = Column(Integer, nullable=True)
    recipients_attempted = Column(Integer, nullable=False, default=0)
    recipients_delivered = Column(Integer, nullable=False, default=0)
    summary = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)

    automation = relationship("Automation", back_populates="runs")

    __table_args__ = (
        Index("ix_automation_runs_automation_id_started_at", "automation_id", "started_at"),
    )
