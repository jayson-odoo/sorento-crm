"""Unified workflow_stages API (all domains)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class UnifiedWorkflowStageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    domain: str
    code: str
    label: str
    color_hex: Optional[str] = None
    description: Optional[str] = None
    sort_order: int
    is_terminal: bool
    allows_conversion: Optional[bool] = None
    can_go_back: bool = False
    is_active: bool = True
    is_cancelled: bool = False
    created_at: datetime
    updated_at: datetime


class UnifiedWorkflowStageCreate(BaseModel):
    domain: str = Field(..., max_length=32)
    code: str = Field(..., max_length=50)
    label: str = Field(..., max_length=100)
    color_hex: Optional[str] = Field(None, max_length=7)
    description: Optional[str] = None
    sort_order: int = 0
    is_terminal: bool = False
    allows_conversion: Optional[bool] = None
    can_go_back: bool = False
    is_active: bool = True
    is_cancelled: bool = False


class UnifiedWorkflowStageUpdate(BaseModel):
    label: Optional[str] = Field(None, max_length=100)
    color_hex: Optional[str] = Field(None, max_length=7)
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_terminal: Optional[bool] = None
    allows_conversion: Optional[bool] = None
    can_go_back: Optional[bool] = None
    is_active: Optional[bool] = None
    is_cancelled: Optional[bool] = None


def unified_workflow_stage_response(row: Any) -> UnifiedWorkflowStageResponse:
    return UnifiedWorkflowStageResponse(
        id=str(row.id),
        domain=row.domain,
        code=row.code,
        label=row.label,
        color_hex=getattr(row, "color_hex", None),
        description=row.description,
        sort_order=row.sort_order,
        is_terminal=bool(row.is_terminal),
        allows_conversion=row.allows_conversion,
        can_go_back=bool(getattr(row, "can_go_back", False)),
        is_active=bool(getattr(row, "is_active", True)),
        is_cancelled=bool(getattr(row, "is_cancelled", False)),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
