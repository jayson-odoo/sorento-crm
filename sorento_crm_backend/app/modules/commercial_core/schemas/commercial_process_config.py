"""Pydantic schemas for commercial process configuration APIs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field


# --- Tender / MQ / task stages (config tables) ---
class CommercialConfigStageBase(BaseModel):
    stage_name: str = Field(..., max_length=100)
    description: Optional[str] = None
    sort_order: int = 0
    is_terminal: bool = False
    is_active: bool = True


class CommercialConfigStageCreate(CommercialConfigStageBase):
    stage_code: str = Field(..., max_length=50)


class CommercialConfigStageUpdate(BaseModel):
    stage_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_terminal: Optional[bool] = None
    is_active: Optional[bool] = None


class CommercialConfigStageResponse(CommercialConfigStageBase):
    stage_code: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


def commercial_config_stage_response_from_workflow(row: Any) -> CommercialConfigStageResponse:
    return CommercialConfigStageResponse(
        stage_code=row.code,
        stage_name=row.label,
        description=row.description,
        sort_order=row.sort_order,
        is_terminal=row.is_terminal,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# --- Activity templates (commercial_activity_templates; template_code mirrors name for API compatibility) ---
class CommercialActivityTemplateBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    is_active: bool = True


class CommercialActivityTemplateCreate(CommercialActivityTemplateBase):
    template_code: Optional[str] = Field(None, max_length=64)


class CommercialActivityTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CommercialActivityTemplateResponse(CommercialActivityTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    version_number: int = 1
    created_at: datetime
    updated_at: datetime

    @computed_field
    def template_code(self) -> str:
        return self.name


# --- Reminder defaults ---
class CommercialReminderDefaultBase(BaseModel):
    display_name: str = Field(..., max_length=255)
    rule: Dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0


class CommercialReminderDefaultCreate(CommercialReminderDefaultBase):
    context: str = Field(..., max_length=80)


class CommercialReminderDefaultUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=255)
    rule: Optional[Dict[str, Any]] = None
    sort_order: Optional[int] = None


class CommercialReminderDefaultResponse(CommercialReminderDefaultBase):
    context: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Checkpoint templates ---
class CommercialCheckpointTemplateBase(BaseModel):
    name: str = Field(..., max_length=255)
    sort_order: int = 0
    is_active: bool = True


class CommercialCheckpointTemplateCreate(CommercialCheckpointTemplateBase):
    checkpoint_code: str = Field(..., max_length=64)


class CommercialCheckpointTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CommercialCheckpointTemplateResponse(CommercialCheckpointTemplateBase):
    checkpoint_code: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Process settings ---
class CommercialProcessSettingsResponse(BaseModel):
    assignment: Dict[str, Any] = Field(default_factory=dict)
    reminders: Dict[str, Any] = Field(default_factory=dict)
    pricing_controls: Dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CommercialProcessSettingsUpdate(BaseModel):
    assignment: Optional[Dict[str, Any]] = None
    reminders: Optional[Dict[str, Any]] = None
    pricing_controls: Optional[Dict[str, Any]] = None


class SelectOption(BaseModel):
    """Dropdown option (code + label; no UUID in UI)."""

    code: str
    label: str
