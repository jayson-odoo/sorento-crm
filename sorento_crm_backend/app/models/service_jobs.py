"""After-sales P1: the service job (a technician sent to a complaint's site) and the technician.

Plan: documentation/plans/after-sales/PLAN-service-jobs-p1-12nov.md. A job points at its
complaint with a real FK; the Site lives on the complaint, never copied here. The technician is
a column, not a table of attempts: earlier tries show in History through the audit trail.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base
from app.models.base import CompanyScopedMixin


class Technician(Base, CompanyScopedMixin):
    """Somebody who attends a site. Not a user: reached by phone, never a login."""

    __tablename__ = "technicians"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    phone = Column(String(32), nullable=True)
    # employee | contractor
    employment_type = Column(String(20), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (Index("ix_technicians_name", "name"),)


class ServiceJob(Base, CompanyScopedMixin):
    """One visit to one complaint's site."""

    __tablename__ = "service_jobs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_number = Column(String(64), nullable=True, unique=True)
    complaint_id = Column(
        UUID(as_uuid=False), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    status_id = Column(
        UUID(as_uuid=False), ForeignKey("statuses.id", ondelete="SET NULL"), nullable=True
    )
    technician_id = Column(
        UUID(as_uuid=False), ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True
    )

    # Naive UTC, like every other timestamp here; the board converts to the MYT day.
    scheduled_from = Column(DateTime(timezone=False), nullable=True)
    scheduled_to = Column(DateTime(timezone=False), nullable=True)
    customer_agreed_by = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    cancel_reason = Column(Text, nullable=True)
    arrived_at = Column(DateTime(timezone=False), nullable=True)
    completed_at = Column(DateTime(timezone=False), nullable=True)
    verified_at = Column(DateTime(timezone=False), nullable=True)

    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_service_jobs_complaint_id", "complaint_id"),
        Index("ix_service_jobs_status_id", "status_id"),
        Index("ix_service_jobs_technician_id", "technician_id"),
        Index("ix_service_jobs_scheduled_from", "scheduled_from"),
    )
