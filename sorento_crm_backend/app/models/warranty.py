"""After-sales P2: the four tables the warranty engine answers from.

Kinds and kind rules are shared by every company ("Water Closet" is one thing whichever brand
sells it). A policy is company-scoped (each brand publishes its own durations); a term is reached
only through its policy, so it carries no company column of its own.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.database import Base
from app.models.base import CompanyScopedMixin


class WarrantyProductKind(Base):
    """A kind of product a policy gives terms to (Water Closet, Booster Pump...)."""

    __tablename__ = "warranty_product_kinds"
    # Migration-seeded reference rows, visible to every company.
    __company_shared__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(64), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_warranty_product_kinds_is_active", "is_active"),
        Index("ix_warranty_product_kinds_sort_order", "sort_order"),
    )


class WarrantyKindRule(Base):
    """Maps a product to a kind: by category, code prefix, model list or series."""

    __tablename__ = "warranty_kind_rules"
    __company_shared__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind_id = Column(
        UUID(as_uuid=False), ForeignKey("warranty_product_kinds.id", ondelete="CASCADE"), nullable=False
    )
    # series | model_list | category | code_prefix
    match_type = Column(String(20), nullable=False)
    match_value = Column(Text, nullable=False)
    priority = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_warranty_kind_rules_kind_id", "kind_id"),
        Index("ix_warranty_kind_rules_match_type", "match_type"),
    )


class WarrantyPolicy(Base, CompanyScopedMixin):
    """One published version of a company's warranty policy, valid over a date window."""

    __tablename__ = "warranty_policies"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    version = Column(String(32), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)  # NULL = open ended
    source_attachment_id = Column(
        UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )
    policy_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "version", name="uq_warranty_policies_company_version"),
        Index("ix_warranty_policies_effective_from", "effective_from"),
        Index("ix_warranty_policies_effective_to", "effective_to"),
    )


class WarrantyTerm(Base):
    """One part's cover of one kind under one policy."""

    __tablename__ = "warranty_terms"
    __audit_parent__ = "policy_id"  # history rolls up to the policy

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id = Column(
        UUID(as_uuid=False), ForeignKey("warranty_policies.id", ondelete="CASCADE"), nullable=False
    )
    kind_id = Column(
        UUID(as_uuid=False), ForeignKey("warranty_product_kinds.id", ondelete="CASCADE"), nullable=False
    )
    part_name = Column(String(120), nullable=False)
    duration_months = Column(Integer, nullable=True)
    is_lifetime = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # lookup_options.id of the after_sales_defect_type set; NULL or empty = every defect.
    covered_defect_type_ids = Column(ARRAY(UUID(as_uuid=False)), nullable=True)
    installation_included = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    qualifications = Column(Text, nullable=True)
    exclusions = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        UniqueConstraint("policy_id", "kind_id", "part_name", name="uq_warranty_terms_policy_kind_part"),
        CheckConstraint(
            "(is_lifetime AND duration_months IS NULL) OR "
            "(NOT is_lifetime AND duration_months IS NOT NULL AND duration_months > 0)",
            name="ck_warranty_terms_duration_xor_lifetime",
        ),
        Index("ix_warranty_terms_policy_kind", "policy_id", "kind_id"),
    )
