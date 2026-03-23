"""Calendar and working days models."""
from sqlalchemy import Column, String, Boolean, Date, DateTime, Time, Text, Index
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
import uuid


class PublicHoliday(Base):
    __tablename__ = "public_holidays"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    date = Column(Date, nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_public_holidays_date", "date"),
    )


class WorkCalendarConfig(Base):
    __tablename__ = "work_calendar_configs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    config_key = Column(String(50), unique=True, nullable=False, default="default")
    monday = Column(Boolean, default=True, nullable=False)
    tuesday = Column(Boolean, default=True, nullable=False)
    wednesday = Column(Boolean, default=True, nullable=False)
    thursday = Column(Boolean, default=True, nullable=False)
    friday = Column(Boolean, default=True, nullable=False)
    saturday = Column(Boolean, default=False, nullable=False)
    sunday = Column(Boolean, default=False, nullable=False)
    # Default working hours on each working day (local / tenant time; used for display and future hour-based logic).
    work_day_start_time = Column(Time, nullable=False)
    work_day_end_time = Column(Time, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
