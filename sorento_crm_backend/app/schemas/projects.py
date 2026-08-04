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
    # Project sales admin's filing reference, e.g. PS26-0143. Searchable, and not an
    # identity: it is the string written on every piece of paper for this job, and
    # without it nobody can tie a document back to the file it belongs to.
    admin_ref: Optional[str] = Field(None, max_length=64)

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
    admin_ref: Optional[str] = None

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

    # Staleness ladder, stamped by the daily sweep (AC-H6). 0 fine, 1 owner nudged, 2 owner
    # warned and management copied, 3 Unattended -- at which point colleagues may ASK to take
    # the project over. Nothing here ever changes the owner.
    stale_level: int = 0
    stale_reason: Optional[str] = None
    stale_since: Optional[datetime] = None
    is_unattended: bool = False
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


class ProjectLeadInformant(BaseModel):
    """Who told us (D6, AC-A2). Never a debtor, never written to `customers`.

    Separate from the BUYER because a BCI sighting has no counterparty at all: the
    trading house only exists once a contractor is awarded. Mixed into create and
    update rather than nested, so the wizard posts one flat body.
    """

    informant_source: Optional[str] = Field(
        None,
        max_length=32,
        description=(
            "Reportable bucket: bci | panel | referral | walk_in | consultant | "
            "architect | contractor | other."
        ),
    )
    informant_ref: Optional[str] = Field(
        None, max_length=180, description="Their own reference, e.g. a BCI project id."
    )
    informant_party_id: Optional[str] = Field(
        None, description="A firm on `project_parties`, when the informant has one."
    )
    informant_contact_name: Optional[str] = Field(
        None,
        max_length=180,
        description="A lone informant with no firm on record is normal.",
    )


class ProjectLeadBase(ProjectLeadInformant):
    title: str = Field(min_length=1)
    customer_id: Optional[str] = Field(
        None,
        description=(
            "The BUYER: the debtor who will issue the PO (D6). Nullable, and usually "
            "unknown on day one -- set it when the contractor is awarded."
        ),
    )
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
    new_customer: Optional[ProjectLeadNewCustomer] = Field(
        None,
        description=(
            "Create the BUYER inline when it is already known and not on file. Ignored "
            "when `customer_id` is given, and omitted entirely on a BCI sighting, which "
            "has no buyer yet."
        ),
    )


class ProjectLeadUpdate(ProjectLeadInformant):
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

    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    developer_party_id: Optional[str] = None
    developer_name: Optional[str] = None

    informant_source: Optional[str] = None
    informant_ref: Optional[str] = None
    informant_party_id: Optional[str] = None
    # Resolved from `project_parties` so the screen never has to render the id, per the
    # cursor rule that no UUID reaches the UI.
    informant_party_label: Optional[str] = None
    informant_contact_name: Optional[str] = None

    # The acceptance handshake (D7). `assigned` is not ownership: a lead is only owned
    # once the salesperson accepts it, which is what makes silence measurable.
    acceptance_state: Optional[str] = None
    assigned_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    declined_reason: Optional[str] = None
    declined_at: Optional[datetime] = None

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
    # Diverges from can_edit precisely where it matters: a decline clears the owner and
    # can_edit is owner-or-manager, so whoever raised the lead could otherwise not
    # re-assign the lead that just came back to them.
    can_assign: bool = False

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectLeadStatusChangeRequest(BaseModel):
    to_status_id: str


class ProjectLeadAssignRequest(BaseModel):
    """Hand the lead to a salesperson and start the acceptance clock (AC-A4)."""

    owner_user_id: str = Field(
        min_length=1, description="The salesperson being asked to take it on."
    )
    note: Optional[str] = Field(
        None,
        description=(
            "Context for the assignee, carried in their notification. Not stored on "
            "the lead: the lead's own `notes` belong to the sighting."
        ),
    )


class ProjectLeadDeclineRequest(BaseModel):
    """Refuse an assignment (AC-A5). The reason is free text on purpose.

    Unlike a disqualification, which feeds the conversion report and must come from a
    lookup, this is one salesperson telling marketing why it is not their patch.
    """

    reason: str = Field(min_length=1)


