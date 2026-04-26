"""Configurable commercial lead stages."""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional, require_permission, require_permission_with_api_key
from app.modules.commercial_core.schemas.commercial import (
    CommercialLeadStageCreate,
    CommercialLeadStageResponse,
    CommercialLeadStageUpdate,
    commercial_lead_stage_response_from_workflow,
)
from app.modules.commercial_core.services.commercial_lead_service import CommercialLeadStageService
from app.services.error_handler import handle_internal_error

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/select")
def select_lead_stages(
    current_user: dict | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        svc = CommercialLeadStageService(db)
        rows = svc.list_stages()
        data = [{"code": r.code, "label": r.label} for r in rows]
        return {"data": data, "pagination": {"total": len(data), "page": 1, "limit": len(data)}, "empty": len(data) == 0}
    except Exception as e:
        logger.exception("lead-stages/select: %s", e)
        return {"data": [], "pagination": {"total": 0, "page": 1, "limit": 0}, "empty": True}


@router.get("/by-code/{stage_code}", response_model=CommercialLeadStageResponse)
async def get_lead_stage_by_code(
    stage_code: str,
    _user: dict = Depends(require_permission_with_api_key("commercial_core.lead_stages.view")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadStageService(db)
        row = svc.get_stage_by_code(stage_code)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead stage not found")
        return commercial_lead_stage_response_from_workflow(row)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/by-code/{stage_code}", response_model=CommercialLeadStageResponse)
async def update_lead_stage_by_code(
    stage_code: str,
    data: CommercialLeadStageUpdate,
    _user: dict = Depends(require_permission("commercial_core.lead_stages.edit")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadStageService(db)
        row = svc.update_stage_by_code(stage_code, data)
        return commercial_lead_stage_response_from_workflow(row)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/by-code/{stage_code}", status_code=status.HTTP_200_OK)
async def delete_lead_stage_by_code(
    stage_code: str,
    _user: dict = Depends(require_permission("commercial_core.lead_stages.delete")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadStageService(db)
        svc.delete_stage_by_code(stage_code)
        return {"message": "Lead stage deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/", response_model=List[CommercialLeadStageResponse])
async def list_lead_stages(
    _user: dict = Depends(require_permission("commercial_core.lead_stages.view")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadStageService(db)
        return [commercial_lead_stage_response_from_workflow(r) for r in svc.list_stages()]
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=CommercialLeadStageResponse, status_code=status.HTTP_201_CREATED)
async def create_lead_stage(
    data: CommercialLeadStageCreate,
    _user: dict = Depends(require_permission("commercial_core.lead_stages.add")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadStageService(db)
        row = svc.create_stage(data)
        return commercial_lead_stage_response_from_workflow(row)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{stage_id}", response_model=CommercialLeadStageResponse)
async def update_lead_stage(
    stage_id: str,
    data: CommercialLeadStageUpdate,
    _user: dict = Depends(require_permission("commercial_core.lead_stages.edit")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadStageService(db)
        row = svc.update_stage(stage_id, data)
        return commercial_lead_stage_response_from_workflow(row)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead_stage(
    stage_id: str,
    _user: dict = Depends(require_permission("commercial_core.lead_stages.delete")),
    db: Session = Depends(get_db),
):
    try:
        svc = CommercialLeadStageService(db)
        svc.delete_stage(stage_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
