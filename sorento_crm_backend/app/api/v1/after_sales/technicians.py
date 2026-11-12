"""Technician roster routes (after-sales P1)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_any_permission_with_api_key, require_permission
from app.schemas.common import MAX_PAGE_LIMIT
from app.schemas.service_jobs import TechnicianCreate, TechnicianUpdate
from app.services import technician_service
from app.utils.multi_value import multi_values

router = APIRouter()

VIEW = "after_sales.service_jobs.view"
MANAGE = "after_sales.technicians.manage"


# ai: not-for-assistant a plain staff roster (names and phones) feeding the Assign picker; no question is asked about it
@router.get("")
def list_technicians(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("asc", pattern="^(asc|desc)$"),
    employment_type: Optional[List[str]] = Query(None),
    is_active: Optional[List[str]] = Query(None),
    current_user: dict = Depends(require_any_permission_with_api_key([VIEW, MANAGE])),
    db: Session = Depends(get_db),
):
    return technician_service.list_technicians(
        db, page=page, limit=limit, query=query, sort=sort, direction=dir,
        employment_types=multi_values(employment_type, "type"),
        active_values=multi_values(is_active, "status"),
    )


@router.get("/{technician_id}")
def get_technician(
    technician_id: str,
    current_user: dict = Depends(require_any_permission_with_api_key([VIEW, MANAGE])),
    db: Session = Depends(get_db),
):
    return technician_service.serialize(technician_service.get(db, technician_id))


@router.post("", status_code=201)
def create_technician(
    payload: TechnicianCreate,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    return technician_service.create(db, payload)


@router.put("/{technician_id}")
def update_technician(
    technician_id: str,
    payload: TechnicianUpdate,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    return technician_service.update(db, technician_id, payload)


@router.delete("/{technician_id}")
def delete_technician(
    technician_id: str,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    return technician_service.delete(db, technician_id)