class ProjectLeadAwaitingAcceptanceRow(ProjectLeadResponse):
    """A row of marketing's "who has taken nothing" worklist (AC-A7).

    ``hours_since_assigned`` is computed here so the screen shows the wait without
    doing date maths in the browser, where a naive-UTC timestamp would be read as
    local time and every row would be eight hours out.
    """

    hours_since_assigned: Optional[float] = None


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
    is_issued: bool = Field(
        default=False,
        description="An issue of the parent document went out carrying this version.",
    )
    is_editable: bool = Field(
        default=True,
        description=(
            "Current AND not issued. The flag a screen should gate on: an issued version is "
            "still the highest, so `is_current` alone offers edits the server refuses."
        ),
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

    # The columns the printed quotation carries. Writable from this slice on, so a line can be
    # entered the way it will actually be sent rather than typed twice.
    item_label: Optional[str] = Field(
        None,
        max_length=8,
        description="The A / B / C letter. Blank on a sub-line under the letter above it.",
    )
    brand_snapshot: Optional[str] = Field(None, max_length=100)
    technical_spec: Optional[str] = None
    complete_set: Optional[str] = Field(None, max_length=100)
    band_label: Optional[str] = Field(
        None,
        max_length=150,
        description=(
            "A section heading BEFORE this line, free text off the customer's own bill of "
            "quantities. Carried by the line that opens the band."
        ),
    )
    is_rate_only: bool = Field(
        False,
        description="Quoted at a rate and printed, contributing nothing to any total.",
    )
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
    item_label: Optional[str] = Field(None, max_length=8)
    brand_snapshot: Optional[str] = Field(None, max_length=100)
    technical_spec: Optional[str] = None
    complete_set: Optional[str] = Field(None, max_length=100)
    band_label: Optional[str] = Field(None, max_length=150)
    is_rate_only: Optional[bool] = None


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
    # Quoted at a rate and printed, contributing nothing to any total (AC-C2).
    is_rate_only: bool = False
    item_label: Optional[str] = None
    brand: Optional[str] = None
    technical_spec: Optional[str] = None
    complete_set: Optional[str] = None
    band_label: Optional[str] = None

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


# --------------------------------------------------- S4 samples and customer POs


class ProjectSampleBase(BaseModel):
    quotation_version_id: str = Field(
        description=(
            "The VERSION, never the quotation: 'which price was the developer looking "
            "at when they approved this finish' is what the binding exists to answer."
        )
    )
    submitted_on: Optional[date] = None
    developer_feedback: Optional[str] = None
    salesperson_notes: Optional[str] = None


class ProjectSampleCreate(ProjectSampleBase):
    pass


class ProjectSampleUpdate(BaseModel):
    quotation_version_id: Optional[str] = None
    submitted_on: Optional[date] = None
    developer_feedback: Optional[str] = None
    salesperson_notes: Optional[str] = None


class ProjectSampleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    quotation_version_id: str
    quotation_id: Optional[str] = None
    scope_label: Optional[str] = None
    version_no: Optional[int] = None
    is_version_current: bool = Field(
        True,
        description=(
            "Derived. False means the version was superseded AFTER this sample went "
            "out, which the panel says plainly rather than hiding."
        ),
    )
    submitted_on: Optional[date] = None
    submitted_by: Optional[str] = None
    submitted_by_name: Optional[str] = None
    developer_feedback: Optional[str] = None
    salesperson_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectPurchaseOrderBase(BaseModel):
    po_number: str = Field(min_length=1, max_length=100)
    po_source: str = Field(
        "contractor_direct", description="contractor_direct | trading_house"
    )
    quotation_version_id: Optional[str] = Field(
        None,
        description=(
            "The version the contractor was last shown, which is the only fair thing to "
            "compare the PO against (AC-F9). Null is allowed: a PO can arrive before "
            "anything was formally quoted, and it simply gets no mismatch check."
        ),
    )
    issuing_party_id: Optional[str] = None
    po_date: Optional[date] = None
    po_amount: Optional[Decimal] = None
    notes: Optional[str] = None


class ProjectPurchaseOrderCreate(ProjectPurchaseOrderBase):
    pass


class ProjectPurchaseOrderUpdate(BaseModel):
    po_number: Optional[str] = Field(None, min_length=1, max_length=100)
    po_source: Optional[str] = None
    quotation_version_id: Optional[str] = None
    issuing_party_id: Optional[str] = None
    po_date: Optional[date] = None
    po_amount: Optional[Decimal] = None
    notes: Optional[str] = None


class ProjectPurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    quotation_version_id: Optional[str] = None
    quotation_id: Optional[str] = None
    scope_label: Optional[str] = None
    version_no: Optional[int] = None

    po_source: str = "contractor_direct"
    issuing_party_id: Optional[str] = None
    issuing_party_name: Optional[str] = None
    po_number: str
    po_date: Optional[date] = None
    po_amount: Optional[Decimal] = None
    notes: Optional[str] = None

    line_count: int = 0
    line_total: Decimal = Decimal("0")
    # What still stands between this PO and its sales orders (see the serializer).
    status: Optional[str] = None
    po_confirmed: bool = False
    schedule_confirmed: bool = False
    model_mismatch_count: int = 0
    price_mismatch_count: int = 0

    # AC-F9a: erosion since v1, as a number rather than a flag. A negotiation is
    # SUPPOSED to move the price; management wants the size of the move.
    v1_total: Optional[Decimal] = None
    drift_delta: Optional[Decimal] = None
    drift_percent: Optional[Decimal] = Field(
        None,
        description="Null when v1 priced nothing: a percentage against zero is not a number.",
    )

    # True only on the response to the create that actually moved the funnel (AC-F10).
    status_moved_to_po_received: bool = False

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectPurchaseOrderLineBase(BaseModel):
    product_id: Optional[str] = None
    product_code: Optional[str] = Field(
        None, description="What the PO itself printed, often the contractor's own code."
    )
    description: Optional[str] = None
    unit_price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("1")
    uom: Optional[str] = None
    sort_order: int = 0
    notes: Optional[str] = None


class ProjectPurchaseOrderLineCreate(ProjectPurchaseOrderLineBase):
    pass


class ProjectPurchaseOrderLineUpdate(BaseModel):
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    description: Optional[str] = None
    unit_price: Optional[Decimal] = None
    quantity: Optional[Decimal] = None
    uom: Optional[str] = None
    sort_order: Optional[int] = None
    notes: Optional[str] = None


class ProjectPurchaseOrderLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    po_id: str
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    description: Optional[str] = None
    unit_price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("1")
    uom: Optional[str] = None
    line_total: Decimal = Decimal("0")

    # What the bound version said WHEN THE PO WAS CHECKED (stored, not re-derived).
    quoted_unit_price: Optional[Decimal] = None
    model_mismatch: bool = False
    price_mismatch: bool = False

    sort_order: int = 0
    notes: Optional[str] = None


class ProjectSponsorshipResponse(BaseModel):
    """A sponsorship form linked to this project (AC-F3, AC-F6).

    `project_title` is still carried: it is what the ~28 pre-link rows display, and a
    linked row may still disagree with the free text somebody typed months ago.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    request_number: Optional[str] = None
    request_date: Optional[date] = None
    status: Optional[str] = None
    approval_status: Optional[str] = None
    customer_name: Optional[str] = None
    project_title: Optional[str] = None
    sponsor_subject: Optional[str] = None
    sponsor_subject_other: Optional[str] = None
    total_project_value: Optional[Decimal] = None
    purpose: Optional[str] = None


class SponsorshipYearTotal(BaseModel):
    year: int
    total: Decimal
    form_count: int


class ProjectSponsorshipRollupResponse(BaseModel):
    """AC-F7. Per project AND per year: "what did this development cost us" and "what did
    sponsorship cost us in 2026" are two different management questions."""

    project_id: str
    total: Decimal
    form_count: int
    by_year: List[SponsorshipYearTotal] = Field(default_factory=list)


class SponsorshipConversionResponse(BaseModel):
    """AC-F7's second half. `rate` is null rather than 0 when nothing was sponsored: 0%
    reads as "we sponsor and never win", which is a different and much worse claim."""

    sponsored_projects: int = 0
    converted_projects: int = 0
    rate: Optional[Decimal] = None
    sponsored_spend: Decimal = Decimal("0")


# ------------------------------------------------------- S5a forecast (Group I)


class ForecastYearRow(BaseModel):
    """One delivery year. The three numbers stay in three fields (AC-I2a) so a UI cannot
    stack a speculative figure on top of banked revenue in one column."""

    year: int
    pipeline: Decimal = Decimal("0")
    weighted: Decimal = Decimal("0")
    committed: Decimal = Decimal("0")


class ForecastBandTotals(BaseModel):
    pipeline: Decimal = Decimal("0")
    weighted: Decimal = Decimal("0")
    committed: Decimal = Decimal("0")


class ProjectForecastResponse(BaseModel):
    """AC-I1: three numbers, never blended.

    There is deliberately no `total` field. A single number that mixes a banked PO with a
    10%-probability rumour is the number every spreadsheet produces and nobody can act on,
    and the fastest way to stop it being reported is to not compute it.
    """

    pipeline: Decimal = Decimal("0")
    weighted: Decimal = Decimal("0")
    committed: Decimal = Decimal("0")
    project_count: int = 0
    by_year: List[ForecastYearRow] = Field(default_factory=list)
    undated: ForecastBandTotals = Field(
        default_factory=ForecastBandTotals,
        description=(
            "Projects with no derivable delivery year. Reported rather than dropped: "
            "dropped rows make the buckets disagree with the totals."
        ),
    )


class ConversionResponse(BaseModel):
    won: int = 0
    lost: int = 0
    decided: int = 0
    open: int = 0
    rate: Optional[Decimal] = Field(
        None, description="Null with nothing decided. 0% would claim we lose everything."
    )


class LossReasonCount(BaseModel):
    reason: str
    label: str
    count: int


class SalespersonRow(BaseModel):
    owner_user_id: Optional[str] = None
    owner_name: Optional[str] = None
    project_count: int = 0
    pipeline: Decimal = Decimal("0")
    weighted: Decimal = Decimal("0")
    committed: Decimal = Decimal("0")


class ProjectDashboardResponse(BaseModel):
    """Everything AC-I4 asks for in one read, because the dashboard shows it in one screen
    and four round trips would render it in four stages."""

    forecast: ProjectForecastResponse
    conversion: ConversionResponse
    loss_reasons: List[LossReasonCount] = Field(default_factory=list)
    by_salesperson: List[SalespersonRow] = Field(default_factory=list)
    sponsorship: SponsorshipConversionResponse = Field(
        default_factory=SponsorshipConversionResponse
    )
    delivery_lag_months: int = 30


# ---------------------------------------------------------- quotation documents


class ProjectQuotationDocumentBase(BaseModel):
    your_ref: Optional[str] = None
    doc_date: Optional[date] = None
    attn_name: Optional[str] = None
    subject_title: Optional[str] = None
    cover_letter_html: Optional[str] = None
    terms_html: Optional[str] = None
    signatory_name: Optional[str] = None
    signatory_phone: Optional[str] = None


class ProjectQuotationDocumentCreate(ProjectQuotationDocumentBase):
    """Every field optional on purpose (AC-A2).

    The document arrives already filled in: the reference from the numbering rule, the recipient
    off the project's developer party, the subject from the project title. A create form that
    asked for them would be asking for facts the system already holds.
    """


class ProjectQuotationDocumentUpdate(ProjectQuotationDocumentBase):
    pass


class ProjectQuotationScopeCreate(BaseModel):
    scope_label: str = Field(
        min_length=1, max_length=150, description="e.g. Townhouse, Guard House, Reception."
    )
    series_id: Optional[str] = None
    notes: Optional[str] = None


class ProjectQuotationScopeUpdate(BaseModel):
    scope_label: Optional[str] = Field(default=None, min_length=1, max_length=150)
    sort_order: Optional[int] = None
    notes: Optional[str] = None


class ProjectQuotationScopeSummary(BaseModel):
    """A tab: enough to render it and its total, without its lines."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    scope_label: str
    sort_order: int = 0
    outcome: str = "open"
    current_version_id: Optional[str] = None
    current_version_no: Optional[int] = None
    line_count: int = 0
    # Rate-only lines excluded, so this agrees with the footer under the money column.
    scope_total: Decimal = Decimal("0.00")


class ProjectQuotationIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    issue_no: int
    our_ref_text: Optional[str] = None
    issued_at: Optional[datetime] = None
    issued_by: Optional[str] = None
    issued_by_name: Optional[str] = None
    grand_total: Decimal = Decimal("0.00")
    scope_count: int = 0

    # The customer's acceptance lives on the issue, but the screen watching for it is the
    # document, so it has to travel with the issue history the document reads.
    customer_signature: Optional["QuotationSignatureResponse"] = None
    accepted_at: Optional[datetime] = None
    is_accepted: bool = False


class ProjectQuotationDocumentResponse(ProjectQuotationDocumentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    document_no: str
    # What the customer quotes back: the number plus the revision they hold.
    our_ref: Optional[str] = None

    recipient_party_id: Optional[str] = None
    recipient_name_snapshot: Optional[str] = None
    recipient_address_snapshot: Optional[str] = None
    recipient_phone_snapshot: Optional[str] = None

    scopes: List[ProjectQuotationScopeSummary] = Field(default_factory=list)
    grand_total: Decimal = Decimal("0.00")

    issue_count: int = 0
    current_issue_no: Optional[int] = None
    is_issued: bool = False

    # AC-H1 gates issuing on the signature, so it has to survive a page refresh. Forward-declared
    # because the signature schema is defined further down; resolved by the model_rebuild below.
    signatory_signature: Optional["QuotationSignatureResponse"] = None
    is_signed: bool = False

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ------------------------------------------------ cover letter and terms templates


class QuotationTemplateBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    body_html: str = Field(min_length=1)


class QuotationTemplateCreate(QuotationTemplateBase):
    kind: str = Field(description="cover_letter | terms")
    # Optional because the FIRST template of a kind is active on arrival whatever the caller
    # says: a company holding a template with nothing active renders an empty letter.
    is_active: Optional[bool] = None


class QuotationTemplateUpdate(BaseModel):
    """The wording and the name only.

    `kind` is not editable (a letter that became terms would vanish from the section it was
    written for) and neither is `is_active`: switching the active template is its own act with
    its own route, so one code path deactivates the incumbent.
    """

    name: Optional[str] = Field(default=None, max_length=150)
    body_html: Optional[str] = None


class QuotationTemplateResponse(QuotationTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    is_active: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class QuotationMergeFieldResponse(BaseModel):
    """One entry in the merge-field picker, served from the backend registry.

    The placeholder is built server-side so the token syntax has exactly one definition; a picker
    that assembled "{{" + token itself would be a second one, free to drift.
    """

    token: str
    placeholder: str
    label: str
    example: str


# ------------------------------------------------------------- signing


class QuotationSignatureRequest(BaseModel):
    """One captured signature. Drawn, typed or initialled, all arriving as one PNG data URI."""

    signer_name: Optional[str] = Field(None, max_length=200)
    mode: str = Field("draw", description="draw | type | initials")
    image_data_uri: str = Field(min_length=1)
    gps_lat: Optional[Decimal] = None
    gps_lng: Optional[Decimal] = None


class QuotationSignAcceptRequest(QuotationSignatureRequest):
    pass


class QuotationSignatureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    signer_name: Optional[str] = None
    mode: str = "draw"
    image_data_uri: Optional[str] = None
    signed_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    # Null when the browser refused. The screen shows "-" rather than hiding the field.
    gps_lat: Optional[Decimal] = None
    gps_lng: Optional[Decimal] = None


# Both refer to the signature above by name, so they cannot be built until here.
ProjectQuotationIssueResponse.model_rebuild()
ProjectQuotationDocumentResponse.model_rebuild()


class QuotationSignScopeLine(BaseModel):
    item_label: Optional[str] = None
    description: Optional[str] = None
    technical_spec: Optional[str] = None
    brand: Optional[str] = None
    product_code: Optional[str] = None
    quantity: Decimal = Decimal("0")
    unit_price: Decimal = Decimal("0")
    complete_set: Optional[str] = None
    band_label: Optional[str] = None
    is_rate_only: bool = False
    amount: Optional[Decimal] = None


class QuotationSignScope(BaseModel):
    scope_label: str
    scope_total: Decimal = Decimal("0")
    lines: List[QuotationSignScopeLine] = Field(default_factory=list)


class QuotationSignPageResponse(BaseModel):
    """The read-only quotation a customer sees on the counter-sign link.

    Deliberately does NOT carry ids: the page needs no handle on anything, and a public payload
    that leaks internal identifiers invites somebody to try them elsewhere.
    """

    our_ref: Optional[str] = None
    issue_no: int
    doc_date: Optional[date] = None
    subject_title: Optional[str] = None
    sender_name: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_address: Optional[str] = None
    attn_name: Optional[str] = None
    cover_letter: Optional[str] = None
    terms: Optional[str] = None
    signatory_name: Optional[str] = None
    scopes: List[QuotationSignScope] = Field(default_factory=list)
    grand_total: Decimal = Decimal("0")
    sorento_signature: Optional[QuotationSignatureResponse] = None
    customer_signature: Optional[QuotationSignatureResponse] = None
    accepted_at: Optional[datetime] = None
    is_accepted: bool = False
