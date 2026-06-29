"""Commercial activity plan: templates, statuses, hierarchical tasks on master quotations."""
from __future__ import annotations

import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class CommercialActivityTaskStatus(Base):
    __tablename__ = "commercial_activity_task_statuses"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    code = Column(String(64), nullable=False, unique=True)
    label = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_default = Column(Boolean, nullable=False, default=False)
    is_terminal = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    color_hex = Column(String(7), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    template_nodes = relationship("CommercialActivityTemplateNode", back_populates="default_status")
    tasks = relationship("CommercialQuotationActivityTask", back_populates="status")


class CommercialActivityTemplate(Base):
    __tablename__ = "commercial_activity_templates"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    version_number = Column(Integer, nullable=False, default=1)
    template_scope = Column(String(32), nullable=False, server_default="project")
    created_by_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    nodes = relationship(
        "CommercialActivityTemplateNode",
        back_populates="template",
        cascade="all, delete-orphan",
    )
    plan_applications = relationship("CommercialActivityPlanApplication", back_populates="template")

    __table_args__ = (Index("ix_commercial_activity_templates_is_active", "is_active"),)


class CommercialProjectTaskCategory(Base):
    __tablename__ = "commercial_project_task_categories"

    code = Column(String(64), primary_key=True)
    label = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (Index("ix_commercial_project_task_categories_is_active", "is_active"),)


class CommercialActivityTemplateNode(Base):
    __tablename__ = "commercial_activity_template_nodes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    template_id = Column(UUID(as_uuid=False), ForeignKey("commercial_activity_templates.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(UUID(as_uuid=False), ForeignKey("commercial_activity_template_nodes.id", ondelete="CASCADE"), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    title = Column(String(512), nullable=False)
    category_code = Column(String(64), nullable=True)
    is_service_task = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=True)
    default_status_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_activity_task_statuses.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_offset_days = Column(Integer, nullable=True)
    lead_time_days = Column(Integer, nullable=False, default=1, server_default="1")
    dependency_node_ids = Column(JSON, nullable=False, default=list, server_default="[]")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    template = relationship("CommercialActivityTemplate", back_populates="nodes", foreign_keys=[template_id])
    parent = relationship(
        "CommercialActivityTemplateNode",
        remote_side="CommercialActivityTemplateNode.id",
        backref="children",
    )
    default_status = relationship("CommercialActivityTaskStatus", back_populates="template_nodes")

    __table_args__ = (
        Index("ix_commercial_activity_template_nodes_template_id", "template_id"),
        Index("ix_commercial_activity_template_nodes_parent_id", "parent_id"),
        Index("ix_commercial_activity_template_nodes_category_code", "category_code"),
    )


class CommercialActivityPlanApplication(Base):
    __tablename__ = "commercial_activity_plan_applications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    master_quotation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_master_quotations.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_id = Column(UUID(as_uuid=False), ForeignKey("commercial_activity_templates.id", ondelete="SET NULL"), nullable=True)
    template_version = Column(Integer, nullable=True)
    applied_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    applied_by_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    master_quotation = relationship("CommercialMasterQuotation", back_populates="activity_plan_applications")
    template = relationship("CommercialActivityTemplate", back_populates="plan_applications")

    __table_args__ = (Index("ix_commercial_activity_plan_applications_master_id", "master_quotation_id"),)


class CommercialProjectTask(Base):
    __tablename__ = "commercial_project_tasks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id = Column(UUID(as_uuid=False), ForeignKey("commercial_project_tasks.id", ondelete="CASCADE"), nullable=True)
    template_node_id = Column(UUID(as_uuid=False), nullable=True)
    parent_template_node_id = Column(UUID(as_uuid=False), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    category_code = Column(String(64), nullable=True)
    is_service_task = Column(Boolean, nullable=False, default=False, server_default="false")
    status_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_activity_task_statuses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assignee_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    lead_time_days = Column(Integer, nullable=False, default=1, server_default="1")
    dependency_task_ids = Column(JSON, nullable=False, default=list, server_default="[]")
    start_date = Column(DateTime(timezone=False), nullable=True)
    end_date = Column(DateTime(timezone=False), nullable=True)
    deleted_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    project = relationship("CommercialProject", foreign_keys=[project_id])
    parent = relationship(
        "CommercialProjectTask",
        remote_side="CommercialProjectTask.id",
        foreign_keys=[parent_id],
        backref="children",
    )
    status = relationship("CommercialActivityTaskStatus", foreign_keys=[status_id])

    __table_args__ = (
        Index("ix_commercial_project_tasks_project_id", "project_id"),
        Index("ix_commercial_project_tasks_parent_id", "parent_id"),
        Index("ix_commercial_project_tasks_assignee", "assignee_user_id"),
        Index("ix_commercial_project_tasks_status", "status_id"),
        Index("ix_commercial_project_tasks_deleted", "deleted_at"),
    )


class CommercialQuotationActivityTask(Base):
    __tablename__ = "commercial_quotation_activity_tasks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    master_quotation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_master_quotations.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id = Column(UUID(as_uuid=False), ForeignKey("commercial_quotation_activity_tasks.id", ondelete="CASCADE"), nullable=True)
    source_template_node_id = Column(UUID(as_uuid=False), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    title = Column(String(512), nullable=False)
    status_id = Column(UUID(as_uuid=False), ForeignKey("commercial_activity_task_statuses.id", ondelete="RESTRICT"), nullable=False)
    assignee_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_at = Column(DateTime(timezone=False), nullable=True)
    remind_at = Column(DateTime(timezone=False), nullable=True)
    last_reminder_sent_at = Column(DateTime(timezone=False), nullable=True)
    start_date = Column(DateTime(timezone=False), nullable=True)
    end_date = Column(DateTime(timezone=False), nullable=True)
    is_tender_level = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    master_quotation = relationship("CommercialMasterQuotation", back_populates="activity_tasks")
    parent = relationship(
        "CommercialQuotationActivityTask",
        remote_side="CommercialQuotationActivityTask.id",
        foreign_keys=[parent_id],
        backref="children",
    )
    status = relationship("CommercialActivityTaskStatus", back_populates="tasks")

    __table_args__ = (
        Index("ix_commercial_quotation_activity_tasks_master_id", "master_quotation_id"),
        Index("ix_commercial_quotation_activity_tasks_parent_id", "parent_id"),
        Index("ix_commercial_quotation_activity_tasks_assignee", "assignee_user_id"),
        Index("ix_commercial_quotation_activity_tasks_due_at", "due_at"),
        Index("ix_commercial_quotation_activity_tasks_deleted", "deleted_at"),
    )
