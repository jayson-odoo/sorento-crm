"""Service job routes (after-sales P1). Mounted under /complaints-management with full paths."""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import MAX_PAGE_LIMIT
from app.schemas.service_jobs import AssignJobRequest, ConfirmJobRequest, TransitionJobRequest
from app.services import service_job_service as svc
from app.utils.multi_value import multi_values

router = APIRouter()

VIEW = "complaint_management.service_jobs.view"
DISPATCH = "complaint_management.service_jobs.dispatch"


def _limit(db: Session, current_user: dict):
    return svc.limit_for(db, str(current_user.get("id") or ""))


def _write_limit(db: Session, current_user: dict):
    svc.stamp_actor(db, current_user)
    return svc.limit_for(db, str(current_user.get("id") or ""), strict=False)


@router.get("/service-jobs")
def list_service_jobs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc", pattern="^(asc|desc)$"),
    status: Optional[List[str]] = Query(None),
    technician_id: Optional[List[str]] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    return svc.list_jobs(
        db,
        _limit(db, current_user),
        page=page,
        limit=limit,
        query=query,
        sort=sort,
        direction=dir,
        statuses=multi_values(status, "status"),
        technician_ids=multi_values(technician_id, "technician"),
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/service-jobs/board")
def service_job_board(
    day: date = Query(...),
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    return svc.board(db, _limit(db, current_user), day)


@router.get("/service-jobs/{job_id}")
def get_service_job(
    job_id: str,
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    return svc.get_job(db, job_id, _limit(db, current_user))


@router.post("/service-jobs/{job_id}/confirm")
def confirm_service_job(
    job_id: str,
    payload: ConfirmJobRequest,
    current_user: dict = Depends(require_permission(DISPATCH)),
    db: Session = Depends(get_db),
):
    return svc.confirm(
        db,
        job_id,
        scheduled_from=payload.scheduled_from,
        scheduled_to=payload.scheduled_to,
        customer_agreed_by=payload.customer_agreed_by,
        limit=_write_limit(db, current_user),
    )


@router.post("/service-jobs/{job_id}/assign")
def assign_service_job(
    job_id: str,
    payload: AssignJobRequest,
    current_user: dict = Depends(require_permission(DISPATCH)),
    db: Session = Depends(get_db),
):
    return svc.assign(db, job_id, payload.technician_id, _write_limit(db, current_user))


@router.post("/service-jobs/{job_id}/transition")
def transition_service_job(
    job_id: str,
    payload: TransitionJobRequest,
    current_user: dict = Depends(require_permission(DISPATCH)),
    db: Session = Depends(get_db),
):
    return svc.transition(db, job_id, payload.to, payload.reason, _write_limit(db, current_user))


@router.get("/complaints/{complaint_id}/service-jobs")
def list_complaint_service_jobs(
    complaint_id: str,
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    rows = svc.list_for_complaint(db, complaint_id, _limit(db, current_user))
    return {"data": rows, "pagination": {"total": len(rows), "page": 1, "limit": max(len(rows), 1)}}


@router.post("/complaints/{complaint_id}/service-jobs")
def raise_service_job(
    complaint_id: str,
    response: Response,
    current_user: dict = Depends(require_permission(DISPATCH)),
    db: Session = Depends(get_db),
):
    job, created = svc.raise_job(
        db, complaint_id, current_user.get("id"), _write_limit(db, current_user)
    )
    response.status_code = 201 if created else 200
    return job
