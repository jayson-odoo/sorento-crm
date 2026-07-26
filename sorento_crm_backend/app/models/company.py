"""Company (multi-company data-isolation partition) models.

A ``company`` is a data partition BELOW the (stubbed) tenant — both Sorento and
Mocha live under ``tenant="__default__"`` but own disjoint business data
(products, stock, orders, ...). Users and Respond contacts are SHARED and tagged
into companies via the M2M grant/membership tables below.

See ``documentation/plans/PLAN-multi-company-isolation.md`` §16 / §4.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Company(Base):
    """A data-isolation partition. Superadmin-only CRUD + grant management."""

    __tablename__ = "companies"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False)  # short, e.g. SRT / MCH
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    autocount_ref = Column(String(255), nullable=True)  # AutoCount company reference
    logo_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_companies_is_active", "is_active"),
    )


class UserCompany(Base):
    """User -> company grant (M2M). Global role — one role per user across all
    their companies (RBAC is orthogonal to company). Union of grants = a user's
    switchable company set."""

    __tablename__ = "user_companies"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "company_id", name="uq_user_companies_user_id_company_id"),
        Index("ix_user_companies_user_id", "user_id"),
        Index("ix_user_companies_company_id", "company_id"),
    )


class RespondContactCompany(Base):
    """Respond contact -> company membership (M2M). Admin-managed, NOT derived
    from access_types. A contact can belong to Sorento, Mocha, or both; the union
    drives the n8n/MCP company scope for that contact."""

    __tablename__ = "respond_contact_companies"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    respond_contact_id = Column(String, ForeignKey("respond_contacts.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("respond_contact_id", "company_id", name="uq_respond_contact_companies_contact_company"),
        Index("ix_respond_contact_companies_contact_id", "respond_contact_id"),
        Index("ix_respond_contact_companies_company_id", "company_id"),
    )
