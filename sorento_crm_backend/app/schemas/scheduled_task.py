"""Pydantic schemas for scheduled tasks and runs."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any
from datetime import datetime


class ScheduledTaskBase(BaseModel):
    key: str
    name: str
    description: Optional[str] = None
    enabled: bool = True
    interval_unit: str = Field(..., pattern="^(seconds|minutes|hours|days)$")
    interval_value: int = Field(..., ge=1)
    timezone: str = "UTC"
    start_at: Optional[datetime] = None


class ScheduledTaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    interval_unit: Optional[str] = Field(None, pattern="^(seconds|minutes|hours|days)$")
    interval_value: Optional[int] = Field(None, ge=1)
    timezone: Optional[str] = None
    start_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class ScheduledTaskResponse(BaseModel):
    id: str
    key: str
    name: str
    description: Optional[str] = None
    enabled: bool
    interval_unit: str
    interval_value: int
    timezone: str
    start_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
    last_error: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = Field(None, serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime

    # Derived overdue state. Computed from `last_run_at + interval`, the scheduler's
    # own truth - NOT from the display-only `next_run_at` above.
    due_at: Optional[datetime] = None
    grace_percent: Optional[int] = None      # effective: per-task override or global
    grace_seconds: Optional[int] = None      # after the [60s, 30min] clamp
    is_overdue: bool = False
    late_by_seconds: Optional[int] = None    # measured from due_at, not due_at + grace

    model_config = ConfigDict(from_attributes=True)


class ScheduledTaskRunResponse(BaseModel):
    id: str
    task_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    duration_ms: Optional[int] = None
    summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
