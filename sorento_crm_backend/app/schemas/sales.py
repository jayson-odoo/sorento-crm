"""Request and response shapes of the `sales` module (plan 3.7, 3.8; slice S6)."""
from __future__ import annotations

from datetime import date as DateType
from datetime import datetime
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
