"""Commercial CRM schemas (leads, stages, conversion)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --- Lead stages ---


class CommercialLeadStageBase(BaseModel):
    stage_code: str = Field(..., max_length=50)
    stage_name: str = Field(..., max_length=100)
    sort_order: int = 0
    is_terminal: bool = False
    allows_conversion: bool = False


class CommercialLeadStageCreate(CommercialLeadStageBase):
    pass


class CommercialLeadStageUpdate(BaseModel):
    stage_name: Optional[str] = Field(None, max_length=100)
    sort_order: Optional[int] = None
    is_terminal: Optional[bool] = None
    allows_conversion: Optional[bool] = None
    can_go_back: Optional[bool] = None
    is_active: Optional[bool] = None
    is_cancelled: Optional[bool] = None


class CommercialLeadStageResponse(CommercialLeadStageBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime
    can_go_back: bool = False
    is_active: bool = True
    is_cancelled: bool = False


def commercial_lead_stage_response_from_workflow(row: Any) -> CommercialLeadStageResponse:
    """Map WorkflowStage (domain=lead) to legacy API shape."""
    return CommercialLeadStageResponse(
        id=str(row.id),
        stage_code=row.code,
        stage_name=row.label,
        sort_order=row.sort_order,
        is_terminal=bool(row.is_terminal),
        allows_conversion=bool(row.allows_conversion) if row.allows_conversion is not None else False,
        created_at=row.created_at,
        updated_at=row.updated_at,
        can_go_back=bool(getattr(row, "can_go_back", False)),
        is_active=bool(getattr(row, "is_active", True)),
        is_cancelled=bool(getattr(row, "is_cancelled", False)),
    )


# --- Leads ---


class CommercialLeadCreate(BaseModel):
    customer_id: str
    title: str = Field(..., min_length=1)
    owner_user_id: str
    lead_code: Optional[str] = Field(None, max_length=64)
    lead_stage_id: Optional[str] = None
    respond_workspace_id: Optional[str] = None
    qualification: Optional[Dict[str, Any]] = None
    qualification_summary: Optional[str] = None


class CommercialLeadUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    owner_user_id: Optional[str] = None
    lead_stage_id: Optional[str] = None
    respond_workspace_id: Optional[str] = None
    qualification: Optional[Dict[str, Any]] = None
    qualification_summary: Optional[str] = None


class CommercialLeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lead_code: str
    title: str
    customer_id: str
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_name: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_by_name: Optional[str] = None
    lead_stage_id: str
    stage_code: Optional[str] = None
    stage_name: Optional[str] = None
    allows_conversion: bool = False
    is_terminal: bool = False
    qualification: Dict[str, Any] = Field(default_factory=dict)
    qualification_summary: Optional[str] = None
    respond_workspace_id: Optional[str] = None
    has_project: bool = False
    project_id: Optional[str] = None
    lead_project_count: int = 0
    created_at: datetime
    updated_at: datetime


class LeadRelatedProjectRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime


class LeadRelatedQuotationRow(BaseModel):
    project_title: str
    tender_code: str
    quotation_code: str
    title: str
    path_role: str
    stage_name: Optional[str] = None


class LeadRelatedSalesOrderRow(BaseModel):
    sales_order_number: str
    status: str
    tender_code: str
    quotation_code: str


class LeadRelatedResponse(BaseModel):
    projects: List[LeadRelatedProjectRow]
    quotations: List[LeadRelatedQuotationRow]
    sales_orders: List[LeadRelatedSalesOrderRow]


# --- Notes ---


class CommercialLeadNoteCreate(BaseModel):
    body: str


class CommercialLeadNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lead_id: str
    body: str
    created_by_user_id: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: datetime


# --- Convert ---


class CommercialLeadConvertRequest(BaseModel):
    project_title: str = Field(..., max_length=255)
    tender_title: str = Field(..., max_length=255)
    tender_code: Optional[str] = Field(None, max_length=64)
    forecast_amount: Optional[Decimal] = None
    forecast_currency: Optional[str] = Field(None, max_length=3)
    pipeline_stage: Optional[str] = Field(None, max_length=80)
    expected_close_on: Optional[str] = None


class CommercialLeadConvertResponse(BaseModel):
    lead_id: str
    project_id: str
    tender_id: str
    tender_code: str


# --- Projects ---


class CommercialProjectMemberPatch(BaseModel):
    name: str = Field(..., max_length=255)
    tags: List[str] = Field(default_factory=list)


class CommercialProjectCustomerContactPatch(BaseModel):
    id: Optional[str] = None
    name: str = ""
    phone: Optional[str] = None
    email: Optional[str] = None


class CommercialProjectCreate(BaseModel):
    lead_id: Optional[str] = None
    title: str = Field(..., min_length=1)
    brief: Optional[str] = None
    notes: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    task_template_id: Optional[str] = None
    status: Optional[str] = Field(None, max_length=50)
    project_stage_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    project_owner_user_ids: Optional[List[str]] = None
    developer_customer_id: str
    customer_ids: Optional[List[str]] = None
    address_line_1: Optional[str] = Field(None, max_length=255)
    address_line_2: Optional[str] = Field(None, max_length=255)
    postcode: Optional[str] = Field(None, max_length=32)
    city: Optional[str] = Field(None, max_length=120)
    state: Optional[str] = Field(None, max_length=120)
    country: Optional[str] = Field(None, max_length=120)
    project_customer_contacts: Optional[List[CommercialProjectCustomerContactPatch]] = None


class CommercialProjectUpdate(BaseModel):
    lead_id: Optional[str] = None
    title: Optional[str] = Field(None, min_length=1)
    brief: Optional[str] = None
    notes: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    task_template_id: Optional[str] = None
    task_board: Optional[Dict[str, Any]] = None
    status: Optional[str] = Field(None, max_length=50)
    project_stage_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    project_owner_user_ids: Optional[List[str]] = None
    developer_customer_id: Optional[str] = None
    customer_ids: Optional[List[str]] = None
    address_line_1: Optional[str] = Field(None, max_length=255)
    address_line_2: Optional[str] = Field(None, max_length=255)
    postcode: Optional[str] = Field(None, max_length=32)
    city: Optional[str] = Field(None, max_length=120)
    state: Optional[str] = Field(None, max_length=120)
    country: Optional[str] = Field(None, max_length=120)
    project_members: Optional[List[CommercialProjectMemberPatch]] = None
    project_customer_contacts: Optional[List[CommercialProjectCustomerContactPatch]] = None

    @field_validator("project_owner_user_ids", mode="before")
    @classmethod
    def coerce_owner_ids(cls, v: Any) -> Any:
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("project_owner_user_ids must be a list")
        out: List[str] = []
        for item in v:
            if item is None:
                continue
            txt = str(item).strip()
            if txt:
                out.append(txt)
        return out


class CommercialProjectMemberOut(BaseModel):
    name: str
    tags: List[str] = Field(default_factory=list)


class CommercialProjectCustomerContactOut(BaseModel):
    id: Optional[str] = None
    name: str = ""
    phone: Optional[str] = None
    email: Optional[str] = None


class CommercialProjectStageSummary(BaseModel):
    id: str
    code: str
    label: str
    sort_order: int = 0
    is_terminal: bool = False
    can_go_back: bool = False


class CommercialProjectSelectRow(BaseModel):
    id: str
    title: str
    lead_code: str


class CommercialProjectListRow(BaseModel):
    id: str
    title: str
    brief: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str
    project_stage_id: str
    project_stage_code: Optional[str] = None
    project_stage_name: Optional[str] = None
    lead_id: str
    lead_code: str
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None
    customer_ids: List[str] = Field(default_factory=list)
    project_lead_count: int = 0
    project_leads: List[Dict[str, Optional[str]]] = Field(default_factory=list)
    lead_project_count: int = 0
    owner_user_id: str
    owner_user_ids: List[str] = Field(default_factory=list)
    owner_name: Optional[str] = None
    owner_names: List[str] = Field(default_factory=list)
    developer_customer_id: str
    developer_customer_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CommercialProjectTenderSummary(BaseModel):
    id: str
    tender_code: str
    title: str
    forecast_amount: Optional[Decimal] = None
    forecast_currency: Optional[str] = None
    pipeline_stage: Optional[str] = None
    expected_close_on: Optional[str] = None
    master_quotation_count: int = 0


class CommercialProjectDocumentRow(BaseModel):
    id: str
    name: str
    size_bytes: Optional[int] = None
    uploaded_by: Optional[str] = None
    uploaded_at: datetime
    file_path: str


class CommercialProjectTaskTemplateRow(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    version_number: int = 1
    template_scope: str = "project"


class CommercialProjectCustomerRow(BaseModel):
    id: str
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None


class CommercialProjectLeadRow(BaseModel):
    id: str
    lead_code: Optional[str] = None
    lead_title: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None


class CommercialProjectDetail(BaseModel):
    id: str
    title: str
    brief: Optional[str] = None
    notes: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    postcode: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    task_template_id: Optional[str] = None
    task_board: Dict[str, Any] = Field(default_factory=dict)
    status: str
    project_stage_id: str
    project_stage: Optional[CommercialProjectStageSummary] = None
    owner_user_id: str
    owner_user_ids: List[str] = Field(default_factory=list)
    owner_name: Optional[str] = None
    owner_names: List[str] = Field(default_factory=list)
    project_members: List[CommercialProjectMemberOut] = Field(default_factory=list)
    developer_customer_id: str
    developer_customer_name: Optional[str] = None
    project_customer_contacts: List[CommercialProjectCustomerContactOut] = Field(default_factory=list)
    lead_id: str
    lead_code: str
    lead_title: str
    lead_stage_code: Optional[str] = None
    lead_stage_name: Optional[str] = None
    lead_project_count: int = 0
    customer_id: Optional[str] = None
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None
    customer_ids: List[str] = Field(default_factory=list)
    project_customers: List[CommercialProjectCustomerRow] = Field(default_factory=list)
    project_leads: List[CommercialProjectLeadRow] = Field(default_factory=list)
    tenders: List[CommercialProjectTenderSummary] = Field(default_factory=list)
    tender_count: int = 0
    forecast_by_currency: Dict[str, str] = Field(default_factory=dict)
    quotation_execution_state_counts: Dict[str, int] = Field(default_factory=dict)
    # Master quotation totals by workflow stage terminal flag (quoted_amount on master quotation)
    open_quotation_amount_by_currency: Dict[str, str] = Field(
        default_factory=dict,
        description="Sum of quoted amounts for quotations not in a terminal workflow stage",
    )
    sales_order_amount_by_currency: Dict[str, str] = Field(
        default_factory=dict,
        description="Sum of quoted amounts for quotations in a terminal workflow stage (final)",
    )
    documents: List[CommercialProjectDocumentRow] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class TaskScheduleImpactRow(BaseModel):
    task_id: str
    title: str
    old_start_date: Optional[str] = None
    old_end_date: Optional[str] = None
    new_start_date: Optional[str] = None
    new_end_date: Optional[str] = None


class TaskBoardSchedulePreviewRequest(BaseModel):
    task_board: Dict[str, Any] = Field(default_factory=dict)
    baseline_start_date: Optional[str] = None
    changed_task_id: Optional[str] = None


class TaskBoardSchedulePreviewResponse(BaseModel):
    task_board: Dict[str, Any] = Field(default_factory=dict)
    impacts: List[TaskScheduleImpactRow] = Field(default_factory=list)


# --- Tenders ---


class CommercialTenderStageSelectRow(BaseModel):
    stage_code: str
    stage_name: str
    sort_order: int
    is_terminal: bool


class CommercialTenderCreate(BaseModel):
    project_id: str
    tender_code: str = Field(..., max_length=64)
    title: str = Field(..., min_length=1)
    owner_user_id: Optional[str] = None
    forecast_amount: Optional[Decimal] = None
    forecast_currency: Optional[str] = Field(None, max_length=3)
    pipeline_stage: Optional[str] = Field(None, max_length=80)
    expected_close_on: Optional[str] = None


class CommercialTenderUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    owner_user_id: Optional[str] = None
    forecast_amount: Optional[Decimal] = None
    forecast_currency: Optional[str] = Field(None, max_length=3)
    pipeline_stage: Optional[str] = Field(None, max_length=80)
    expected_close_on: Optional[str] = None


class CommercialTenderListRow(BaseModel):
    tender_code: str
    title: str
    project_id: str
    owner_name: Optional[str] = None
    forecast_amount: Optional[Decimal] = None
    forecast_currency: Optional[str] = None
    pipeline_stage: Optional[str] = None
    expected_close_on: Optional[str] = None
    tender_lifecycle: str
    tender_outcome: str
    closed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class CommercialTenderDetail(CommercialTenderListRow):
    outcome_notes: Optional[str] = None


class CommercialTenderCloseRequest(BaseModel):
    """Close outcome: won, lost, cancelled (stored as withdrawn), no_bid (stored as no_award)."""

    outcome: str = Field(..., description="won | lost | cancelled | no_bid | withdrawn | no_award")
    winning_master_quotation_id: Optional[str] = None
    outcome_notes: Optional[str] = None


class CommercialTenderSummaryResponse(BaseModel):
    tender_code: str
    title: str
    tender_lifecycle: str
    tender_outcome: str
    pipeline_value_amount: Optional[str] = None
    pipeline_value_currency: Optional[str] = None
    in_open_pipeline: bool
    milestone_total: int
    milestone_achieved: int
    master_quotation_count: int
    master_quotation_path_roles: Dict[str, int] = Field(default_factory=dict)
    master_quotation_stage_id_counts: Dict[str, int] = Field(default_factory=dict)


class CommercialTenderMilestoneCreate(BaseModel):
    milestone_code: str = Field(..., max_length=64)
    due_on: Optional[str] = None
    sort_order: int = 0


class CommercialTenderMilestoneUpdate(BaseModel):
    milestone_code: Optional[str] = Field(None, max_length=64)
    due_on: Optional[str] = None
    achieved_at: Optional[datetime] = None
    sort_order: Optional[int] = None


class CommercialTenderMilestoneResponse(BaseModel):
    id: str
    tender_id: str
    milestone_code: str
    due_on: Optional[str] = None
    achieved_at: Optional[datetime] = None
    sort_order: int
    created_at: datetime


class CommercialMasterQuotationListRow(BaseModel):
    id: str
    quotation_code: str
    title: str
    path_role: str
    quotation_stage_id: str
    quoted_amount: Optional[Decimal] = None
    quoted_currency: Optional[str] = None
