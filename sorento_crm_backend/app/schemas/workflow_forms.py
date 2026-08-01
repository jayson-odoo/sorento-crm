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


class WorkflowSubmissionLineOut(BaseModel):
    id: str
    line_group_id: str
    sort_order: int
    row_data: Dict[str, Any]

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
