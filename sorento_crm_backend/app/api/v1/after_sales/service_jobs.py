"""Service job routes (after-sales P1). Mounted under /after-sales with full paths."""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import MAX_PAGE_LIMIT
from app.schemas.service_job_products import ServiceJobProductCreate, ServiceJobProductUpdate
from app.schemas.service_jobs import (
    AssignJobRequest,
    ConfirmJobRequest,
    ServiceJobCreate,
    ServiceJobUpdate,
    TransitionJobRequest,
)
from app.services import service_job_product_service as lines
from app.services import service_job_service as svc
from app.utils.multi_value import multi_choices, multi_values

router = APIRouter()

VIEW = "after_sales.service_jobs.view"
DISPATCH = "after_sales.service_jobs.dispatch"


@router.get("/service-jobs")
def list_service_jobs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc", pattern="^(asc|desc)$"),
    status: Optional[List[str]] = Query(None),
    technician_id: Optional[List[str]] = Query(None),
    warranty_summary: Optional[List[str]] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    return svc.list_jobs(
        db,
        page=page,
        limit=limit,
        query=query,
        sort=sort,
        direction=dir,
        statuses=multi_values(status, "status"),
        technician_ids=multi_values(technician_id, "technician"),
        warranty_summaries=multi_choices(warranty_summary, lines.SUMMARY_ORDER, "warranty_summary"),
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/service-jobs", status_code=201)
def create_service_job(
    payload: ServiceJobCreate,
    current_user: dict = Depends(require_permission(DISPATCH)),
    db: Session = Depends(get_db),
):
    svc.stamp_actor(db, current_user)
    return svc.create_job(db, payload.model_dump(exclude_unset=True), current_user.get("id"))


@router.get("/service-jobs/board")
def service_job_board(
    day: date = Query(...),
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    return svc.board(db, day)


@router.get("/service-jobs/{job_id}")
def get_service_job(
    job_id: str,
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    return svc.get_job(db, job_id)


@router.put("/service-jobs/{job_id}")
def update_service_job(
    job_id: str,
    payload: ServiceJobUpdate,
    current_user: dict = Depends(require_permission(DISPATCH)),
    db: Session = Depends(get_db),
):
    svc.stamp_actor(db, current_user)
    return svc.update_job(db, job_id, payload.model_dump(exclude_unset=True))


@router.post("/service-jobs/{job_id}/confirm")
def confirm_service_job(
    job_id: str,
    payload: ConfirmJobRequest,
    current_user: dict = Depends(require_permission(DISPATCH)),
    db: Session = Depends(get_db),
):
    svc.stamp_actor(db, current_user)
    return svc.confirm(
        db,
        job_id,
        scheduled_from=payload.scheduled_from,
        scheduled_to=payload.scheduled_to,
        customer_agreed_by=payload.customer_agreed_by,
    )


@router.post("/service-jobs/{job_id}/assign")
def assign_service_job(
    job_id: str,
    payload: AssignJobRequest,
    current_user: dict = Depends(require_permission(DISPATCH)),
    db: Session = Depends(get_db),
):
    svc.stamp_actor(db, current_user)
    return svc.assign(db, job_id, payload.technician_id)


@router.post("/service-jobs/{job_id}/transition")
def transition_service_job(
    job_id: str,
    payload: TransitionJobRequest,
    current_user: dict = Depends(require_permission(DISPATCH)),
    db: Session = Depends(get_db),
):
    svc.stamp_actor(db, current_user)
    return svc.transition(db, job_id, payload.to, payload.reason)


@router.get("/service-jobs/{job_id}/products")
def list_job_products(
    job_id: str,
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    return lines.list_lines(db, job_id)


@router.post("/service-jobs/{job_id}/products", status_code=201)
def add_job_product(
    job_id: str,
    payload: ServiceJobProductCreate,
    current_user: dict = Depends(require_permission(DISPATCH)),
    db: Session = Depends(get_db),
):
    svc.stamp_actor(db, current_user)
    return lines.add_line(db, job_id, payload)


@router.patch("/service-jobs/{job_id}/products/{line_id}")
def update_job_product(
    job_id: str,
    line_id: str,
    payload: ServiceJobProductUpdate,
    current_user: dict = Depends(require_permission(DISPATCH)),
    db: Session = Depends(get_db),
):
    svc.stamp_actor(db, current_user)
    return lines.update_line(db, job_id, line_id, payload)


@router.delete("/service-jobs/{job_id}/products/{line_id}")
def delete_job_product(
    job_id: str,
    line_id: str,
    current_user: dict = Depends(require_permission(DISPATCH)),
    db: Session = Depends(get_db),
):
    svc.stamp_actor(db, current_user)
    return lines.delete_line(db, job_id, line_id)
