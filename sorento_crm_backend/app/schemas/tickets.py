"""Ticket schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.tickets import (
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_RAISED_BY_KINDS,
    TICKET_SOURCE_CHANNELS,
    TICKET_STATUSES,
)


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


class TicketDraftPortalUpdate(BaseModel):
    """Portal-side draft edit (token-gated, draft-only).

    The portal review page lets the contact tweak the AI-extracted description
    before submitting. We only expose description fields here — title /
    priority / category come from the LLM extraction and stay server-owned."""

    description_text: Optional[str] = None
    description_html: Optional[str] = None


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
    """Save-only response payload — does not change status or notify submitter."""

    response_html: str
    response_text: Optional[str] = None


class TicketResolutionUpdate(BaseModel):
    """Save-only resolution payload — does not change status or notify submitter."""

    resolution_html: str
    resolution_text: Optional[str] = None


class TicketResponseAndReply(TicketResponseUpdate):
    """Save the response, flip the ticket to ``responded``, and notify the
    submitter via their channel (in-app + email for users; WhatsApp via
    Respond.io for respond-contact submitters)."""


class TicketResolutionAndReply(TicketResolutionUpdate):
    """Save the resolution, flip the ticket to ``resolved``, and notify the
    submitter via their channel."""


class TicketWatchersUpdate(BaseModel):
    user_ids: list[str]


class TicketAttachmentLinkRequest(BaseModel):
    attachment_id: str


class TicketRaisedByActor(BaseModel):
    """Resolved submitter for either a system user or a respond contact.

    ``kind`` is the discriminator. ``id`` is the row id in the corresponding
    table. ``email`` and ``avatar_url`` are user-only; ``phone_number`` and
    ``respond_io_id`` are contact-only — fields not applicable to the kind
    are simply ``None``."""

    kind: str  # 'user' | 'respond_contact'
    id: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    phone_number: Optional[str] = None
    respond_io_id: Optional[str] = None


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

    raised_by: Optional[str] = None
    raised_by_kind: str = "user"
    raised_by_user: Optional[TicketUserRef] = None  # legacy: populated only when kind='user'
    raised_by_actor: Optional[TicketRaisedByActor] = None  # always populated
    source_channel: str = "manual"
    source_conversation_id: Optional[str] = None
    source_message_id: Optional[str] = None
    source_space_id: Optional[str] = None
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


# --- IT Support intake (MCP / n8n) -----------------------------------------


class ITSupportTicketDraftPreview(BaseModel):
    """LLM-extracted draft surfaced to the user for confirmation."""

    title: str
    priority: str
    category: str
    description_html: str
    description_text: str

    @field_validator("priority")
    @classmethod
    def _validate_priority(cls, v: str) -> str:
        if v not in TICKET_PRIORITIES:
            raise ValueError(f"priority must be one of {TICKET_PRIORITIES}")
        return v

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v: str) -> str:
        if v not in TICKET_CATEGORIES:
            raise ValueError(f"category must be one of {TICKET_CATEGORIES}")
        return v


class ITSupportTicketCreateRequest(BaseModel):
    """Request body for the MCP intake endpoint.

    Single-shot: always creates a DRAFT ticket and returns ``draft_url``.
    The caller is expected to surface that URL to the user; the user opens
    it, reviews the preview on a real ticket page, and clicks Submit /
    Edit / Cancel. There is no in-chat confirmation handshake.

    Two accepted input shapes for the draft fields:

    1. ``original_message`` only → server runs LLM extraction to fill in
       title / priority / category / description.
    2. Caller-drafted ``title`` (+ optional priority / category /
       description / description_html / description_text) → server uses
       them directly, skipping the LLM draft step. This is the typical
       path when the calling agent already has those fields in hand.

    Channel context auto-defaults on the server: ``source_channel``
    defaults to ``ai_assistant`` and ``actor_user_id`` falls back to the
    X-API-Key principal's ``act_as`` user id."""

    original_message: Optional[str] = None
    title: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    description_html: Optional[str] = None
    description_text: Optional[str] = None

    source_channel: Optional[Literal["ai_assistant", "whatsapp_respond"]] = None

    actor_user_id: Optional[str] = None
    # ``respond_contact_id`` accepts the internal ``respond_contacts.id`` (UUID) OR
    # the Respond.io numeric ``respond_io_id``. The MCP intake tool forwards the
    # latter under the alias ``contact_id``; the service resolves either.
    respond_contact_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("respond_contact_id", "contact_id"),
    )
    # NOTE: Respond.io has one inbox per contact, so the contact id IS the
    # conversation reference. We do not accept a separate conversation_id from
    # callers — ticket_intake_service derives source_conversation_id from the
    # resolved contact's respond_io_id automatically.
    source_conversation_id: Optional[str] = None
    source_message_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("source_message_id", "message_id"),
    )
    source_space_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("source_space_id", "space_id"),
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator(
        "respond_contact_id",
        "source_conversation_id",
        "source_message_id",
        "source_space_id",
        "actor_user_id",
        mode="before",
    )
    @classmethod
    def _coerce_id_to_str(cls, v: Any) -> Optional[str]:
        # n8n / OpenAI-style tool calls forward Respond.io ids as JSON numbers.
        # Pydantic ``str`` field rejects int; coerce here so the alias paths
        # ``contact_id`` / ``space_id`` accept either form.
        if v is None:
            return None
        if isinstance(v, bool):
            return str(int(v))
        if isinstance(v, (int, float)):
            return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
        return str(v).strip() or None

    @model_validator(mode="after")
    def _validate_minimum_payload(self) -> "ITSupportTicketCreateRequest":
        if not (self.original_message or self.title):
            raise ValueError(
                "either original_message (server drafts) or title (caller-drafted preview) is required"
            )
        return self


class ITSupportTicketCreateResponse(BaseModel):
    """Response from the MCP intake endpoint.

    Always creates a draft and returns a link the user opens to review +
    submit / edit / cancel. The caller (AI assistant or n8n WhatsApp agent)
    is expected to surface ``draft_url`` to the user verbatim and stop —
    no in-chat confirmation handshake."""

    status: Literal["draft_created"]
    ticket_id: str
    ticket_number: Optional[str] = None
    draft_url: str
    portal_token: Optional[str] = None  # only for whatsapp_respond callers
    preview: ITSupportTicketDraftPreview
    ticket: Optional[TicketResponse] = None
