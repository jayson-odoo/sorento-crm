"""Lead ↔ respond_contacts junction schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


ContactRole = Literal["main", "stakeholder"]


class RespondContactBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    phone_number: str
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    respond_io_id: Optional[str] = None
    access_type_code: Optional[str] = None
    respond_workspace_id: str


class LeadRespondContactRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lead_id: str
    respond_contact_id: str
    contact_role: ContactRole
    sort_order: int
    created_at: datetime
    updated_at: datetime
    contact: RespondContactBrief


class LeadRespondContactCreate(BaseModel):
    respond_contact_id: str = Field(..., min_length=1)
    contact_role: ContactRole = "stakeholder"
    sort_order: int = 0


class LeadRespondContactLinkByPhone(BaseModel):
    """Create local respond_contact in lead workspace if missing, then link."""

    phone: str = Field(..., min_length=3)
    name: Optional[str] = None
    contact_role: ContactRole = "stakeholder"
    sort_order: int = 0


class LeadRespondContactUpdate(BaseModel):
    contact_role: Optional[ContactRole] = None
    sort_order: Optional[int] = None
