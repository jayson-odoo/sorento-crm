"""Pydantic schemas for commercial activity plan APIs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ActivityTemplateScope = Literal["project", "quotation"]


class CommercialActivityTaskStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    label: str
    sort_order: int
    is_default: bool
    is_terminal: bool
    is_active: bool
    color_hex: Optional[str] = None


class CommercialActivityTaskStatusCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=255)
    sort_order: int = 0
    is_default: bool = False
    is_terminal: bool = False
    is_active: bool = True
    color_hex: Optional[str] = Field(None, max_length=7)


class CommercialActivityTaskStatusUpdate(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=255)
    sort_order: Optional[int] = None
    is_default: Optional[bool] = None
    is_terminal: Optional[bool] = None
    is_active: Optional[bool] = None
    color_hex: Optional[str] = Field(None, max_length=7)


class CommercialActivityTemplateNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    template_id: str
    parent_id: Optional[str] = None
    sort_order: int
    title: str
    category_code: Optional[str] = None
    is_service_task: bool = False
    description: Optional[str] = None
    default_status_id: Optional[str] = None
    default_offset_days: Optional[int] = None
    lead_time_days: int = 1
    dependency_node_ids: List[str] = Field(default_factory=list)
    children: List["CommercialActivityTemplateNodeOut"] = Field(default_factory=list)


CommercialActivityTemplateNodeOut.model_rebuild()


class CommercialActivityTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str] = None
    is_active: bool
    version_number: int
    template_scope: ActivityTemplateScope = "project"
    created_by_user_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    nodes: List[CommercialActivityTemplateNodeOut] = Field(default_factory=list)


def commercial_activity_template_out_without_nodes(row: object) -> CommercialActivityTemplateOut:
    """Serialize template metadata without touching the `nodes` relationship (avoids lazy loads)."""
    scope = getattr(row, "template_scope", None) or "project"
    if scope not in ("project", "quotation"):
        scope = "project"
    return CommercialActivityTemplateOut(
        id=str(getattr(row, "id")),
        name=getattr(row, "name"),
        description=getattr(row, "description", None),
        is_active=bool(getattr(row, "is_active")),
        version_number=int(getattr(row, "version_number")),
        template_scope=scope,  # type: ignore[arg-type]
        created_by_user_id=getattr(row, "created_by_user_id", None),
        created_at=getattr(row, "created_at", None),
        updated_at=getattr(row, "updated_at", None),
        nodes=[],
    )


class CommercialActivityTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: bool = True
    template_scope: ActivityTemplateScope = "project"


class CommercialActivityTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    template_scope: Optional[ActivityTemplateScope] = None


class CommercialActivityTemplateNodeCreate(BaseModel):
    parent_id: Optional[str] = None
    sort_order: int = 0
    title: str = Field(..., min_length=1, max_length=512)
    category_code: Optional[str] = Field(None, max_length=64)
    is_service_task: bool = False
    description: Optional[str] = None
    default_status_id: Optional[str] = None
    default_offset_days: Optional[int] = None
    lead_time_days: int = Field(1, ge=1)
    dependency_node_ids: List[str] = Field(default_factory=list)


class CommercialActivityTemplateNodeUpdate(BaseModel):
    parent_id: Optional[str] = None
    sort_order: Optional[int] = None
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    category_code: Optional[str] = Field(None, max_length=64)
    is_service_task: Optional[bool] = None
    description: Optional[str] = None
    default_status_id: Optional[str] = None
    default_offset_days: Optional[int] = None
    lead_time_days: Optional[int] = Field(None, ge=1)
    dependency_node_ids: Optional[List[str]] = None


class CommercialProjectTaskCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    sort_order: int
    is_active: bool


class CommercialProjectTaskCategoryCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=255)
    sort_order: int = 0


class CommercialProjectTaskCategoryUpdate(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=255)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CommercialQuotationActivityTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    master_quotation_id: str
    parent_id: Optional[str] = None
    source_template_node_id: Optional[str] = None
    sort_order: int
    title: str
    status_id: str
    assignee_user_id: Optional[str] = None
    due_at: Optional[datetime] = None
    remind_at: Optional[datetime] = None
    last_reminder_sent_at: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_tender_level: bool
    deleted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    quotation_code: Optional[str] = None
    tender_code: Optional[str] = None
    status_code: Optional[str] = None
    status_label: Optional[str] = None
    children: List["CommercialQuotationActivityTaskOut"] = Field(default_factory=list)


CommercialQuotationActivityTaskOut.model_rebuild()


class CommercialQuotationActivityTaskCreate(BaseModel):
    parent_id: Optional[str] = None
    sort_order: Optional[int] = None
    title: str = Field(..., min_length=1, max_length=512)
    status_id: Optional[str] = None
    assignee_user_id: Optional[str] = None
    due_at: Optional[datetime] = None
    remind_at: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_tender_level: bool = False


class CommercialQuotationActivityTaskUpdate(BaseModel):
    parent_id: Optional[str] = None
    sort_order: Optional[int] = None
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    status_id: Optional[str] = None
    assignee_user_id: Optional[str] = None
    due_at: Optional[datetime] = None
    remind_at: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_tender_level: Optional[bool] = None


class ActivityTaskReorderItem(BaseModel):
    id: str
    sort_order: int


class ReorderActivityTasksBody(BaseModel):
    parent_id: Optional[str] = None
    items: List[ActivityTaskReorderItem] = Field(default_factory=list)


class ApplyActivityTemplateBody(BaseModel):
    template_id: str
    anchor_at: Optional[datetime] = None


class ActivityPlanApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    master_quotation_id: str
    template_id: Optional[str] = None
    template_version: Optional[int] = None
    applied_at: Optional[datetime] = None
    applied_by_user_id: Optional[str] = None
