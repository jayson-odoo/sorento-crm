"""Request and response shapes of the `sales` module (plan 3.7, 3.8; slices S6 and S1)."""
from __future__ import annotations

import uuid
from datetime import date as DateType
from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator


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
    #: Team targets with a period containing today (S1, "Targets now" column).
    targets_now: int = 0
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


# --------------------------------------------------------------------------------------
# Targets (slice S1; plan 3.1, 3.2, 3.8, 16.3)
# --------------------------------------------------------------------------------------

def _uuid_str(value):
    """A UUID, kept as the canonical string the models use. Anything else is a 422."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if not isinstance(value, str):
        raise ValueError("must be a UUID")
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise ValueError("must be a UUID") from exc


#: An id sent by the client: validated as a UUID so a bad one is 422, never a database error.
UuidStr = Annotated[str, BeforeValidator(_uuid_str)]

Metric = Literal["amount", "quantity"]
Basis = Literal["ordered", "delivered"]
ProductScope = Literal["all", "categories", "products"]
SplitUnit = Literal["day", "week", "month"]


def _clean_target_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Target name is required.")
    return cleaned


class SalesTargetAgentFigure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sales_agent_id: UuidStr
    #: The agent's figure for each period of the team target.
    target_value: float = Field(..., ge=0)


class SalesTargetCreate(BaseModel):
    """`extra="forbid"`: the round 3 fields `start_month`, `months`, `periodicity` are 422 (S1-1)."""

    model_config = ConfigDict(extra="forbid")

    subject_kind: Literal["agent", "team"]
    sales_agent_id: Optional[UuidStr] = None
    sales_team_id: Optional[UuidStr] = None
    name: str = Field(..., max_length=120)
    metric: Metric
    basis: Basis = "ordered"
    product_scope: ProductScope = "all"
    category_ids: List[UuidStr] = Field(default_factory=list, max_length=500)
    product_ids: List[UuidStr] = Field(default_factory=list, max_length=500)
    start_date: DateType
    end_date: DateType
    split_every: Optional[int] = Field(None, ge=1, le=99)
    split_unit: Optional[SplitUnit] = None
    #: Agent targets: the figure written to every period. Rejected on a team target (T3).
    target_value: Optional[float] = Field(None, ge=0)
    #: Team targets: one child agent target per entry; the team figure is their sum (S1-27).
    agent_figures: Optional[List[SalesTargetAgentFigure]] = Field(None, max_length=200)

    @field_validator("name")
    @classmethod
    def _name(cls, value):
        return _clean_target_name(value)


class SalesTargetUpdate(BaseModel):
    """The header. The subject is not editable (not in this schema, so it is 422)."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, max_length=120)
    metric: Optional[Metric] = None
    basis: Optional[Basis] = None
    product_scope: Optional[ProductScope] = None
    category_ids: Optional[List[UuidStr]] = Field(None, max_length=500)
    product_ids: Optional[List[UuidStr]] = Field(None, max_length=500)
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None
    #: Sent as null (both): the split is turned off.
    split_every: Optional[int] = Field(None, ge=1, le=99)
    split_unit: Optional[SplitUnit] = None

    @field_validator("name")
    @classmethod
    def _name(cls, value):
        return _clean_target_name(value)

    @model_validator(mode="after")
    def _no_null_for_required(self):
        # Leaving a field out keeps it; sending null for one the header cannot be without is
        # a 422 here, never a NOT NULL violation at the database. Only the split may be null
        # (it turns the split off).
        for key in ("name", "metric", "basis", "product_scope", "start_date", "end_date"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} cannot be empty")
        return self


class SalesTargetPeriodUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_value: float = Field(..., ge=0)


class SalesTargetChildCreate(BaseModel):
    """Add figure: a member of the team with no figure yet gets their own child (S1-28)."""

    model_config = ConfigDict(extra="forbid")

    sales_agent_id: UuidStr
    target_value: float = Field(0, ge=0)


