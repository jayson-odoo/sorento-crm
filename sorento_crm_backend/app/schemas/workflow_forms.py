"""Pydantic schemas for workflow forms API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkflowFormDefinitionCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class WorkflowFormDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    draft_schema: Optional[Dict[str, Any]] = None
    # Line-derived header status (F1a), opt-in per definition. Sent as a group: the
    # keys name rungs of the HEADER graph in force for this form, the open one must be
    # that graph's starting state and the resolved one must not be final, and the save
    # is refused with `status_derivation_misconfigured` when either rule is broken.
    derives_status_from_lines: Optional[bool] = None
    derived_open_status_key: Optional[str] = Field(None, max_length=64)
    derived_resolved_status_key: Optional[str] = Field(None, max_length=64)
    # Portal submittability (F2b). Two fields, one meaning each: the boolean is the door
    # and the list narrows who may walk through it, where an EMPTY list means no
    # narrowing. Sending `[]` therefore opens the form to every contact, which is only
    # safe because it takes `portal_submittable=true` to reach the list at all.
    portal_submittable: Optional[bool] = None
    portal_party_kinds: Optional[List[str]] = None


class WorkflowFormVersionOut(BaseModel):
    id: str
    definition_id: str
    version_number: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkflowPublishedDefinitionOut(BaseModel):
    """Minimal definition row for runtime menus / submitters (published forms only)."""

    id: str
    code: str
    name: str


class WorkflowFormDefinitionOut(BaseModel):
    id: str
    code: str
    name: str
    description: Optional[str] = None
    is_active: bool
    draft_schema: Dict[str, Any]
    published_version_id: Optional[str] = None
    published_version_number: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Off, with no keys, on every definition that has not opted in. Reported so the
    # builder can show the current configuration instead of guessing at it.
    derives_status_from_lines: bool = False
    derived_open_status_key: Optional[str] = None
    derived_resolved_status_key: Optional[str] = None
    # Closed, with no narrowing, on every definition that never opted in. Reported so
    # the builder shows the stance instead of guessing at it.
    portal_submittable: bool = False
    portal_party_kinds: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class WorkflowSubmissionLineIn(BaseModel):
    line_group_id: str
    sort_order: int = 0
    row_data: Dict[str, Any] = Field(default_factory=dict)


class WorkflowSubmissionCreate(BaseModel):
    definition_id: str
    header_data: Dict[str, Any] = Field(default_factory=dict)
    lines: List[WorkflowSubmissionLineIn] = Field(default_factory=list)


class WorkflowSubmissionUpdate(BaseModel):
    header_data: Optional[Dict[str, Any]] = None
    lines: Optional[List[WorkflowSubmissionLineIn]] = None


class WorkflowTransitionRequest(BaseModel):
    """The status to move to. The engine resolves which edge authorises it."""

    to_status_id: str
    remark: Optional[str] = None


class WorkflowLineTransitionRequest(BaseModel):
    """The line status to move to. The engine resolves which edge authorises it.

    No remark: ``workflow_submission_transition_logs`` is the HEADER's companion log,
    and a line move writes nothing there, so a remark would have nowhere to land.
    """

    to_status_id: str


class WorkflowLineDispositionRequest(BaseModel):
    """How a decided line will be settled, or ``null`` to clear it.

    Both fields default to None, so an omitted ``disposition`` CLEARS. That is
    deliberate: this is the one payload whose whole purpose is to set or unset a single
    value, and a PATCH that silently kept the old one would leave the caller unable to
    clear it at all.
    """

    disposition: Optional[str] = Field(None, max_length=150)
    disposition_reason: Optional[str] = None


class WorkflowLineDispositionOptionOut(BaseModel):
    """One selectable disposition, straight from the bound lookup set."""

    value: str
    label: str
    description: Optional[str] = None


class WorkflowLineDispositionOptionsOut(BaseModel):
    """The dispositions an admin currently offers, in their configured order.

    ``set_key`` is None when nothing is bound to the column, which is a real state (a
    deployment that never seeded the set) and reads as an empty dropdown rather than an
    error. Never a hardcoded list: the options are admin-editable master data.
    """

    set_key: Optional[str] = None
    options: List[WorkflowLineDispositionOptionOut] = Field(default_factory=list)


class WorkflowSubmissionLineOut(BaseModel):
    id: str
    line_group_id: str
    sort_order: int
    row_data: Dict[str, Any]
    # All NULL for a form that does not use line-level statuses, which is every form
    # today. The key and label travel beside the id because the frontend may not render
    # a UUID.
    status_id: Optional[str] = None
    status_key: Optional[str] = None
    status_label: Optional[str] = None
    disposition: Optional[str] = None
    disposition_reason: Optional[str] = None

    class Config:
        from_attributes = True


class WorkflowTransitionLogOut(BaseModel):
    """One accepted move: the endpoints, the edge that authorised it, the remark.

    Keys travel beside the ids because the frontend may not render a UUID.
    """

    id: str
    from_status_id: Optional[str] = None
    to_status_id: str
    from_status_key: Optional[str] = None
    to_status_key: Optional[str] = None
    status_transition_id: Optional[str] = None
    remark: Optional[str] = None
    user_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkflowSubmissionOut(BaseModel):
    id: str
    definition_id: str
    version_id: str
    status_id: str
    # Derived from the joined status row, so a grid never has to show an id.
    status_key: Optional[str] = None
    status_label: Optional[str] = None
    header_data: Dict[str, Any]
    lines: List[WorkflowSubmissionLineOut] = Field(default_factory=list)
    transition_logs: List[WorkflowTransitionLogOut] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by_user_id: Optional[str] = None
    # Display + rendering (no separate definitions.view permission needed)
    definition_name: Optional[str] = None
    definition_code: Optional[str] = None
    form_version_number: Optional[int] = None
    # Frozen schema for this submission's version (detail / mutation responses).
    form_schema: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class WorkflowPreviewOut(BaseModel):
    """Resolved draft or published schema for UI preview."""

    schema: Dict[str, Any]
    source: str  # "draft" | "published"
