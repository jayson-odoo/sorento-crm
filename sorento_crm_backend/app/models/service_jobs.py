"""After-sales P1: the service job (a technician sent to a customer's site) and the technician.

Plan: documentation/plans/after-sales/PLAN-service-jobs-p1-12nov.md. A job carries its
own customer, contact, site and problem; the complaint is an optional reference. The technician is
a column, not a table of attempts: earlier tries show in History through the audit trail.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, func, text
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
    # Optional "Related complaint": a plain reference, nothing on the complaint side reads it.
    complaint_id = Column(
        UUID(as_uuid=False), ForeignKey("complaints.id", ondelete="SET NULL"), nullable=True
    )
    customer_name = Column(Text, nullable=False)
    contact_name = Column(Text, nullable=True)
    contact_phone = Column(Text, nullable=True)  # E.164
    site_address_line1 = Column(Text, nullable=True)
    site_address_line2 = Column(Text, nullable=True)
    site_postcode = Column(Text, nullable=True)
    site_city = Column(Text, nullable=True)
    site_state = Column(Text, nullable=True)
    site_country = Column(Text, nullable=True)
    problem = Column(Text, nullable=True)
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
        Index("ix_service_jobs_customer_name", "customer_name"),
        Index("ix_service_jobs_status_id", "status_id"),
        Index("ix_service_jobs_technician_id", "technician_id"),
        Index("ix_service_jobs_scheduled_from", "scheduled_from"),
    )


class ServiceJobProduct(Base, CompanyScopedMixin):
    """One product on a service job, with the facts the warranty answer needs (after-sales P2).

    The verdicts are never stored: they are computed from the policy in force when read.
    """

    __tablename__ = "service_job_products"
    __audit_parent__ = "service_job_id"  # history rolls up to the job

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    service_job_id = Column(
        UUID(as_uuid=False), ForeignKey("service_jobs.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    kind_id = Column(
        UUID(as_uuid=False), ForeignKey("warranty_product_kinds.id", ondelete="RESTRICT"), nullable=True
    )
    purchase_date = Column(Date, nullable=True)
    # lookup_options.id of the after_sales_defect_type set
    defect_type_id = Column(
        UUID(as_uuid=False), ForeignKey("lookup_options.id", ondelete="SET NULL"), nullable=True
    )
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_service_job_products_job", "service_job_id"),
        Index("ix_service_job_products_kind_id", "kind_id"),
    )
