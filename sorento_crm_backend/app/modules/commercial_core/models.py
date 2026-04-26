"""Commercial hierarchy: customer (profile) → lead → project → tender → master quotation → revision → sales order."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

# Eager-import platform model files referenced by string ``relationship("...")``
# below. Use ``importlib`` to load the submodule directly without triggering
# ``app.models.__init__`` — that ``__init__`` itself imports commercial_core,
# which would create a circular import during fresh-deployment discovery.
import importlib as _importlib
for _mod in (
    "app.models.user",  # User
    "app.models.workflow_stage",  # WorkflowStage
    "app.models.respond_workspace",  # RespondWorkspace
    "app.models.access",  # RespondContact
):
    try:
        _importlib.import_module(_mod)
    except Exception:  # noqa: BLE001
        # Missing platform file → SQLAlchemy will surface a clearer error at
        # configure_mappers() time. Don't block module load here.
        pass
del _importlib, _mod

if TYPE_CHECKING:
    from app.models.order import Customer
    from app.models.user import User


def _uuid_str() -> str:
    return str(uuid.uuid4())


class CommercialLeadNote(Base):
    __tablename__ = "commercial_lead_notes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    lead_id = Column(UUID(as_uuid=False), ForeignKey("commercial_leads.id", ondelete="CASCADE"), nullable=False)
    body = Column(Text, nullable=False)
    created_by_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    lead = relationship("CommercialLead", back_populates="notes")
    created_by = relationship("User", foreign_keys=[created_by_user_id])

    __table_args__ = (Index("ix_commercial_lead_notes_lead_id", "lead_id"),)


class CommercialTask(Base):
    """Top-level CRM task for pipeline boards (optional link to lead and/or tender)."""

    __tablename__ = "commercial_tasks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    title = Column(Text, nullable=False)
    due_on = Column(Date, nullable=True)
    status = Column(String(80), nullable=False, default="open")
    owner_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    lead_id = Column(UUID(as_uuid=False), ForeignKey("commercial_leads.id", ondelete="CASCADE"), nullable=True)
    tender_id = Column(UUID(as_uuid=False), ForeignKey("commercial_tenders.id", ondelete="CASCADE"), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    owner = relationship("User", foreign_keys=[owner_user_id])
    lead = relationship("CommercialLead", back_populates="pipeline_tasks")
    tender = relationship("CommercialTender", back_populates="pipeline_tasks")

    __table_args__ = (
        Index("ix_commercial_tasks_owner_user_id", "owner_user_id"),
        Index("ix_commercial_tasks_lead_id", "lead_id"),
        Index("ix_commercial_tasks_tender_id", "tender_id"),
        Index("ix_commercial_tasks_due_on", "due_on"),
        Index("ix_commercial_tasks_status", "status"),
    )


class CommercialSalesOrderStatus:
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    VOID = "void"
    CANCELLED = "cancelled"
    ALL = (DRAFT, CONFIRMED, VOID, CANCELLED)
    ACTIVE_FOR_TENDER_UNIQUE = (DRAFT, CONFIRMED)


class CommercialTenderLifecycle:
    OPEN = "open"
    CLOSED = "closed"
    ALL = (OPEN, CLOSED)


class CommercialTenderOutcome:
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    WITHDRAWN = "withdrawn"
    NO_AWARD = "no_award"
    ALL = (PENDING, WON, LOST, WITHDRAWN, NO_AWARD)
    CLOSE_WITHOUT_ORDER = (LOST, WITHDRAWN, NO_AWARD)


class CommercialMasterQuotationPathRole:
    OPEN = "open"
    WINNER = "winner"
    CLOSED_SUPERSEDED = "closed_superseded"
    CLOSED_UNAWARDED = "closed_unawarded"
    ALL = (OPEN, WINNER, CLOSED_SUPERSEDED, CLOSED_UNAWARDED)


class CommercialLead(Base):
    __tablename__ = "commercial_leads"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    lead_code = Column(String(64), nullable=False, unique=True)
    title = Column(Text, nullable=False)
    owner_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    lead_stage_id = Column(
        UUID(as_uuid=False),
        ForeignKey("workflow_stages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    qualification = Column(JSONB, nullable=False, server_default="{}")
    qualification_summary = Column(Text, nullable=True)
    created_by_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    respond_workspace_id = Column(
        UUID(as_uuid=False),
        ForeignKey("respond_workspaces.id", ondelete="SET NULL"),
        nullable=True,
    )

    customer = relationship("Customer", back_populates="commercial_leads")
    owner = relationship("User", foreign_keys=[owner_user_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    lead_stage = relationship(
        "WorkflowStage",
        back_populates="leads",
        foreign_keys=[lead_stage_id],
    )
    projects = relationship(
        "CommercialProject",
        back_populates="lead",
        order_by="CommercialProject.created_at",
    )
    notes = relationship(
        "CommercialLeadNote",
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="CommercialLeadNote.created_at.desc()",
    )
    pipeline_tasks = relationship(
        "CommercialTask",
        back_populates="lead",
        cascade="all, delete-orphan",
    )
    respond_workspace = relationship("RespondWorkspace", back_populates="commercial_leads")
    lead_respond_contacts = relationship(
        "CommercialLeadRespondContact",
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="CommercialLeadRespondContact.sort_order",
    )

    __table_args__ = (
        Index("ix_commercial_leads_customer_id", "customer_id"),
        Index("ix_commercial_leads_owner_user_id", "owner_user_id"),
        Index("ix_commercial_leads_lead_stage_id", "lead_stage_id"),
        Index("ix_commercial_leads_respond_workspace_id", "respond_workspace_id"),
    )


class CommercialLeadRespondContact(Base):
    """Links a commercial lead to a respond_contacts row with role and display order."""

    __tablename__ = "commercial_lead_respond_contacts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    lead_id = Column(UUID(as_uuid=False), ForeignKey("commercial_leads.id", ondelete="CASCADE"), nullable=False)
    respond_contact_id = Column(Text, ForeignKey("respond_contacts.id", ondelete="CASCADE"), nullable=False)
    contact_role = Column(String(20), nullable=False)
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    lead = relationship("CommercialLead", back_populates="lead_respond_contacts")
    respond_contact = relationship("RespondContact", back_populates="lead_links")

    __table_args__ = (
        CheckConstraint(
            "contact_role IN ('main', 'stakeholder')",
            name="ck_commercial_lead_respond_contacts_role",
        ),
        UniqueConstraint("lead_id", "respond_contact_id", name="uq_clr_lead_contact"),
        Index("ix_clr_lead_id_sort", "lead_id", "sort_order"),
    )


class CommercialProject(Base):
    __tablename__ = "commercial_projects"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    lead_id = Column(UUID(as_uuid=False), ForeignKey("commercial_leads.id", ondelete="SET NULL"), nullable=True)
    owner_user_id = Column(String(100), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_owner_user_ids = Column(JSONB, nullable=False, server_default="[]")
    developer_customer_id = Column(
        UUID(as_uuid=False),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_stage_id = Column(
        UUID(as_uuid=False),
        ForeignKey("workflow_stages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title = Column(Text, nullable=False)
    brief = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    task_template_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_activity_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_team = Column(JSONB, nullable=False, server_default="[]")
    project_members = Column(JSONB, nullable=False, server_default="[]")
    project_customer_contacts = Column(JSONB, nullable=False, server_default="[]")
    address_line_1 = Column(String(255), nullable=True)
    address_line_2 = Column(String(255), nullable=True)
    postcode = Column(String(32), nullable=True)
    city = Column(String(120), nullable=True)
    state = Column(String(120), nullable=True)
    country = Column(String(120), nullable=True)
    status = Column(String(50), nullable=False, default="active")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    lead = relationship("CommercialLead", back_populates="projects")
    owner = relationship("User", foreign_keys=[owner_user_id])
    developer_customer = relationship("Customer", foreign_keys=[developer_customer_id])
    project_stage = relationship("WorkflowStage", foreign_keys=[project_stage_id])
    project_customers = relationship(
        "CommercialProjectCustomer",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="CommercialProjectCustomer.created_at",
    )
    project_leads = relationship(
        "CommercialProjectLead",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="CommercialProjectLead.created_at",
    )
    tenders = relationship("CommercialTender", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_commercial_projects_lead_id", "lead_id", unique=False),
        Index("ix_commercial_projects_owner_user_id", "owner_user_id"),
        Index("ix_commercial_projects_developer_customer_id", "developer_customer_id"),
    )


class CommercialTender(Base):
    __tablename__ = "commercial_tenders"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(UUID(as_uuid=False), ForeignKey("commercial_projects.id", ondelete="CASCADE"), nullable=False)
    tender_code = Column(String(64), nullable=False, unique=True)
    title = Column(Text, nullable=False)
    forecast_amount = Column(Numeric(18, 2), nullable=True)
    forecast_currency = Column(String(3), nullable=True)
    pipeline_stage = Column(String(80), nullable=True)
    expected_close_on = Column(Date, nullable=True)
    owner_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tender_lifecycle = Column(String(20), nullable=False, default=CommercialTenderLifecycle.OPEN)
    tender_outcome = Column(String(20), nullable=False, default=CommercialTenderOutcome.PENDING)
    closed_at = Column(DateTime(timezone=False), nullable=True)
    winning_master_quotation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_master_quotations.id", ondelete="SET NULL"),
        nullable=True,
    )
    outcome_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    project = relationship("CommercialProject", back_populates="tenders")
    owner = relationship("User", foreign_keys=[owner_user_id])
    winning_master_quotation = relationship(
        "CommercialMasterQuotation",
        foreign_keys=[winning_master_quotation_id],
        post_update=True,
        overlaps="master_quotations",
    )
    milestones = relationship(
        "CommercialTenderMilestone",
        back_populates="tender",
        cascade="all, delete-orphan",
        order_by="CommercialTenderMilestone.sort_order",
    )
    master_quotations = relationship(
        "CommercialMasterQuotation",
        back_populates="tender",
        cascade="all, delete-orphan",
        foreign_keys="[CommercialMasterQuotation.tender_id]",
    )
    pipeline_tasks = relationship(
        "CommercialTask",
        back_populates="tender",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "tender_lifecycle IN ('open', 'closed')",
            name="ck_commercial_tenders_tender_lifecycle",
        ),
        CheckConstraint(
            "tender_outcome IN ('pending', 'won', 'lost', 'withdrawn', 'no_award')",
            name="ck_commercial_tenders_tender_outcome",
        ),
        Index("ix_commercial_tenders_project_id", "project_id"),
        Index("ix_commercial_tenders_owner_user_id", "owner_user_id"),
    )


class CommercialTenderMilestone(Base):
    __tablename__ = "commercial_tender_milestones"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    tender_id = Column(UUID(as_uuid=False), ForeignKey("commercial_tenders.id", ondelete="CASCADE"), nullable=False)
    milestone_code = Column(String(64), nullable=False)
    due_on = Column(Date, nullable=True)
    achieved_at = Column(DateTime(timezone=False), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    tender = relationship("CommercialTender", back_populates="milestones")

    __table_args__ = (Index("ix_commercial_tender_milestones_tender_id", "tender_id"),)


class CommercialProjectCustomer(Base):
    __tablename__ = "commercial_project_customers"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id = Column(
        UUID(as_uuid=False),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    project = relationship("CommercialProject", back_populates="project_customers")
    customer = relationship("Customer")

    __table_args__ = (
        UniqueConstraint("project_id", "customer_id", name="uq_commercial_project_customers_project_customer"),
        Index("ix_commercial_project_customers_project_id", "project_id"),
        Index("ix_commercial_project_customers_customer_id", "customer_id"),
    )


class CommercialProjectLead(Base):
    __tablename__ = "commercial_project_leads"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    project_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    lead_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    project = relationship("CommercialProject", back_populates="project_leads")
    lead = relationship("CommercialLead")

    __table_args__ = (
        UniqueConstraint("project_id", "lead_id", name="uq_commercial_project_leads_project_lead"),
        Index("ix_commercial_project_leads_project_id", "project_id"),
        Index("ix_commercial_project_leads_lead_id", "lead_id"),
    )


class CommercialMasterQuotationActivity(Base):
    """Per–master-quotation execution checklist (due dates, assignee)."""

    __tablename__ = "commercial_master_quotation_activities"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    master_quotation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_master_quotations.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="open")
    due_at = Column(DateTime(timezone=False), nullable=True)
    assignee_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    completed_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    master_quotation = relationship("CommercialMasterQuotation", back_populates="workspace_activities")
    assignee = relationship("User", foreign_keys=[assignee_user_id])

    __table_args__ = (
        CheckConstraint("status IN ('open', 'done')", name="ck_commercial_mq_activities_status"),
        Index("ix_commercial_mq_activities_master_sort", "master_quotation_id", "sort_order"),
        Index("ix_commercial_mq_activities_assignee_due", "assignee_user_id", "due_at"),
    )


class CommercialMasterQuotation(Base):
    __tablename__ = "commercial_master_quotations"
    __audit_track__ = True
    __audit_entity_type__ = "commercial_master_quotation"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    tender_id = Column(UUID(as_uuid=False), ForeignKey("commercial_tenders.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    quotation_code = Column(String(64), nullable=False)
    title = Column(Text, nullable=False)
    owner_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    quotation_stage_id = Column(
        UUID(as_uuid=False),
        ForeignKey("workflow_stages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quoted_amount = Column(Numeric(18, 2), nullable=True)
    quoted_currency = Column(String(3), nullable=True)
    valid_until = Column(Date, nullable=True)
    payment_terms = Column(Text, nullable=True)
    commercial_details = Column(JSONB, nullable=False, server_default="{}")
    pricing_approval_status = Column(String(32), nullable=False, default="not_required")
    pricing_approver_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    pricing_approval_action_at = Column(DateTime(timezone=False), nullable=True)
    pricing_approval_action_by_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    stage_updated_at = Column(DateTime(timezone=False), nullable=True)
    path_role = Column(String(40), nullable=False, default=CommercialMasterQuotationPathRole.OPEN)
    current_working_revision_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_quotation_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    final_selected_revision_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_quotation_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    task_board = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    tender = relationship(
        "CommercialTender",
        back_populates="master_quotations",
        foreign_keys=[tender_id],
    )
    customer = relationship("Customer", foreign_keys=[customer_id])
    owner = relationship("User", foreign_keys=[owner_user_id])
    pricing_approver = relationship("User", foreign_keys=[pricing_approver_user_id])
    pricing_approval_action_by = relationship("User", foreign_keys=[pricing_approval_action_by_user_id])
    quotation_stage = relationship(
        "WorkflowStage",
        back_populates="master_quotations",
        foreign_keys=[quotation_stage_id],
    )
    workspace_activities = relationship(
        "CommercialMasterQuotationActivity",
        back_populates="master_quotation",
        cascade="all, delete-orphan",
        order_by="CommercialMasterQuotationActivity.sort_order",
    )
    revisions = relationship(
        "CommercialQuotationRevision",
        back_populates="master_quotation",
        cascade="all, delete-orphan",
        order_by="CommercialQuotationRevision.revision_number",
        foreign_keys="[CommercialQuotationRevision.master_quotation_id]",
    )
    current_working_revision = relationship(
        "CommercialQuotationRevision",
        foreign_keys=[current_working_revision_id],
        post_update=True,
    )
    final_selected_revision = relationship(
        "CommercialQuotationRevision",
        foreign_keys=[final_selected_revision_id],
        post_update=True,
    )
    sales_orders = relationship("CommercialSalesOrder", back_populates="master_quotation")
    activity_tasks = relationship(
        "CommercialQuotationActivityTask",
        back_populates="master_quotation",
        cascade="all, delete-orphan",
        order_by="CommercialQuotationActivityTask.sort_order",
    )
    activity_plan_applications = relationship(
        "CommercialActivityPlanApplication",
        back_populates="master_quotation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "path_role IN ('open', 'winner', 'closed_superseded', 'closed_unawarded')",
            name="ck_commercial_master_quotations_path_role",
        ),
        UniqueConstraint("tender_id", "quotation_code", name="uq_commercial_master_quotations_tender_code"),
        Index("ix_commercial_master_quotations_tender_id", "tender_id"),
        Index("ix_commercial_master_quotations_customer_id", "customer_id"),
        Index("ix_commercial_master_quotations_owner", "owner_user_id"),
        Index("ix_commercial_master_quotations_stage", "quotation_stage_id"),
        Index("ix_commercial_master_quotations_current_working_revision_id", "current_working_revision_id"),
        Index("ix_commercial_master_quotations_final_selected_revision_id", "final_selected_revision_id"),
    )


class CommercialQuotationRevision(Base):
    __tablename__ = "commercial_quotation_revisions"
    __audit_track__ = True
    __audit_entity_type__ = "commercial_quotation_revision"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    master_quotation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_master_quotations.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_number = Column(Integer, nullable=False)
    pricing_snapshot = Column(JSONB, nullable=False, server_default="{}")
    revision_notes = Column(Text, nullable=True)
    superseded_at = Column(DateTime(timezone=False), nullable=True)
    final_selected_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    master_quotation = relationship(
        "CommercialMasterQuotation",
        back_populates="revisions",
        foreign_keys=[master_quotation_id],
    )
    sales_order = relationship("CommercialSalesOrder", back_populates="quotation_revision", uselist=False)

    __table_args__ = (
        UniqueConstraint("master_quotation_id", "revision_number", name="uq_commercial_quotation_revisions_master_rev"),
        Index("ix_commercial_quotation_revisions_master_id", "master_quotation_id"),
    )


class CommercialSalesOrder(Base):
    __tablename__ = "commercial_sales_orders"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    quotation_revision_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_quotation_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    master_quotation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_master_quotations.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    tender_id = Column(
        UUID(as_uuid=False),
        ForeignKey("commercial_tenders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sales_order_number = Column(String(100), nullable=False, unique=True)
    status = Column(String(32), nullable=False, default=CommercialSalesOrderStatus.DRAFT)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    quotation_revision = relationship("CommercialQuotationRevision", back_populates="sales_order")
    master_quotation = relationship("CommercialMasterQuotation", back_populates="sales_orders")
    tender = relationship("CommercialTender", backref="commercial_sales_orders")

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'void', 'cancelled')",
            name="ck_commercial_sales_orders_status",
        ),
        Index("ix_commercial_sales_orders_tender_id", "tender_id"),
        Index("ix_commercial_sales_orders_master_quotation_id", "master_quotation_id"),
    )
