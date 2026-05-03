"""Ticket schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.tickets import TICKET_CATEGORIES, TICKET_PRIORITIES, TICKET_STATUSES


class TicketUserRef(BaseModel):
    id: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None


class TicketWatcherRef(BaseModel):
    user_id: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    added_at: datetime


class TicketRespondContactRef(BaseModel):
    respond_contact_id: str
    name: Optional[str] = None
    phone_number: Optional[str] = None
    respond_io_id: Optional[str] = None
    is_primary: bool = False


class TicketAttachmentRef(BaseModel):
    id: str
    attachment_id: str
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    file_size_bytes: Optional[Decimal] = None
    uploaded_at: Optional[datetime] = None


class TicketBase(BaseModel):
    title: str
    description_html: Optional[str] = None
    description_text: Optional[str] = None
    priority: str = "medium"
    category: str = "question"
    due_date: Optional[date] = None
    assigned_to: Optional[str] = None

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in TICKET_PRIORITIES:
            raise ValueError(f"priority must be one of {TICKET_PRIORITIES}")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in TICKET_CATEGORIES:
            raise ValueError(f"category must be one of {TICKET_CATEGORIES}")
        return v


class TicketCreate(TicketBase):
    save_as_draft: bool = False
    attachment_ids: list[str] = Field(default_factory=list)


class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description_html: Optional[str] = None
    description_text: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[date] = None

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in TICKET_PRIORITIES:
            raise ValueError(f"priority must be one of {TICKET_PRIORITIES}")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in TICKET_CATEGORIES:
            raise ValueError(f"category must be one of {TICKET_CATEGORIES}")
        return v


class TicketStatusChangeRequest(BaseModel):
    new_status: str
    note: Optional[str] = None

    @field_validator("new_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in TICKET_STATUSES:
            raise ValueError(f"status must be one of {TICKET_STATUSES}")
        return v


class TicketAssignRequest(BaseModel):
    assignee_id: Optional[str] = None  # null = unassign


class TicketResponseUpdate(BaseModel):
    response_html: str
    response_text: Optional[str] = None


class TicketResolutionUpdate(BaseModel):
    resolution_html: str
    resolution_text: Optional[str] = None


class TicketWatchersUpdate(BaseModel):
    user_ids: list[str]


class TicketAttachmentLinkRequest(BaseModel):
    attachment_id: str


class TicketResponse(BaseModel):
    id: str
    ticket_number: Optional[str] = None
    title: str
    description_html: Optional[str] = None
    description_text: Optional[str] = None
    status: str
    priority: str
    category: str
    due_date: Optional[date] = None

    raised_by: str
    raised_by_user: Optional[TicketUserRef] = None
    assigned_to: Optional[str] = None
    assigned_to_user: Optional[TicketUserRef] = None

    response_html: Optional[str] = None
    response_text: Optional[str] = None
    responded_by: Optional[str] = None
    responded_by_user: Optional[TicketUserRef] = None

    resolution_html: Optional[str] = None
    resolution_text: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_by_user: Optional[TicketUserRef] = None

    submitted_at: Optional[datetime] = None
    assigned_at: Optional[datetime] = None
    first_response_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    sla_response_due_at: Optional[datetime] = None
    sla_resolution_due_at: Optional[datetime] = None
    response_time_hours: Optional[Decimal] = None
    resolution_time_hours: Optional[Decimal] = None

    watchers: list[TicketWatcherRef] = Field(default_factory=list)
    respond_contacts: list[TicketRespondContactRef] = Field(default_factory=list)
    attachments: list[TicketAttachmentRef] = Field(default_factory=list)

    is_overdue_response: bool = False
    is_overdue_resolution: bool = False

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TicketKanbanResponse(BaseModel):
    columns: dict[str, list[TicketResponse]]
    counts: dict[str, int]


class BulkDeleteTicketsRequest(BaseModel):
    ids: list[str]
