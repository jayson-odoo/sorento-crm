"""Warranty kind rule routes. Mounted under /after-sales/warranty/kind-rules."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.after_sales.warranty.access import can_read, can_write
from app.database import get_db
from app.schemas.common import MAX_PAGE_LIMIT
from app.schemas.warranty_config import KindRuleCreate, KindRuleTestRequest, KindRuleUpdate
from app.services import warranty_config_service as svc
from app.services.service_job_service import stamp_actor
from app.utils.multi_value import multi_uuids

router = APIRouter()


@router.get("")
def list_rules(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("asc", pattern="^(asc|desc)$"),
    kind_id: Optional[List[str]] = Query(None),
    current_user: dict = Depends(can_read),
    db: Session = Depends(get_db),
):
    return svc.list_rules(
        db, page=page, limit=limit, query=query, sort=sort, direction=dir, kind_ids=multi_uuids(kind_id, "kind")
    )


@router.post("/test")
def test_rules(payload: KindRuleTestRequest, current_user: dict = Depends(can_read), db: Session = Depends(get_db)):
    return svc.try_rules(db, payload.product_id)


@router.post("", status_code=201)
def create_rule(payload: KindRuleCreate, current_user: dict = Depends(can_write), db: Session = Depends(get_db)):
    stamp_actor(db, current_user)
    return svc.create_rule(db, payload)


@router.patch("/{rule_id}")
def update_rule(rule_id: str, payload: KindRuleUpdate, current_user: dict = Depends(can_write), db: Session = Depends(get_db)):
    stamp_actor(db, current_user)
    return svc.update_rule(db, rule_id, payload)


@router.delete("/{rule_id}")
def delete_rule(rule_id: str, current_user: dict = Depends(can_write), db: Session = Depends(get_db)):
    stamp_actor(db, current_user)
    return svc.delete_rule(db, rule_id)
