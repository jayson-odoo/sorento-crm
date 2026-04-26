"""Unified workflow stages for lead, quotation, tender, task, and project domains.

Note: sorento keeps `order_statuses` as a separate table for the order domain,
so this model intentionally does NOT carry an `orders` relationship. The
commercial domain back-references (leads, master_quotations, commercial_projects)
are installed at runtime by `app/modules/commercial_core/_base_patches.py` when
that module is enabled — the base class stays free of commercial dependencies.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class WorkflowStage(Base):
    __tablename__ = "workflow_stages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    domain = Column(String(32), nullable=False)
    code = Column(String(50), nullable=False)
    label = Column(String(100), nullable=False)
    color_hex = Column(String(7), nullable=True)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0")
    is_terminal = Column(Boolean, nullable=False, server_default="false")
    allows_conversion = Column(Boolean, nullable=True)
    can_go_back = Column(Boolean, nullable=False, server_default="false")
    is_active = Column(Boolean, nullable=False, server_default="true")
    is_cancelled = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "domain IN ('lead','quotation','tender','task','order','project')",
            name="ck_workflow_stages_domain",
        ),
        UniqueConstraint("domain", "code", name="uq_workflow_stages_domain_code"),
        Index("ix_workflow_stages_domain_sort", "domain", "sort_order"),
        Index("ix_workflow_stages_domain_active", "domain", "is_active"),
    )


WORKFLOW_DOMAIN_LEAD = "lead"
WORKFLOW_DOMAIN_QUOTATION = "quotation"
WORKFLOW_DOMAIN_TENDER = "tender"
WORKFLOW_DOMAIN_TASK = "task"
WORKFLOW_DOMAIN_ORDER = "order"
WORKFLOW_DOMAIN_PROJECT = "project"
