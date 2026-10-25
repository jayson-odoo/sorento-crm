"""A project registration raised from the portal (PROJECT-REG-PORTAL).

A sales agent types the legacy paper form in the portal; a Project Sales Admin approves it
in the CRM, which creates the `Project` and draws its PPF code. The typed values stay as
typed (D3): the admin resolves developer, architect and contractor to parties on Approve.

In the `projects` schema with the other Project Sales tables. Plan:
documentation/plans/projects/PLAN-project-registration-portal-25oct.md.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base
from app.models.base import CompanyScopedMixin


def _uuid_str() -> str:
    return str(uuid.uuid4())


STATUS_DRAFT = "draft"
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

#: The eleven contact-written fields (D3), in form order.
FIELD_KEYS = (
    "title",
    "distributor_name",
    "customer_id",
    "customer_name",
    "type_of_building",
    "state",
    "mukim",
    "your_ref",
    "developer_name",
    "main_contractor_name",
    "architect_name",
)


class ProjectRegistration(Base, CompanyScopedMixin):
    __tablename__ = "project_registrations"
    __audit_entity_type__ = "project_registrations"
    __audit_track__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, server_default=STATUS_DRAFT)

    contact_id = Column(Text, ForeignKey("respond_contacts.id", ondelete="SET NULL"), nullable=True)
    sales_agent_id = Column(
        UUID(as_uuid=False), ForeignKey("sales_agents.id", ondelete="SET NULL"), nullable=True
    )
    #: The CRM user linked to the contact, stamped on submit; who gets the decision notice.
    applicant_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    project_id = Column(
        UUID(as_uuid=False), ForeignKey("projects.projects.id", ondelete="SET NULL"), nullable=True
    )

    submitted_at = Column(DateTime(timezone=False), nullable=True)
    decided_at = Column(DateTime(timezone=False), nullable=True)
    decided_by = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reject_reason = Column(Text, nullable=True)

    title = Column(Text, nullable=True)
    distributor_name = Column(String(255), nullable=True)
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    customer_name = Column(String(255), nullable=True)
    type_of_building = Column(String(255), nullable=True)
    state = Column(String(100), nullable=True)
    mukim = Column(String(255), nullable=True)
    your_ref = Column(String(255), nullable=True)
    developer_name = Column(String(255), nullable=True)
    main_contractor_name = Column(String(255), nullable=True)
    architect_name = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_project_registrations_status", "status"),
        Index("ix_project_registrations_contact", "contact_id"),
        {"schema": "projects"},
    )
