"""Project Sales schemas.

No UUID is ever the user-facing identifier of a project: ``project_code`` is, and
every response that names a project carries it. Party and owner FKs are echoed back
with resolved names for the same reason (the FE cursor rule bans UUIDs in the UI).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------- parties


class ProjectPartyBase(BaseModel):
    party_type: str = Field(
        ...,
        description=(
            "developer | architect | main_contractor | trading_house | consultant"
        ),
    )
    name: str = Field(..., min_length=1, max_length=255)
    registration_no: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=150)
    notes: Optional[str] = None
    customer_id: Optional[str] = Field(
        None,
        description=(
            "Set only once this party actually issues a purchase order. Architects "
            "never buy, which is why parties are not customers."
        ),
    )
    is_active: bool = True


class ProjectPartyCreate(ProjectPartyBase):
    pass


class ProjectPartyUpdate(BaseModel):
    party_type: Optional[str] = None
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    registration_no: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=150)
    notes: Optional[str] = None
    customer_id: Optional[str] = None
    is_active: Optional[bool] = None


class ProjectPartyResponse(ProjectPartyBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_name: Optional[str] = None
    project_count: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ------------------------------------------------------------ types, templates


class ProjectTypeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    code: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None
    derives_delivery_from_launch: bool = Field(
        False,
        description=(
            "Property developments infer delivery from launch date plus a configurable "
            "lag. Every other type states an explicit delivery window instead."
        ),
    )
    sort_order: int = 0
    is_active: bool = True


class ProjectTypeCreate(ProjectTypeBase):
    pass


class ProjectTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    code: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = None
    derives_delivery_from_launch: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ProjectTypeResponse(ProjectTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    template_count: Optional[int] = None


class ProjectTemplateRoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    sort_order: int
    is_active: bool


class ProjectTemplateBase(BaseModel):
    type_id: str
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    is_active: bool = True


class ProjectTemplateCreate(ProjectTemplateBase):
    role_names: List[str] = Field(
        default_factory=list,
        description=(
            "Stakeholder roles this template offers. Seeded default: Decision Maker, "
            "Influencer, Info Provider, Architect."
        ),
    )


class ProjectTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    role_names: Optional[List[str]] = None


class ProjectTemplateResponse(ProjectTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type_name: Optional[str] = None
    roles: List[ProjectTemplateRoleResponse] = Field(default_factory=list)
    has_forked_status_graph: bool = False


# ------------------------------------------------------------------- clashes


class ClashCandidateResponse(BaseModel):
    """One possible duplicate, with everything the user needs to decide.

    AC-C6a: the incumbent is rendered, not merely named. Owner, status and last
    activity are what let someone tell "that is my colleague's live tender" from
    "that is a different phase with a similar name".
    """

    project_id: str
    project_code: str
    title: str
    outcome: str
    status_label: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_name: Optional[str] = None
    developer_name: Optional[str] = None
    estimated_sales_value: Optional[Decimal] = None
    brands: List[str] = Field(default_factory=list)
    last_activity_at: Optional[datetime] = None
    similarity: float
    blocks: bool


class ClashPreviewRequest(BaseModel):
    developer_party_id: Optional[str] = None
    title: str = Field(..., min_length=1)


class ClashPreviewResponse(BaseModel):
    candidates: List[ClashCandidateResponse] = Field(default_factory=list)
    would_block: bool = False


# ------------------------------------------------------------------- projects


class ProjectRegisterRequest(BaseModel):
    """AC-C3. Only title is structurally required.

    Everything else is knowable later and demanding it up front is how a
    registration screen becomes something people avoid until they have "all the
    details", which is exactly when the duplicate gets created.
    """

    title: str = Field(..., min_length=1)
    developer_party_id: Optional[str] = None
    type_id: Optional[str] = None
    template_id: Optional[str] = None
    owner_user_id: Optional[str] = Field(
        None, description="Defaults to the caller. Reassigning needs projects.manage."
    )

    registered_company_name: Optional[str] = None
    location: Optional[str] = None
    address: Optional[str] = None
    architect_party_id: Optional[str] = None
    main_contractor_party_id: Optional[str] = None
    estimated_sales_value: Optional[Decimal] = Field(None, ge=0)
    launch_date: Optional[date] = None
    expected_delivery_from: Optional[date] = None
    expected_delivery_to: Optional[date] = None
    brand_ids: List[str] = Field(default_factory=list)


class ProjectUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    developer_party_id: Optional[str] = None
    type_id: Optional[str] = None
    template_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    loss_reason: Optional[str] = None

    registered_company_name: Optional[str] = None
    location: Optional[str] = None
    address: Optional[str] = None
    architect_party_id: Optional[str] = None
    main_contractor_party_id: Optional[str] = None
    estimated_sales_value: Optional[Decimal] = Field(None, ge=0)
    launch_date: Optional[date] = None
    expected_delivery_from: Optional[date] = None
    expected_delivery_to: Optional[date] = None
    brand_ids: Optional[List[str]] = None

    # AC-G7: critical is a flag settable at any status, never a funnel rung.
    is_critical: Optional[bool] = None
    management_support: Optional[str] = None
    management_notes: Optional[str] = None


class ProjectStatusChangeRequest(BaseModel):
    to_status_id: str
    note: Optional[str] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_code: str
    title: str
    outcome: str
    loss_reason: Optional[str] = None

    developer_party_id: Optional[str] = None
    developer_name: Optional[str] = None
    type_id: Optional[str] = None
    type_name: Optional[str] = None
    template_id: Optional[str] = None
    template_name: Optional[str] = None

    # Provenance (AC-O10). All null on a project registered directly, which the detail
    # page renders as "registered directly" rather than as an empty section.
    lead_id: Optional[str] = None
    lead_code: Optional[str] = None
    lead_source: Optional[str] = None
    lead_created_at: Optional[datetime] = None
    lead_owner_user_id: Optional[str] = None

    status_id: Optional[str] = None
    status_key: Optional[str] = None
    status_label: Optional[str] = None

    owner_user_id: Optional[str] = None
    owner_name: Optional[str] = None

    is_critical: bool = False
    critical_at: Optional[datetime] = None
    management_support: Optional[str] = None
    management_notes: Optional[str] = None

    registered_company_name: Optional[str] = None
    location: Optional[str] = None
    address: Optional[str] = None
    architect_party_id: Optional[str] = None
    architect_name: Optional[str] = None
    main_contractor_party_id: Optional[str] = None
    main_contractor_name: Optional[str] = None
    estimated_sales_value: Optional[Decimal] = None
    launch_date: Optional[date] = None
    expected_delivery_from: Optional[date] = None
    expected_delivery_to: Optional[date] = None
    brands: List[str] = Field(default_factory=list)
    brand_ids: List[str] = Field(default_factory=list)

    last_meaningful_activity_at: Optional[datetime] = None
    days_since_last_activity: Optional[int] = None
    # DERIVED from the earliest open task, never stored (AC-N6). Absent rather than
    # null-dated when there is no open work at all: "nothing planned" and "planned with
    # no date" are different states and the worklist treats them differently.
    next_action_date: Optional[date] = None
    next_action_overdue: bool = False
    open_task_count: int = 0
    can_edit: bool = False

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --------------------------------------------------------------- stakeholders


class ProjectStakeholderBase(BaseModel):
    person_name: str = Field(..., min_length=1, max_length=255)
    role_id: Optional[str] = Field(
        None,
        description=(
            "A role from the project's template. The role belongs to the pairing, not "
            "the person: the same QS is a decision maker on one tender and an "
            "influencer on the next."
        ),
    )
    party_id: Optional[str] = None
    job_title: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=150)
    influence: Optional[str] = Field(None, description="high | medium | low")
    is_primary: bool = False
    notes: Optional[str] = None


class ProjectStakeholderCreate(ProjectStakeholderBase):
    pass


class ProjectStakeholderUpdate(BaseModel):
    person_name: Optional[str] = Field(None, min_length=1, max_length=255)
    role_id: Optional[str] = None
    party_id: Optional[str] = None
    job_title: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=150)
    influence: Optional[str] = None
    is_primary: Optional[bool] = None
    notes: Optional[str] = None


class ProjectStakeholderResponse(ProjectStakeholderBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    role_name: Optional[str] = None
    party_name: Optional[str] = None


# ------------------------------------------------- collaborators / takeovers


class TakeoverRequestCreate(BaseModel):
    kind: str = Field(..., description="join | dispute")
    reason: str = Field(
        ...,
        min_length=1,
        description=(
            "Mandatory (AC-C7). A takeover with no stated reason gives the manager "
            "nothing to decide on."
        ),
    )


class TakeoverRequestDecision(BaseModel):
    approve: bool
    decision_note: Optional[str] = None


class TakeoverRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    project_code: Optional[str] = None
    project_title: Optional[str] = None
    kind: str
    reason: str
    status: str
    requester_user_id: str
    requester_name: Optional[str] = None
    decided_by: Optional[str] = None
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    created_at: Optional[datetime] = None


class ProjectCollaboratorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    user_id: str
    user_name: Optional[str] = None
    granted_by: Optional[str] = None
    granted_at: Optional[datetime] = None


# ---------------------------------------------------------------------- tasks


class ProjectTemplateTaskBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    task_phase: str = Field(
        "pursuit",
        description=(
            "pursuit = the sales work needed to win; delivery = post-win execution. "
            "A separate axis from category, which is the work-stream."
        ),
    )
    category: Optional[str] = Field(
        None,
        max_length=120,
        description="Work-stream label, free-form per template (Spec-in, Sampling, ...)",
    )
    sort_order: int = 0
    default_offset_days: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "Days after registration this task is due. Null means no due date, which "
            "is honest for work whose timing depends on events rather than elapsed days."
        ),
    )
    is_active: bool = True


class ProjectTemplateTaskCreate(ProjectTemplateTaskBase):
    pass


class ProjectTemplateTaskUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    task_phase: Optional[str] = None
    category: Optional[str] = Field(None, max_length=120)
    sort_order: Optional[int] = None
    default_offset_days: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class ProjectTemplateTaskResponse(ProjectTemplateTaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    template_id: str
    # How many live project tasks came from this item. Non-zero means delete is
    # blocked and deactivate is the action (AC-N11), so the UI can say why up front.
    in_use_count: int = 0


class ProjectTaskBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    task_phase: str = "pursuit"
    category: Optional[str] = Field(None, max_length=120)
    assignee_user_id: Optional[str] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    sort_order: int = 0
    linked_entity_type: Optional[str] = Field(
        None, description="quotation_version | sample | purchase_order"
    )
    linked_entity_id: Optional[str] = None


class ProjectTaskCreate(ProjectTaskBase):
    status_id: Optional[str] = Field(
        None, description="Defaults to the task graph's initial status."
    )


class ProjectTaskUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    task_phase: Optional[str] = None
    category: Optional[str] = Field(None, max_length=120)
    assignee_user_id: Optional[str] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    sort_order: Optional[int] = None
    linked_entity_type: Optional[str] = None
    linked_entity_id: Optional[str] = None


class ProjectTaskStatusChangeRequest(BaseModel):
    """Escalate and Stuck carry their context in the SAME request as the move.

    Two calls would leave a window where the task is escalated to nobody, and a client
    that crashed between them would leave it there permanently.
    """

    to_status_id: str
    escalated_to_user_id: Optional[str] = Field(
        None, description="Required when moving to a status keyed `escalate`."
    )
    stuck_reason: Optional[str] = Field(
        None, description="Required when moving to a status keyed `stuck`."
    )


class ProjectTaskResponse(ProjectTaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    project_code: Optional[str] = None
    project_title: Optional[str] = None

    status_id: Optional[str] = None
    status_key: Optional[str] = None
    status_label: Optional[str] = None
    is_open: bool = True

    assignee_name: Optional[str] = None
    escalated_to_user_id: Optional[str] = None
    escalated_to_name: Optional[str] = None
    stuck_reason: Optional[str] = None

    completed_at: Optional[datetime] = None
    is_overdue: bool = False
    days_until_due: Optional[int] = None
    source_template_task_id: Optional[str] = None
    can_edit: bool = False

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectTaskHistoryEntry(BaseModel):
    """One change to a task, from the existing audit listeners (AC-N7).

    No dedicated history table: the audit trail already captures per-field diffs, and a
    second store would drift from it.
    """

    at: datetime
    actor_name: Optional[str] = None
    action: str
    field: Optional[str] = None
    from_value: Optional[str] = None
    to_value: Optional[str] = None


# ----------------------------------------------------------------- S2c leads


class ProjectLeadBase(BaseModel):
    title: str = Field(min_length=1)
    customer_id: str = Field(description="Required (AC-O1): somebody told us about it.")
    developer_party_id: Optional[str] = Field(
        None, description="Often unknown at sighting time."
    )
    source: Optional[str] = None
    source_detail: Optional[str] = None
    estimated_value: Optional[Decimal] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    owner_user_id: Optional[str] = None


class ProjectLeadNewCustomer(BaseModel):
    """Create a customer for an organisation that has never bought anything.

    Rows created this way carry ``source='project_lead'`` so order and invoice pickers
    can filter prospects out if the noise becomes real.
    """

    customer_name: str = Field(min_length=1, max_length=255)
    customer_code: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=150)
    phone_number: Optional[str] = Field(None, max_length=50)
    registration_number: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class ProjectLeadCreate(ProjectLeadBase):
    customer_id: Optional[str] = Field(
        None, description="Omit only when supplying `new_customer` instead."
    )
    new_customer: Optional[ProjectLeadNewCustomer] = Field(
        None,
        description=(
            "Step 1 of the wizard when the informant is not yet a customer. Ignored "
            "when `customer_id` is given."
        ),
    )


class ProjectLeadUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    customer_id: Optional[str] = None
    developer_party_id: Optional[str] = None
    source: Optional[str] = None
    source_detail: Optional[str] = None
    estimated_value: Optional[Decimal] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    owner_user_id: Optional[str] = None


class ProjectLeadDuplicateHint(BaseModel):
    """Informational only (AC-O3). A lead is never blocked by one of these."""

    lead_id: str
    lead_code: str
    owner_name: Optional[str] = None


class ProjectLeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lead_code: str
    title: str

    customer_id: str
    customer_name: Optional[str] = None
    developer_party_id: Optional[str] = None
    developer_name: Optional[str] = None

    source: Optional[str] = None
    source_detail: Optional[str] = None
    estimated_value: Optional[Decimal] = None
    location: Optional[str] = None
    notes: Optional[str] = None

    status_id: Optional[str] = None
    status_key: Optional[str] = None
    status_label: Optional[str] = None
    outcome: str = "open"
    disqualified_reason: Optional[str] = None
    qualified_at: Optional[datetime] = None

    owner_user_id: Optional[str] = None
    owner_name: Optional[str] = None

    project_count: int = 0
    possible_duplicates: List[ProjectLeadDuplicateHint] = Field(default_factory=list)
    can_edit: bool = False

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectLeadStatusChangeRequest(BaseModel):
    to_status_id: str


class ProjectLeadQualifyRequest(BaseModel):
    """The confirm step of the wizard. Every field is optional: the lead already knows
    most of it, and the point of qualify is to avoid re-keying what we were told."""

    title: Optional[str] = Field(
        None, description="Defaults to the lead's title. Split a masterplan here."
    )
    developer_party_id: Optional[str] = None
    type_id: Optional[str] = None
    template_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    brand_ids: Optional[List[str]] = None
    details: Optional[Dict[str, Any]] = Field(
        None, description="Sales-profile fields, same shape as registration."
    )


class ProjectLeadDisqualifyRequest(BaseModel):
    reason: str = Field(
        min_length=1,
        description=(
            "Must be a value from the `project_lead_disqualify_reason` lookup set: a "
            "free-text reason cannot be reported on."
        ),
    )


class ProjectLeadReasonOption(BaseModel):
    value: str
    label: str


class ProjectLeadDisqualifiedReasonCount(ProjectLeadReasonOption):
    count: int


class ProjectLeadConversionMetrics(BaseModel):
    total: int
    open: int
    qualified: int
    disqualified: int
    decided: int
    conversion_rate: Optional[float] = Field(
        None,
        description=(
            "Qualified / decided. Null rather than 0 when nothing is decided yet: zero "
            "would read as 'we convert nothing'."
        ),
    )
    projects_from_leads: int
    disqualified_reasons: List[ProjectLeadDisqualifiedReasonCount] = Field(
        default_factory=list
    )


class CustomerPortfolioResponse(BaseModel):
    """One customer's leads and projects (AC-O9), the account view.

    Both lists always present, empty when there is nothing: the section renders either
    way per the CRUD standard, with an explicit empty state rather than disappearing.
    """

    leads: List[ProjectLeadResponse] = Field(default_factory=list)
    projects: List[ProjectResponse] = Field(default_factory=list)


# ------------------------------------------------------------ S3 quotations


class ProjectSeriesBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    brand_id: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True


class ProjectSeriesCreate(ProjectSeriesBase):
    category_ids: List[str] = Field(
        default_factory=list,
        description=(
            "Nominated categories. A PARENT covers all its descendants, so this is a "
            "short list of groups rather than a list of every SKU."
        ),
    )


class ProjectSeriesUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    brand_id: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    category_ids: Optional[List[str]] = Field(
        None, description="Sent WHOLE, not as a delta."
    )


class ProjectSeriesResponse(ProjectSeriesBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    brand_name: Optional[str] = None
    category_ids: List[str] = Field(default_factory=list)
    category_names: List[str] = Field(default_factory=list)
    covered_category_count: int = Field(
        0,
        description=(
            "Nominated categories plus every descendant -- what the non-standard check "
            "actually compares against."
        ),
    )
    quotation_count: int = 0


class PriceFloorRuleBase(BaseModel):
    mode: str = Field(
        "percent",
        description=(
            "percent = of the product's list price; absolute = a hard amount that "
            "ignores list entirely."
        ),
    )
    value: Decimal
    notes: Optional[str] = None
    is_active: bool = True


class PriceFloorRuleUpsert(PriceFloorRuleBase):
    product_id: Optional[str] = Field(
        None, description="Set for a product-level rule. Mutually exclusive with category_id."
    )
    category_id: Optional[str] = Field(
        None, description="Set for a category-level rule. Covers that category only."
    )


class PriceFloorRuleResponse(PriceFloorRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    level: str = Field(
        description=(
            "Derived from which key is set, never stored: product | category | system."
        )
    )


class ProjectQuotationBase(BaseModel):
    scope_label: str = Field(
        min_length=1, max_length=150, description="e.g. House Units, Common Area, Showroom."
    )
    series_id: Optional[str] = None
    notes: Optional[str] = None


class ProjectQuotationCreate(ProjectQuotationBase):
    pass


class ProjectQuotationUpdate(BaseModel):
    scope_label: Optional[str] = Field(None, min_length=1, max_length=150)
    series_id: Optional[str] = None
    notes: Optional[str] = None


class ProjectQuotationResponse(ProjectQuotationBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    series_name: Optional[str] = None

    outcome: str = "open"
    loss_reason: Optional[str] = None
    loss_reason_label: Optional[str] = None
    decided_at: Optional[datetime] = None

    version_count: int = 0
    # There is no `current_version_id` COLUMN (AC-E3a); this is computed as
    # MAX(version_no) at read time and is safe to render.
    current_version_id: Optional[str] = None
    current_version_no: Optional[int] = None
    current_total: Optional[Decimal] = None

    below_floor_count: int = 0
    non_standard_count: int = 0
    line_count: int = 0

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectQuotationVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    quotation_id: str
    version_no: int
    is_current: bool = Field(
        description="Derived: version_no == MAX(version_no). Everything else is frozen."
    )
    frozen_at: Optional[datetime] = None
    issued_by: Optional[str] = None
    issued_by_name: Optional[str] = None
    issued_on: Optional[date] = None
    total_amount: Decimal = Decimal("0")
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class ProjectQuotationLineBase(BaseModel):
    product_id: Optional[str] = Field(
        None, description="Null for an off-catalog line, which always raises the alert."
    )
    description_snapshot: Optional[str] = Field(
        None, description="Required when there is no product: it is what the customer reads."
    )
    unit_price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("1")
    uom: Optional[str] = None
    unit_type: Optional[str] = Field(
        None, description="house_unit | bathroom | facility | common_area"
    )
    sort_order: int = 0
    notes: Optional[str] = None
    image_attachment_id: Optional[str] = None


class ProjectQuotationLineCreate(ProjectQuotationLineBase):
    pass


class ProjectQuotationLineUpdate(BaseModel):
    product_id: Optional[str] = None
    description_snapshot: Optional[str] = None
    unit_price: Optional[Decimal] = None
    quantity: Optional[Decimal] = None
    uom: Optional[str] = None
    unit_type: Optional[str] = None
    sort_order: Optional[int] = None
    notes: Optional[str] = None
    image_attachment_id: Optional[str] = None


class ProjectQuotationLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version_id: str
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    description: Optional[str] = None
    list_price: Optional[Decimal] = None
    image_attachment_id: Optional[str] = None

    unit_price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("1")
    uom: Optional[str] = None
    unit_type: Optional[str] = None
    line_total: Decimal = Decimal("0")

    is_non_standard: bool = False
    # The floor IN FORCE WHEN PRICED (AC-E7). A later policy change never rewrites it.
    floor_value_applied: Optional[Decimal] = None
    floor_level_applied: Optional[str] = None
    is_below_floor: bool = False

    sort_order: int = 0
    notes: Optional[str] = None


class ProjectQuotationOutcomeRequest(BaseModel):
    outcome: str = Field(description="open | won | lost")
    loss_reason: Optional[str] = Field(
        None,
        description=(
            "Mandatory when outcome is lost, and must be a value from the "
            "`project_quotation_loss_reason` lookup set."
        ),
    )
