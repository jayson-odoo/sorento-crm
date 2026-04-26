"""Commercial pipeline: Kanban boards, filters, dashboard metrics."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.modules.commercial_core.schemas.commercial_pipeline import (
    KanbanBoardResponse,
    PatchStageBody,
    PipelineDashboardMetrics,
    StageConfigResponse,
)
from app.modules.commercial_core.services.commercial_pipeline_service import CommercialPipelineService
from app.services.error_handler import handle_internal_error
from app.services.user_service import UserPermissionService

router = APIRouter()


def _require_perm(slug: str):
    def _inner(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
        svc = UserPermissionService(db)
        uid = current_user["id"]
        if svc.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
            return current_user
        if not svc.check_user_has_permission(uid, slug):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {slug}")
        return current_user

    return _inner


@router.get("/stage-config", response_model=StageConfigResponse)
async def get_stage_config(
    _user: dict = Depends(_require_perm("commercial_core.leads.view")),
    db: Session = Depends(get_db),
):
    try:
        data = CommercialPipelineService(db).get_stage_config()
        return StageConfigResponse(**data)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/kanban/leads", response_model=KanbanBoardResponse)
async def kanban_leads(
    scope: Literal["mine", "all"] = Query("all"),
    stage_code: Optional[str] = Query(None),
    _user: dict = Depends(_require_perm("commercial_core.leads.view")),
    db: Session = Depends(get_db),
):
    try:
        cols, order = CommercialPipelineService(db).list_leads_kanban(
            user_id=_user["id"], scope=scope, stage_code=stage_code
        )
        return KanbanBoardResponse(columns=cols, column_order=order)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/kanban/tenders", response_model=KanbanBoardResponse)
async def kanban_tenders(
    scope: Literal["mine", "all"] = Query("all"),
    pipeline_stage: Optional[str] = Query(None),
    tender_outcome: Optional[str] = Query(None),
    _user: dict = Depends(_require_perm("commercial_core.tenders.view")),
    db: Session = Depends(get_db),
):
    try:
        cols, order = CommercialPipelineService(db).list_tenders_kanban(
            user_id=_user["id"],
            scope=scope,
            pipeline_stage=pipeline_stage,
            outcome=tender_outcome,
        )
        return KanbanBoardResponse(columns=cols, column_order=order)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/kanban/master-quotations", response_model=KanbanBoardResponse)
async def kanban_master_quotations(
    scope: Literal["mine", "all"] = Query("all"),
    execution_state: Optional[str] = Query(None),
    _user: dict = Depends(_require_perm("commercial_core.master_quotations.view")),
    db: Session = Depends(get_db),
):
    try:
        cols, order = CommercialPipelineService(db).list_master_quotations_kanban(
            user_id=_user["id"], scope=scope, execution_state=execution_state
        )
        return KanbanBoardResponse(columns=cols, column_order=order)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/kanban/tasks", response_model=KanbanBoardResponse)
async def kanban_tasks(
    scope: Literal["mine", "all"] = Query("all"),
    overdue_only: bool = Query(False),
    due_soon_only: bool = Query(False),
    due_soon_days: int = Query(7, ge=1, le=90),
    include_activity: bool = Query(True),
    _user: dict = Depends(_require_perm("commercial_core.pipeline_tasks.view")),
    db: Session = Depends(get_db),
):
    try:
        cols, order = CommercialPipelineService(db).list_tasks_kanban(
            user_id=_user["id"],
            scope=scope,
            overdue_only=overdue_only,
            due_soon_only=due_soon_only,
            due_soon_days=due_soon_days,
            include_activity=include_activity,
        )
        return KanbanBoardResponse(columns=cols, column_order=order)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/dashboard/metrics", response_model=PipelineDashboardMetrics)
async def dashboard_metrics(
    scope: Literal["mine", "all"] = Query("all"),
    _user: dict = Depends(_require_perm("commercial_core.pipeline_dashboard.view")),
    db: Session = Depends(get_db),
):
    try:
        data = CommercialPipelineService(db).get_dashboard_metrics(
            user_id=_user["id"],
            scope=scope,
        )
        return PipelineDashboardMetrics(**data)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/kanban/leads/{lead_code}/stage")
async def patch_lead_stage(
    lead_code: str,
    body: PatchStageBody,
    _user: dict = Depends(_require_perm("commercial_core.leads.edit")),
    db: Session = Depends(get_db),
):
    if not body.stage_code:
        raise HTTPException(status_code=400, detail="stage_code is required")
    try:
        CommercialPipelineService(db).patch_lead_stage(lead_code=lead_code, stage_code=body.stage_code)
        return {"ok": True}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/kanban/tenders/{tender_code}/pipeline")
async def patch_tender_pipeline(
    tender_code: str,
    body: PatchStageBody,
    _user: dict = Depends(_require_perm("commercial_core.tenders.edit")),
    db: Session = Depends(get_db),
):
    try:
        CommercialPipelineService(db).patch_tender_pipeline(
            tender_code=tender_code, pipeline_stage=body.pipeline_stage
        )
        return {"ok": True}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/kanban/tenders/{tender_code}/master-quotations/{quotation_code}/execution")
async def patch_mq_execution(
    tender_code: str,
    quotation_code: str,
    body: PatchStageBody,
    _user: dict = Depends(_require_perm("commercial_core.master_quotations.edit")),
    db: Session = Depends(get_db),
):
    if not body.execution_state:
        raise HTTPException(status_code=400, detail="execution_state is required")
    try:
        result = CommercialPipelineService(db).patch_master_quotation_execution(
            tender_code=tender_code,
            quotation_code=quotation_code,
            execution_state=body.execution_state,
            actor_user_id=_user["id"],
        )
        return {"ok": True, **result}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/kanban/tasks/{task_id}/status")
async def patch_task_status(
    task_id: str,
    body: PatchStageBody,
    _user: dict = Depends(_require_perm("commercial_core.pipeline_tasks.edit")),
    db: Session = Depends(get_db),
):
    if not body.status:
        raise HTTPException(status_code=400, detail="status is required")
    try:
        CommercialPipelineService(db).patch_pipeline_task_status(task_id=task_id, status=body.status)
        return {"ok": True}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise handle_internal_error(str(e))
