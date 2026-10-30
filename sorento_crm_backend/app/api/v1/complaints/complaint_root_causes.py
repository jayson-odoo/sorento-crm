"""Complaint root cause master data API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.services.uuid_path_param import validate_uuid_path
from app.dependencies import require_permission, require_permission_with_api_key
from app.services.complaint_master_data_service import ComplaintRootCauseService
from app.schemas.complaint_master_data import (
    ComplaintRootCauseCreate,
    ComplaintRootCauseUpdate,
    ComplaintRootCauseResponse,
    ComplaintRootCauseSimple,
)
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[ComplaintRootCauseResponse])
def get_complaint_root_causes(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key("master_data.complaint_root_causes.view")),
    db: Session = Depends(get_db),
):
    try:
        service = ComplaintRootCauseService(db)
        return service.list_root_causes(page=page, limit=limit, query=query, is_active=is_active)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/select", response_model=List[ComplaintRootCauseSimple])
def get_complaint_root_causes_select(
    query: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key("master_data.complaint_root_causes.view")),
    db: Session = Depends(get_db),
):
    """Active root causes for dropdowns."""
    try:
        from app.models.complaint_master_data import ComplaintRootCause
        q = db.query(ComplaintRootCause).filter(ComplaintRootCause.is_active.is_(True))
        if query:
            q = q.filter(ComplaintRootCause.name.ilike(f"%{query}%"))
        rows = q.order_by(ComplaintRootCause.name.asc()).limit(200).all()
        return rows
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{root_cause_id}", response_model=ComplaintRootCauseResponse)
def get_complaint_root_cause(
    root_cause_id: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.complaint_root_causes.view")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(root_cause_id, resource="Complaint Root Cause")
        service = ComplaintRootCauseService(db)
        return service.get_root_cause(root_cause_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=ComplaintRootCauseResponse, status_code=status.HTTP_201_CREATED)
def create_complaint_root_cause(
    payload: ComplaintRootCauseCreate,
    current_user: dict = Depends(require_permission("master_data.complaint_root_causes.add")),
    db: Session = Depends(get_db),
):
    try:
        service = ComplaintRootCauseService(db)
        return service.create_root_cause(payload)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{root_cause_id}", response_model=ComplaintRootCauseResponse)
def update_complaint_root_cause(
    root_cause_id: str,
    payload: ComplaintRootCauseUpdate,
    current_user: dict = Depends(require_permission("master_data.complaint_root_causes.edit")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(root_cause_id, resource="Complaint Root Cause")
        service = ComplaintRootCauseService(db)
        return service.update_root_cause(root_cause_id, payload)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{root_cause_id}", status_code=status.HTTP_200_OK)
def delete_complaint_root_cause(
    root_cause_id: str,
    current_user: dict = Depends(require_permission("master_data.complaint_root_causes.delete")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(root_cause_id, resource="Complaint Root Cause")
        service = ComplaintRootCauseService(db)
        return service.delete_root_cause(root_cause_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