class SalesTargetMemberRef(BaseModel):
    sales_agent_id: str
    label: str


class SalesTargetRow(BaseModel):
    """One target period containing `on`, or a "No target" row (every target field null)."""

    target_id: Optional[str] = None
    target_no: Optional[str] = None
    name: Optional[str] = None
    subject_kind: str
    sales_agent_id: Optional[str] = None
    sales_team_id: Optional[str] = None
    subject_label: str
    #: Agent rows: the team whose membership covers `on`. Team rows: the team itself.
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    #: Agent rows under a team filter: the last day of a stay that ended on or before `on`.
    left_on: Optional[DateType] = None
    #: Team rows: the members on `on`, for the Agents pills. Null on agent rows.
    members: Optional[List[SalesTargetMemberRef]] = None
    metric: Optional[str] = None
    basis: Optional[str] = None
    product_scope: Optional[str] = None
    scope_labels: List[str] = Field(default_factory=list)
    period_id: Optional[str] = None
    period_start: Optional[DateType] = None
    period_end: Optional[DateType] = None
    end_date: Optional[DateType] = None
    target_value: Optional[float] = None
    achieved_value: Optional[float] = None
    achieved_pct: Optional[float] = None
    parent_target_id: Optional[str] = None


class SalesTargetList(BaseModel):
    on: DateType
    rows: List[SalesTargetRow]
    #: Non-cancelled lines with no agent, ordered in the calendar month of `on` (S1-14).
    unassigned_amount: float
    #: Active agents with no team membership covering `on`.
    no_team_count: int


class SalesTargetScopeItem(BaseModel):
    #: The category or product id.
    id: str
    label: str


class SalesTargetParentRef(BaseModel):
    id: str
    name: str
    target_no: str


class SalesTargetPeriodOut(BaseModel):
    id: str
    period_start: DateType
    period_end: DateType
    target_value: float
    achieved_value: float
    achieved_pct: Optional[float] = None
    #: The period containing `on`.
    is_current: bool


class SalesTargetChildPeriod(BaseModel):
    id: str
    period_start: DateType
    target_value: float


class SalesTargetChild(BaseModel):
    target_id: str
    target_no: str
    sales_agent_id: str
    label: str
    periods: List[SalesTargetChildPeriod]


class SalesTargetDetail(BaseModel):
    id: str
    target_no: str
    name: str
    subject_kind: str
    sales_agent_id: Optional[str] = None
    sales_team_id: Optional[str] = None
    subject_label: str
    #: Agent targets: the team the agent is in on `on`.
    subject_team_name: Optional[str] = None
    parent: Optional[SalesTargetParentRef] = None
    metric: str
    basis: str
    product_scope: str
    start_date: DateType
    end_date: DateType
    split_every: Optional[int] = None
    split_unit: Optional[str] = None
    #: "Ordered", "Delivered", or "Delivered (by DO date)" once any DO line is linked.
    counts_label: str
    scope: List[SalesTargetScopeItem]
    periods: List[SalesTargetPeriodOut]
    children: List[SalesTargetChild]
    members_without_figure: List[SalesTargetMemberRef]
    child_count: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SalesTargetOptionAgent(BaseModel):
    id: str
    code: str
    label: str
    team_id: Optional[str] = None
    team_name: Optional[str] = None


class SalesTargetOptionMember(BaseModel):
    sales_agent_id: str
    label: str
    valid_from: Optional[DateType] = None
    valid_to: Optional[DateType] = None


class SalesTargetOptionTeam(BaseModel):
    id: str
    name: str
    is_active: bool
    #: Every stay, so the modal can offer the members overlapping the chosen range.
    members: List[SalesTargetOptionMember]


class SalesTargetOptionCategory(BaseModel):
    id: str
    label: str
    parent_category_id: Optional[str] = None


class SalesTargetOptions(BaseModel):
    agents: List[SalesTargetOptionAgent]
    teams: List[SalesTargetOptionTeam]
    categories: List[SalesTargetOptionCategory]
