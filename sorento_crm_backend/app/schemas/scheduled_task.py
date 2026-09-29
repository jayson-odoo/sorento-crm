"""Pydantic schemas for scheduled tasks and runs."""
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional, Dict, Any, Annotated, List, Literal
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


class ScmReorderRunTaskMetadata(BaseModel):
    """Validates the ``scm_reorder_run`` task's ``metadata`` (#1340): the scope the
    scheduled reorder run plans with. Every key is optional - absent means the same
    default the run makes today (all warehouses, all products, both demand legs, no
    window, full budget, market off). Other keys the task's metadata already carries
    (``company_ids``, ``grace_percent``) pass through untouched via ``extra="allow"``.
    """
    model_config = ConfigDict(extra="allow")

    warehouse_codes: Optional[List[Annotated[str, Field(max_length=100)]]] = Field(None, max_length=500)
    product_codes: Optional[List[Annotated[str, Field(max_length=100)]]] = Field(None, max_length=500)
    demand_class: Optional[Literal["project", "retail"]] = None
    horizon_start_days: Optional[int] = Field(None, ge=-3650, le=3650, strict=True)
    # A negative end is Start Plan's own refusal of a past cut-off: it leaves the run
    # with no demand, so the floor is 0 (today), not negative.
    horizon_end_days: Optional[int] = Field(None, ge=0, le=3650, strict=True)
    budget: Optional[float] = Field(None, ge=0, strict=True)
    include_market: Optional[bool] = Field(None, strict=True)

    @model_validator(mode="after")
    def _start_before_end(self):
        if (
            self.horizon_start_days is not None
            and self.horizon_end_days is not None
            and self.horizon_start_days > self.horizon_end_days
        ):
            raise ValueError("horizon_start_days must be on or before horizon_end_days")
        return self


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
