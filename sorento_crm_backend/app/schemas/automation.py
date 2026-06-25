"""Schemas for automations + runs."""
from __future__ import annotations

from datetime import datetime, time
from typing import Any, Optional

from pydantic import BaseModel, Field


class RecipientConfig(BaseModel):
    user_ids: list[str] = Field(default_factory=list)
    role_ids: list[str] = Field(default_factory=list)
    include_promotion_owner: bool = False
    include_assigned_cs_pic: bool = False
    extra_emails: list[str] = Field(default_factory=list)


class AutomationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    enabled: bool = True
    trigger_type: str = Field(..., min_length=1, max_length=80)
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    action_type: str = Field(default="send_email", max_length=80)
    email_template_id: str
    recipient_config: RecipientConfig = Field(default_factory=RecipientConfig)
    group_matches: bool = True
    schedule_type: str = Field(default="manual")  # manual | daily
    run_time: Optional[time] = None
    timezone: str = Field(default="Asia/Kuala_Lumpur", max_length=80)


class AutomationCreate(AutomationBase):
    pass


class AutomationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    enabled: Optional[bool] = None
    trigger_type: Optional[str] = Field(None, min_length=1, max_length=80)
    trigger_config: Optional[dict[str, Any]] = None
    action_type: Optional[str] = None
    email_template_id: Optional[str] = None
    recipient_config: Optional[RecipientConfig] = None
    group_matches: Optional[bool] = None
    schedule_type: Optional[str] = None
    run_time: Optional[time] = None
    timezone: Optional[str] = None


class AutomationResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    enabled: bool
    trigger_type: str
    trigger_config: dict[str, Any]
    action_type: str
    email_template_id: str
    email_template_name: Optional[str] = None
    recipient_config: dict[str, Any]
    group_matches: bool = True
    schedule_type: str
    run_time: Optional[time]
    timezone: str
    last_run_at: Optional[datetime]
    last_status: Optional[str]
    last_error: Optional[str]
    next_run_at: Optional[datetime]
    created_by_user_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AutomationToggleRequest(BaseModel):
    enabled: bool


class AutomationRunResponse(BaseModel):
    id: str
    automation_id: str
    run_mode: str
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    duration_ms: Optional[int]
    recipients_attempted: int
    recipients_delivered: int
    summary: Optional[dict[str, Any]]
    error: Optional[str]

    class Config:
        from_attributes = True


class AutomationRunNowResponse(BaseModel):
    run_id: str
    status: str
    recipients_attempted: int
    summary: Optional[dict[str, Any]] = None


class TriggerSpec(BaseModel):
    type: str
    label: str
    description: str
    config_schema: dict[str, Any]


class TriggerCatalog(BaseModel):
    triggers: list[TriggerSpec]
