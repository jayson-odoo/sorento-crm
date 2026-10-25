"""Project registration queue (PROJECT-REG-PORTAL): list, read, approve, reject.

Mounted BEFORE the projects router (api/v1/projects/__init__.py): `/projects/registrations`
is a literal segment that `/projects/{project_id}` must not capture. Every route needs
`projects.registrations.approve`; the rules live in `project_registration_service`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.projects._common import acting_company_id  # noqa: F401  (company is on the row)
from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import MAX_PAGE_LIMIT
from app.schemas.projects import ProjectRegisterRequest
from app.services import project_registration_service as svc
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

APPROVE = svc.APPROVE_PERMISSION


class RejectBody(BaseModel):
    reason: str


def _load(db: Session, registration_id: str):
    return svc.get_or_404(db, validate_uuid_path(registration_id, resource="Project registration"))


@router.get("/")
async def list_registrations(
    status_filter: Optional[str] = Query(None, alias="status"),
    query: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=MAX_PAGE_LIMIT),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    _user: dict = Depends(require_permission(APPROVE)),
    db: Session = Depends(get_db),
):
    return svc.list_rows(
        db, status=status_filter, query=query, page=page, limit=limit, sort=sort, direction=dir
    )


@router.get("/{registration_id}")
async def get_registration(
    registration_id: str,
    _user: dict = Depends(require_permission(APPROVE)),
    db: Session = Depends(get_db),
):
    return svc.detail(db, _load(db, registration_id))


@router.post("/{registration_id}/approve")
async def approve_registration(
    registration_id: str,
    payload: ProjectRegisterRequest,
    user: dict = Depends(require_permission(APPROVE)),
    db: Session = Depends(get_db),
):
    try:
        row = svc.approve(
            db,
            _load(db, registration_id),
            payload.model_dump(exclude_unset=True),
            actor_user_id=user["id"],
        )
        db.commit()
        db.refresh(row)
        svc.notify(db, row, "approved")
        return svc.detail(db, row)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/{registration_id}/reject")
async def reject_registration(
    registration_id: str,
    payload: RejectBody,
    user: dict = Depends(require_permission(APPROVE)),
    db: Session = Depends(get_db),
):
    try:
        row = svc.reject(db, _load(db, registration_id), payload.reason, actor_user_id=user["id"])
        db.commit()
        db.refresh(row)
        svc.notify(db, row, "rejected")
        return svc.detail(db, row)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
