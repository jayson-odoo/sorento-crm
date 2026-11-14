"""Register a CRM project in AutoCount (AC-PROJECT-REGISTER).

    GET  /project-sales/projects/{project_id}/autocount-register   (status)
    POST /project-sales/projects/{project_id}/autocount-register   (register, no body)

Check order: permission (`projects.autocount.write`) -> the admin switch "AutoCount project
registration" (403, and the Shared Service is never touched) -> the project, found in the
caller's company (404) -> write access (POST) -> eligibility (409) -> the Shared Service. The
company code and the project code come from the project, never from the request.

Every answer the Shared Service gave is a 200 with the result dict, a refusal included.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.projects.project_autocount_write import (
    WRITE,
    WriteResult,
    _assert_project_access,
    _guard,
    _run,
)
from app.database import get_db
from app.dependencies import require_permission
from app.models.user import SystemSetting
from app.services import project_service as projects
from app.services.error_handler import AppException
from app.services.project_autocount_register_service import ProjectAutocountRegisterService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

SWITCHED_OFF = "AutoCount project registration is switched off in Settings."


class RegisterStatus(BaseModel):
    registered: bool
    project_no: Optional[str] = None
    registered_at: Optional[datetime] = None
    eligible: bool
    can_register: bool
    reason: Optional[str] = None


def _require_switch(db: Session) -> None:
    row = db.query(SystemSetting).first()
    if not bool(getattr(row, "project_autocount_register_enabled", False)):
        raise AppException(status_code=403, message=SWITCHED_OFF, code="ac_register_switched_off")


@router.get("/projects/{project_id}/autocount-register", response_model=RegisterStatus)
def register_status(
    project_id: str,
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    _require_switch(db)
    validate_uuid_path(project_id, resource="Project")
    projects.get_project_or_404(db, project_id)
    try:
        return ProjectAutocountRegisterService(db).status(project_id)
    except Exception as exc:
        _guard(exc)


@router.post("/projects/{project_id}/autocount-register", response_model=WriteResult)
def register_project(
    project_id: str,
    current_user: dict = Depends(require_permission(WRITE)),
    db: Session = Depends(get_db),
):
    _require_switch(db)
    validate_uuid_path(project_id, resource="Project")
    _assert_project_access(db, project_id, current_user)
    return _run(db, lambda: ProjectAutocountRegisterService(db).register(project_id, current_user))
