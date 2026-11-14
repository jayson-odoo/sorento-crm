"""Warranty product kind routes. Mounted under /after-sales/warranty/kinds."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.after_sales.warranty.access import can_read, can_write
from app.database import get_db
from app.schemas.common import MAX_PAGE_LIMIT
from app.schemas.warranty_config import KindCreate, KindUpdate
from app.services import warranty_config_service as svc
from app.services.service_job_service import stamp_actor
from app.utils.multi_value import multi_values

router = APIRouter()


@router.get("")
def list_kinds(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("asc", pattern="^(asc|desc)$"),
    is_active: Optional[List[str]] = Query(None),
    has_no_rule: bool = Query(False),
    current_user: dict = Depends(can_read),
    db: Session = Depends(get_db),
):
    return svc.list_kinds(
        db,
        page=page,
        limit=limit,
        query=query,
        sort=sort,
        direction=dir,
        active_values=multi_values(is_active, "status"),
        has_no_rule=has_no_rule,
    )


@router.post("", status_code=201)
def create_kind(payload: KindCreate, current_user: dict = Depends(can_write), db: Session = Depends(get_db)):
    stamp_actor(db, current_user)
    return svc.create_kind(db, payload)


@router.get("/{kind_id}")
def get_kind(kind_id: str, current_user: dict = Depends(can_read), db: Session = Depends(get_db)):
    return svc.get_kind(db, kind_id)


@router.patch("/{kind_id}")
def update_kind(kind_id: str, payload: KindUpdate, current_user: dict = Depends(can_write), db: Session = Depends(get_db)):
    stamp_actor(db, current_user)
    return svc.update_kind(db, kind_id, payload)


@router.delete("/{kind_id}")
def delete_kind(kind_id: str, current_user: dict = Depends(can_write), db: Session = Depends(get_db)):
    stamp_actor(db, current_user)
    return svc.delete_kind(db, kind_id)
