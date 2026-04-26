"""Unified workflow_stages CRUD (all domains)."""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.modules.commercial_core.schemas.unified_workflow_stage import (
    UnifiedWorkflowStageCreate,
    UnifiedWorkflowStageResponse,
    UnifiedWorkflowStageUpdate,
    unified_workflow_stage_response,
)
from app.services.error_handler import handle_internal_error
from app.modules.commercial_core.services.unified_workflow_stage_service import (
    create_workflow_stage,
    delete_workflow_stage,
    get_workflow_stage,
    list_workflow_stages,
    update_workflow_stage,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=List[UnifiedWorkflowStageResponse])
async def list_unified_workflow_stages(
    domain: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    _user: dict = Depends(require_permission("commercial_process_config.settings.view")),
    db: Session = Depends(get_db),
):
    try:
        rows = list_workflow_stages(db, domain=domain, include_inactive=include_inactive)
        return [unified_workflow_stage_response(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=UnifiedWorkflowStageResponse, status_code=status.HTTP_201_CREATED)
async def create_unified_workflow_stage(
    data: UnifiedWorkflowStageCreate,
    _user: dict = Depends(require_permission("commercial_process_config.settings.edit")),
    db: Session = Depends(get_db),
):
    try:
        row = create_workflow_stage(db, data)
        return unified_workflow_stage_response(row)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{stage_id}", response_model=UnifiedWorkflowStageResponse)
async def get_unified_workflow_stage(
    stage_id: str,
    _user: dict = Depends(require_permission("commercial_process_config.settings.view")),
    db: Session = Depends(get_db),
):
    try:
        row = get_workflow_stage(db, stage_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow stage not found")
        return unified_workflow_stage_response(row)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{stage_id}", response_model=UnifiedWorkflowStageResponse)
async def patch_unified_workflow_stage(
    stage_id: str,
    data: UnifiedWorkflowStageUpdate,
    _user: dict = Depends(require_permission("commercial_process_config.settings.edit")),
    db: Session = Depends(get_db),
):
    try:
        row = update_workflow_stage(db, stage_id, data)
        return unified_workflow_stage_response(row)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unified_workflow_stage(
    stage_id: str,
    _user: dict = Depends(require_permission("commercial_process_config.settings.edit")),
    db: Session = Depends(get_db),
):
    try:
        delete_workflow_stage(db, stage_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("workflow-stages delete: %s", e)
        raise handle_internal_error(str(e))
