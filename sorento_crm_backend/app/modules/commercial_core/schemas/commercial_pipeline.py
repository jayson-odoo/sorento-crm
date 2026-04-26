"""Schemas for commercial pipeline Kanban, filters, and dashboard."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StageInfo(BaseModel):
    code: str
    label: str
    sort_order: int = 0
    is_terminal: bool = False


class StageConfigResponse(BaseModel):
    lead_stages: List[StageInfo]
    tender_stages: List[StageInfo]
    mq_execution_states: List[StageInfo]
    pipeline_task_statuses: List[StageInfo]
    activity_task_statuses: List[StageInfo]


class KanbanLeadCard(BaseModel):
    lead_code: str
    title: str
    stage_code: str
    owner_name: Optional[str] = None


class KanbanTenderCard(BaseModel):
    tender_code: str
    title: str
    pipeline_stage: Optional[str] = None
    forecast_amount: Optional[Decimal] = None
    forecast_currency: Optional[str] = None
    expected_close_on: Optional[date] = None
    tender_outcome: str
    owner_name: Optional[str] = None


class KanbanMasterQuotationCard(BaseModel):
    tender_code: str
    quotation_code: str
    title: str
    execution_state: str
    path_role: str


class KanbanTaskCard(BaseModel):
    id: Optional[str] = None
    kind: str = Field(description="crm | activity")
    title: str
    status_code: str
    due_on: Optional[date] = None
    due_at: Optional[datetime] = None
    tender_code: Optional[str] = None
    quotation_code: Optional[str] = None
    lead_code: Optional[str] = None


class KanbanBoardResponse(BaseModel):
    columns: Dict[str, List[Any]]
    column_order: List[str]


class PatchStageBody(BaseModel):
    stage_code: Optional[str] = None
    pipeline_stage: Optional[str] = None
    execution_state: Optional[str] = None
    status: Optional[str] = None


class PipelineDashboardMetrics(BaseModel):
    active_pipeline_value_by_stage: Dict[str, str]
    active_pipeline_currency: Optional[str] = None
    tender_count_by_stage: Dict[str, int]
    tenders_with_multiple_quotations: int
    master_quotation_count_by_execution: Dict[str, int]
    win_loss_counts: Dict[str, int]
    crm_tasks_overdue: int
    crm_tasks_due_soon: int
    activity_tasks_overdue: int
    activity_tasks_due_soon: int
    closest_to_closure: List[KanbanTenderCard]
    bottleneck_stage: Optional[str] = None
