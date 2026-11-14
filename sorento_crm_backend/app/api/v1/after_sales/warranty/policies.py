"""Warranty policy routes. Mounted under /after-sales/warranty/policies."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.after_sales.warranty.access import can_read, can_write
from app.database import get_db
from app.schemas.common import MAX_PAGE_LIMIT
from app.schemas.warranty_config import PolicyCreate, PolicyUpdate, SupersedeRequest
from app.services import warranty_config_service as svc
from app.services.service_job_service import stamp_actor

router = APIRouter()


@router.get("")
def list_policies(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: dict = Depends(can_read),
    db: Session = Depends(get_db),
):
    return svc.list_policies(db, page=page, limit=limit, query=query, sort=sort, direction=dir)


@router.post("", status_code=201)
def create_policy(payload: PolicyCreate, current_user: dict = Depends(can_write), db: Session = Depends(get_db)):
    stamp_actor(db, current_user)
    return svc.create_policy(db, payload)


@router.get("/{policy_id}")
def get_policy(policy_id: str, current_user: dict = Depends(can_read), db: Session = Depends(get_db)):
    return svc.get_policy(db, policy_id)


@router.patch("/{policy_id}")
def update_policy(
    policy_id: str, payload: PolicyUpdate, current_user: dict = Depends(can_write), db: Session = Depends(get_db)
):
    stamp_actor(db, current_user)
    return svc.update_policy(db, policy_id, payload)


@router.delete("/{policy_id}")
def delete_policy(policy_id: str, current_user: dict = Depends(can_write), db: Session = Depends(get_db)):
    stamp_actor(db, current_user)
    return svc.delete_policy(db, policy_id)


@router.post("/{policy_id}/supersede")
def supersede_policy(
    policy_id: str, payload: SupersedeRequest, current_user: dict = Depends(can_write), db: Session = Depends(get_db)
):
    stamp_actor(db, current_user)
    return svc.supersede_policy(db, policy_id, payload)
