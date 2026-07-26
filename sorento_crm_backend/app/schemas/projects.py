"""Project Sales schemas.

No UUID is ever the user-facing identifier of a project: ``project_code`` is, and
every response that names a project carries it. Party and owner FKs are echoed back
with resolved names for the same reason (the FE cursor rule bans UUIDs in the UI).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

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
