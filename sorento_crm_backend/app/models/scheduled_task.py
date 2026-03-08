"""Scheduled task and run models for configurable background jobs."""
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class ScheduledTask(Base):
    """Configurable scheduled task (e.g. Respond.io sync, integration log retry)."""
    __tablename__ = "scheduled_tasks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    key = Column(String(100), unique=True, nullable=False, index=True)  # e.g. respond_contacts_sync
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)  # context for UI
    enabled = Column(Boolean, default=True, nullable=False)
    interval_unit = Column(String(20), nullable=False)  # seconds | minutes | hours | days
    interval_value = Column(Integer, nullable=False)  # e.g. 10 for "every 10 minutes"
    timezone = Column(String(50), default="UTC", nullable=False)
    start_at = Column(DateTime(timezone=False), nullable=True)
    next_run_at = Column(DateTime(timezone=False), nullable=True, index=True)
    last_run_at = Column(DateTime(timezone=False), nullable=True)
    last_status = Column(String(50), nullable=True)  # started | success | failed | skipped
    last_error = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    runs = relationship("ScheduledTaskRun", back_populates="task", order_by="ScheduledTaskRun.started_at.desc()")

    __table_args__ = (Index("ix_scheduled_tasks_next_run_at_enabled", "next_run_at", "enabled"),)


class ScheduledTaskRun(Base):
    """Execution log for a scheduled task run."""
    __tablename__ = "scheduled_task_runs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(UUID(as_uuid=False), ForeignKey("scheduled_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=False), nullable=True)
    status = Column(String(50), nullable=False)  # started | success | failed | skipped
    duration_ms = Column(Integer, nullable=True)
    summary = Column(JSONB, nullable=True)  # e.g. {"scanned": 10, "created": 2, "failed": 0}
    error = Column(Text, nullable=True)

    task = relationship("ScheduledTask", back_populates="runs")

    __table_args__ = (Index("ix_scheduled_task_runs_task_id_started_at", "task_id", "started_at"),)
