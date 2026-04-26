"""Schemas for master quotations and quotation revisions (version control)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class QuotationStageBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage_code: str
    stage_name: str
    is_terminal: bool = False


class MasterQuotationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tender_code: str = ""
    quotation_code: str
    title: str
    lead_id: Optional[str] = None
    lead_code: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    path_role: str
    quotation_stage: Optional[QuotationStageBrief] = None
    current_working_revision_number: Optional[int] = None
    final_selected_revision_number: Optional[int] = None
    quoted_amount: Optional[str] = None
    quoted_currency: Optional[str] = None
    owner_name: Optional[str] = None
    created_at: Optional[datetime] = None


class MasterQuotationTableRow(BaseModel):
    """Flat row for the global quotations list (table UI)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tender_code: str = ""
    quotation_code: str
    title: str
    project_id: str
    project_title: str
    lead_id: str
    lead_code: str
    customer_id: Optional[str] = None
    client_name: Optional[str] = None
    quotation_stage: Optional[QuotationStageBrief] = None
    owner_user_id: Optional[str] = None
    owner_name: Optional[str] = None
    quoted_amount: Optional[str] = None
    quoted_currency: Optional[str] = None
    current_working_revision_number: Optional[int] = None
    created_at: datetime


class MasterQuotationAdvanceBody(BaseModel):
    confirm_tolerance_breach: bool = False


class MasterQuotationDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tender_id: str
    """Commercial project this quotation belongs to (via tender)."""
    project_id: Optional[str] = None
    tender_code: str
    quotation_code: str
    title: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    path_role: str
    quotation_stage: Optional[QuotationStageBrief] = None
    quoted_amount: Optional[Decimal] = None
    quoted_currency: Optional[str] = None
    valid_until: Optional[date] = None
    payment_terms: Optional[str] = None
    description: Optional[str] = None
    remark: Optional[str] = None
    pricing_approval_status: str = "not_required"
    pricing_intended_execution_state: Optional[str] = None
    pricing_approver_user_id: Optional[str] = None
    current_working_revision_id: Optional[str] = None
    final_selected_revision_id: Optional[str] = None
    task_board: Dict[str, Any] = Field(default_factory=dict)
    working_revision_editable: bool = True
    quotation_package_template_id: Optional[str] = None
    quotation_package_template_name: Optional[str] = None
    task_template_id: Optional[str] = None
    task_template_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ProjectMasterQuotationCreate(BaseModel):
    title: str = Field(..., min_length=1)
    valid_until: Optional[date] = None
    description: Optional[str] = Field(None, max_length=4000)
    remark: Optional[str] = Field(None, max_length=4000)
    owner_user_id: Optional[str] = None
    customer_id: Optional[str] = None
    lead_id: Optional[str] = None
    task_template_id: Optional[str] = None
    quotation_package_template_id: Optional[str] = None


class ApplyQuotationPackageTemplateBody(BaseModel):
    quotation_package_template_id: str = Field(..., min_length=1)


class MasterQuotationUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    valid_until: Optional[date] = None
    payment_terms: Optional[str] = None
    owner_user_id: Optional[str] = None
    quoted_amount: Optional[Decimal] = None
    quoted_currency: Optional[str] = Field(None, max_length=3)
    description: Optional[str] = Field(None, max_length=4000)
    remark: Optional[str] = Field(None, max_length=4000)
    task_board: Optional[Dict[str, Any]] = None


class TaskScheduleImpactRow(BaseModel):
    task_id: str
    title: str
    old_start_date: Optional[str] = None
    old_end_date: Optional[str] = None
    new_start_date: Optional[str] = None
    new_end_date: Optional[str] = None


class MasterQuotationTaskBoardSchedulePreviewRequest(BaseModel):
    task_board: Dict[str, Any] = Field(default_factory=dict)
    baseline_start_date: Optional[str] = None
    changed_task_id: Optional[str] = None


class MasterQuotationTaskBoardSchedulePreviewResponse(BaseModel):
    task_board: Dict[str, Any] = Field(default_factory=dict)
    impacts: List[TaskScheduleImpactRow] = Field(default_factory=list)


class QuotationRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    master_quotation_id: str
    revision_number: int
    pricing_snapshot: Dict[str, Any] = Field(default_factory=dict)
    revision_notes: Optional[str] = None
    tolerance_breaches: List[Dict[str, Any]] = Field(default_factory=list)
    pricing_line_hints: List[Dict[str, Any]] = Field(default_factory=list)
    computed_valid_until: Optional[date] = None
    final_selected_at: Optional[datetime] = None
    created_at: datetime
    is_current_working: bool = False
    is_final_selected: bool = False


class QuotationRevisionCreate(BaseModel):
    copy_from_revision_id: Optional[str] = None
    revision_notes: Optional[str] = None
    pricing_snapshot: Optional[Dict[str, Any]] = None


class QuotationRevisionUpdate(BaseModel):
    pricing_snapshot: Optional[Dict[str, Any]] = None
    revision_notes: Optional[str] = None


class SetRevisionPointerBody(BaseModel):
    revision_id: Optional[str] = None


class EntityAttachmentLinkItem(BaseModel):
    id: str
    attachment_id: str
    file_name: Optional[str] = None
    file_path: Optional[str] = None


class LinkAttachmentBody(BaseModel):
    attachment_id: str


class UserBrief(BaseModel):
    user_code: str
    name: Optional[str] = None


class MasterQuotationCompareRow(BaseModel):
    tender_code: str
    quotation_code: str
    title: str
    path_role: str
    quotation_stage: QuotationStageBrief
    owner: Optional[UserBrief] = None
    salesperson_name: Optional[str] = None
    quoted_amount: Optional[Decimal] = None
    quoted_currency: Optional[str] = None
    updated_at: datetime


class PricingApprovalDecision(BaseModel):
    approved: bool
    notes: Optional[str] = None


class WorkspaceActivityOut(BaseModel):
    id: str
    title: str
    body: Optional[str] = None
    status: str
    due_at: Optional[datetime] = None
    assignee: Optional[UserBrief] = None
    sort_order: int
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WorkspaceActivityCreate(BaseModel):
    title: str = Field(..., min_length=1)
    body: Optional[str] = None
    due_at: Optional[datetime] = None
    assignee_user_code: Optional[str] = None
    sort_order: Optional[int] = None


class WorkspaceActivityPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    body: Optional[str] = None
    status: Optional[str] = None
    due_at: Optional[datetime] = None
    assignee_user_code: Optional[str] = None
    sort_order: Optional[int] = None
    completed_at: Optional[datetime] = None


class MasterQuotationAttachmentLinkBody(BaseModel):
    attachment_id: str
