"""Wire shapes for onboarding intake and review.

The one that matters is ``PublicTemplateOption``. It carries a name, a
description and three booleans - and NOT ``role_ids``, ``company_ids`` or
``access_agent_ids``. That omission is the feature's privacy boundary (UAC
AC-5.4), and it is enforced HERE, in the schema, rather than by remembering not
to render those fields in a component: a requester with no CRM account must be
able to propose "Salesperson" while learning nothing about what roles exist.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- shared -------------------------------------------------------------------


class CollisionOut(BaseModel):
    kind: str
    label: str


class PersonOut(BaseModel):
    id: str
    row_number: int
    full_name: str
    nick_name: Optional[str] = None
    phone_raw: Optional[str] = None
    email_raw: Optional[str] = None
    section_label: Optional[str] = None
    template_id: Optional[str] = None
    requester_note: Optional[str] = None
    reviewer_note: Optional[str] = None
    needs_system_account: bool
    needs_respond_contact: bool
    needs_agent_seat: bool
    review_status: str
    rejection_reason: Optional[str] = None
    #: Recomputed on read from the normalised values, so a row the reviewer just
    #: corrected stops complaining without a round trip through the parser.
    problems: list[str] = Field(default_factory=list)
    collisions: list[CollisionOut] = Field(default_factory=list)
    user_step: str
    user_error: Optional[str] = None
    #: A name, never an id (cursor rule: no UUIDs in the UI).
    user_label: Optional[str] = None
    contact_step: str
    contact_error: Optional[str] = None
    agent_step: str
    agent_error: Optional[str] = None


class PublicTemplateOption(BaseModel):
    """What the requester may see of a template. See the module docstring."""

    id: str
    name: str
    description: Optional[str] = None
    default_needs_system_account: bool
    default_needs_respond_contact: bool
    default_needs_agent_seat: bool


# --- public intake ------------------------------------------------------------


class DraftRowIn(BaseModel):
    row_number: int = 0
    full_name: str
    nick_name: Optional[str] = None
    phone_raw: Optional[str] = None
    email_raw: Optional[str] = None
    section_label: Optional[str] = None
    template_id: Optional[str] = None
    requester_note: Optional[str] = None
    needs_system_account: bool = True
    needs_respond_contact: bool = False
    needs_agent_seat: bool = False


class SaveRowsIn(BaseModel):
    rows: list[DraftRowIn]


class SubmitIn(BaseModel):
    requester_note: Optional[str] = None


class IntakeContextOut(BaseModel):
    title: str
    company_name: str
    requester_name: str
    requester_email: str
    status: str
    expires_at: datetime
    #: False once submitted, revoked or expired. The page renders its read-only
    #: status view off this rather than re-deriving the rule client-side.
    editable: bool
    requester_note: Optional[str] = None
    templates: list[PublicTemplateOption] = Field(default_factory=list)
    people: list[PersonOut] = Field(default_factory=list)


class ParsedRowOut(BaseModel):
    row_number: int
    full_name: str
    nick_name: Optional[str] = None
    phone_raw: Optional[str] = None
    email_raw: Optional[str] = None
    section_label: Optional[str] = None
    problems: list[str] = Field(default_factory=list)


class ParseProblemOut(BaseModel):
    row: int
    reason: str


class ParseResultOut(BaseModel):
    rows: list[ParsedRowOut] = Field(default_factory=list)
    problems: list[ParseProblemOut] = Field(default_factory=list)
    unmapped_headers: list[str] = Field(default_factory=list)
    missing_columns: list[str] = Field(default_factory=list)
    total_rows: int = 0
    sections: list[str] = Field(default_factory=list)


# --- admin --------------------------------------------------------------------


class RequestCreateIn(BaseModel):
    company_id: str
    title: str
    requester_name: str
    requester_email: str
    requester_phone: Optional[str] = None
    expiry_days: int = 14


class RequestSummaryOut(BaseModel):
    id: str
    title: str
    company_name: str
    requester_name: str
    requester_email: str
    status: str
    people_count: int
    approved_count: int
    rejected_count: int
    submitted_at: Optional[datetime] = None
    created_at: datetime
    expires_at: datetime
    revoked_at: Optional[datetime] = None


class RequestDetailOut(RequestSummaryOut):
    reviewer_note: Optional[str] = None
    requester_note: Optional[str] = None
    reviewed_by_name: Optional[str] = None
    provisioned_at: Optional[datetime] = None
    source_file_name: Optional[str] = None
    templates: list[PublicTemplateOption] = Field(default_factory=list)
    people: list[PersonOut] = Field(default_factory=list)
    #: Only ever returned to an authenticated reviewer, so the captain can copy
    #: the link into WhatsApp himself the way the contact portal already allows.
    intake_url: Optional[str] = None


class PersonPatchIn(BaseModel):
    full_name: Optional[str] = None
    nick_name: Optional[str] = None
    phone_raw: Optional[str] = None
    email_raw: Optional[str] = None
    section_label: Optional[str] = None
    template_id: Optional[str] = None
    requester_note: Optional[str] = None
    reviewer_note: Optional[str] = None
    needs_system_account: Optional[bool] = None
    needs_respond_contact: Optional[bool] = None
    needs_agent_seat: Optional[bool] = None


class RejectIn(BaseModel):
    reason: str


class TemplateWriteIn(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True
    role_ids: list[str] = Field(default_factory=list)
    company_ids: list[str] = Field(default_factory=list)
    access_agent_ids: list[str] = Field(default_factory=list)
    default_needs_system_account: bool = True
    default_needs_respond_contact: bool = False
    default_needs_agent_seat: bool = False


class TemplateOut(PublicTemplateOption):
    """The reviewer's view: the labels PLUS what they actually resolve to."""

    is_active: bool
    role_ids: list[str] = Field(default_factory=list)
    company_ids: list[str] = Field(default_factory=list)
    access_agent_ids: list[str] = Field(default_factory=list)
    captured_from_user_id: Optional[str] = None


class CaptureTemplateIn(BaseModel):
    name: str


class ApproveResultOut(BaseModel):
    status: str
    job_id: Optional[str] = None
    queued_people: int
