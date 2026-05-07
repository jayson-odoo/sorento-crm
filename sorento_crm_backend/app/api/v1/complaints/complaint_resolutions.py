"""Complaint resolution master data API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.services.complaint_master_data_service import ComplaintResolutionService
from app.schemas.complaint_master_data import (
    ComplaintResolutionCreate,
    ComplaintResolutionUpdate,
    ComplaintResolutionResponse,
    ComplaintResolutionSimple,
)
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[ComplaintResolutionResponse])
async def get_complaint_resolutions(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key("master_data.complaint_resolutions.view")),
    db: Session = Depends(get_db),
):
    try:
        service = ComplaintResolutionService(db)
        return service.list_resolutions(page=page, limit=limit, query=query, is_active=is_active)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/select", response_model=List[ComplaintResolutionSimple])
async def get_complaint_resolutions_select(
    query: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key("master_data.complaint_resolutions.view")),
    db: Session = Depends(get_db),
):
    """Active resolutions for dropdowns."""
    try:
        from app.models.complaint_master_data import ComplaintResolution
        q = db.query(ComplaintResolution).filter(ComplaintResolution.is_active.is_(True))
        if query:
            q = q.filter(ComplaintResolution.name.ilike(f"%{query}%"))
        rows = q.order_by(ComplaintResolution.name.asc()).limit(200).all()
        return rows
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{resolution_id}", response_model=ComplaintResolutionResponse)
async def get_complaint_resolution(
    resolution_id: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.complaint_resolutions.view")),
    db: Session = Depends(get_db),
):
    try:
        service = ComplaintResolutionService(db)
        return service.get_resolution(resolution_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=ComplaintResolutionResponse, status_code=status.HTTP_201_CREATED)
async def create_complaint_resolution(
    payload: ComplaintResolutionCreate,
    current_user: dict = Depends(require_permission("master_data.complaint_resolutions.add")),
    db: Session = Depends(get_db),
):
    try:
        service = ComplaintResolutionService(db)
        return service.create_resolution(payload)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{resolution_id}", response_model=ComplaintResolutionResponse)
async def update_complaint_resolution(
    resolution_id: str,
    payload: ComplaintResolutionUpdate,
    current_user: dict = Depends(require_permission("master_data.complaint_resolutions.edit")),
    db: Session = Depends(get_db),
):
    try:
        service = ComplaintResolutionService(db)
        return service.update_resolution(resolution_id, payload)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{resolution_id}", status_code=status.HTTP_200_OK)
async def delete_complaint_resolution(
    resolution_id: str,
    current_user: dict = Depends(require_permission("master_data.complaint_resolutions.delete")),
    db: Session = Depends(get_db),
):
    try:
        service = ComplaintResolutionService(db)
        return service.delete_resolution(resolution_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
