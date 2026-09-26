"""Request and response shapes of the `sales` module (plan 3.7, 3.8; slices S6, S2)."""
from __future__ import annotations

from datetime import date as DateType
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


def _clean_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Team name is required.")
    return cleaned


class SalesTeamCreate(BaseModel):
    name: str = Field(..., max_length=120)
    sales_agent_ids: List[str] = Field(default_factory=list)
    is_active: bool = True
    #: The day a picked agent who is in another team starts counting here (T2). Default today.
    moves_on: Optional[DateType] = None
    #: One of the team's agents (W1); one not in `sales_agent_ids` is added to them.
    leader_sales_agent_id: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name(cls, value):
        return _clean_name(value)


class SalesTeamUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    is_active: Optional[bool] = None
    #: Optional: the team page saves the name, Active and the agents in ONE transaction, so a
    #: refused rename cannot leave the agents half-saved (review round 1, N1).
    sales_agent_ids: Optional[List[str]] = None
    moves_on: Optional[DateType] = None
    #: Sent: set the leader (null clears it). Not sent: the leader stays, unless left out (W1).
    leader_sales_agent_id: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name(cls, value):
        return _clean_name(value)


class SalesTeamMembersUpdate(BaseModel):
    sales_agent_ids: List[str]
    moves_on: Optional[DateType] = None


class SalesTeamAgentRef(BaseModel):
    sales_agent_id: str
    label: str


class SalesTeamMemberResponse(BaseModel):
    sales_agent_id: str
    code: str
    name: Optional[str] = None
    label: str
    valid_from: Optional[DateType] = None
    valid_to: Optional[DateType] = None
    #: Left the team on or before the date shown; drawn muted with a "Left <date>" pill (S6-15).
    left: bool = False


class SalesTeamMove(BaseModel):
    sales_agent_id: str
    label: str
    from_team_id: str
    from_team_name: str


class SalesTeamListItem(BaseModel):
    id: str
    name: str
    is_active: bool
    leader_sales_agent_id: Optional[str] = None
    member_count: int
    members: List[SalesTeamAgentRef]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SalesTeamDetail(BaseModel):
    id: str
    name: str
    is_active: bool
    #: The team's leader now, one of its agents (W1); None when none is picked.
    leader_sales_agent_id: Optional[str] = None
    leader_label: Optional[str] = None
    #: Members on the date shown, not counting those who have left.
    member_count: int
    #: The date the members are read for (`on`, default today).
    on: DateType
    members: List[SalesTeamMemberResponse]
    #: Agents this write moved out of another team; empty on a read.
    moved: List[SalesTeamMove] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SalesTeamAgentOption(BaseModel):
    id: str
    code: str
    label: str
    #: The team the agent is in now, so the picker can say "(now in Central)".
    team_id: Optional[str] = None
    team_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Opportunities (plan 3.4, 3.5; slice S2)
# ---------------------------------------------------------------------------


class SalesOpportunityLineInput(BaseModel):
    product_id: str
    qty: Decimal = Field(..., gt=0)


class SalesOpportunityCreate(BaseModel):
    """CRM create (S2-7). Portal create is `PortalSalesOpportunityCreate` below - it has
    no `sales_agent_id`/`source`/`sales_order_id` fields, so those keys in a portal body
    are ignored rather than accepted (section 16)."""

    title: str = Field(..., max_length=200)
    expected_amount: Decimal
    expected_close_date: DateType
    customer_id: Optional[str] = None
    prospect_name: Optional[str] = None
    #: CRM only: stamped from the customer when omitted (S2-7).
    sales_agent_id: Optional[str] = None
    lines: Optional[List[SalesOpportunityLineInput]] = None


class SalesOpportunityUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    expected_amount: Optional[Decimal] = None
    expected_close_date: Optional[DateType] = None
    customer_id: Optional[str] = None
    prospect_name: Optional[str] = None
    sales_agent_id: Optional[str] = None
    status_id: Optional[str] = None
    lost_reason: Optional[str] = None
    #: Won only; must be the same customer as the opportunity (S2-7).
    sales_order_id: Optional[str] = None
    lines: Optional[List[SalesOpportunityLineInput]] = None


class PortalSalesOpportunityCreate(BaseModel):
    """No `sales_agent_id` (from the token only, S2-3), no `source`, no
    `sales_order_id` (only the CRM sends it, section 16)."""

    title: str = Field(..., max_length=200)
    expected_amount: Decimal
    expected_close_date: DateType
    customer_id: Optional[str] = None
    prospect_name: Optional[str] = None
    lines: Optional[List[SalesOpportunityLineInput]] = None


class PortalSalesOpportunityUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    expected_amount: Optional[Decimal] = None
    expected_close_date: Optional[DateType] = None
    customer_id: Optional[str] = None
    prospect_name: Optional[str] = None
    status_id: Optional[str] = None
    lost_reason: Optional[str] = None
    lines: Optional[List[SalesOpportunityLineInput]] = None


class SalesOpportunityLineResponse(BaseModel):
    id: str
    product_id: str
    product_code: str
    product_name: str
    qty: Decimal


class SalesOpportunityTransition(BaseModel):
    to_status_id: str
    key: str
    label: str


class SalesOpportunityResponse(BaseModel):
    id: str
    opportunity_no: str
    title: str
    customer_id: Optional[str] = None
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None
    prospect_name: Optional[str] = None
    sales_agent_id: Optional[str] = None
    sales_agent_label: Optional[str] = None
    status_id: Optional[str] = None
    stage_key: Optional[str] = None
    stage_label: Optional[str] = None
    win_probability: Optional[Decimal] = None
    outcome: str
    expected_amount: Decimal
    expected_close_date: DateType
    lost_reason: Optional[str] = None
    lost_reason_label: Optional[str] = None
    sales_order_id: Optional[str] = None
    sales_order_no: Optional[str] = None
    source: str
    created_by_label: Optional[str] = None
    created_by_contact_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    stage_changed_at: Optional[datetime] = None
    lines: List[SalesOpportunityLineResponse] = Field(default_factory=list)
    available_transitions: List[SalesOpportunityTransition] = Field(default_factory=list)


class SalesOpportunityCustomerOptionItem(BaseModel):
    customer_id: str
    customer_code: str
    customer_name: str


class SalesOpportunityProspectOption(BaseModel):
    name: str


class SalesOpportunityBlockedOption(BaseModel):
    name: str
    message: str


class SalesOpportunityCustomerOptionsResponse(BaseModel):
    items: List[SalesOpportunityCustomerOptionItem]
    prospect: Optional[SalesOpportunityProspectOption] = None
    blocked: Optional[SalesOpportunityBlockedOption] = None


class SalesOpportunityStageOption(BaseModel):
    id: str
    key: str
    label: str
    win_probability: Optional[Decimal] = None
    is_active: bool
    is_terminal: bool


class SalesOpportunityLostReasonOption(BaseModel):
    value: str
    label: str


class SalesOpportunityMeta(BaseModel):
    stages: List[SalesOpportunityStageOption]
    lost_reasons: List[SalesOpportunityLostReasonOption]


class SalesOpportunitySalesOrderOption(BaseModel):
    id: str
    so_number: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    order_date: Optional[DateType] = None
