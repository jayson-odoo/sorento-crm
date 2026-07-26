"""Project task API (S2b, UAC Group N).

Status moves go through their own endpoint rather than the generic PUT, because
Escalate and Stuck must carry their context in the SAME request as the move: two calls
would leave a window where a task is escalated to nobody, and a client that died
between them would leave it that way permanently.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import acting_company_id, permission_slugs
from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import MAX_PAGE_LIMIT, ListResponse
from app.schemas.projects import (
    ProjectTaskCreate,
    ProjectTaskHistoryEntry,
    ProjectTaskResponse,
    ProjectTaskStatusChangeRequest,
    ProjectTaskUpdate,
    ProjectTemplateTaskCreate,
    ProjectTemplateTaskResponse,
    ProjectTemplateTaskUpdate,
)
from app.services import project_reference_service as refs
from app.services import project_service as projects
from app.services import project_task_service as svc
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"
CONFIG_VIEW = "projects.types.view"
CONFIG_EDIT = "projects.types.edit"


def _envelope(data: List[dict], total: Optional[int] = None, page: int = 1, limit: int = 50):
    resolved = len(data) if total is None else total
    return {
        "data": data,
        "pagination": {"total": resolved, "page": page, "limit": max(limit, 1)},
        "empty": resolved == 0,
    }


# ------------------------------------------------------------- project tasks


@router.get(
    "/projects/{project_id}/tasks", response_model=ListResponse[ProjectTaskResponse]
)
async def list_project_tasks(
    project_id: str,
    task_phase: Optional[str] = Query(
        None, description="pursuit | delivery. Omit for both."
    ),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        project = projects.get_project_or_404(db, project_id)
        rows = svc.list_tasks(db, project_id=project_id, task_phase=task_phase)
        data = svc.serialize_tasks(
            db,
            rows,
            actor_user_id=current_user["id"],
            permissions=permission_slugs(db, current_user["id"]),
            projects_by_id={project.id: project},
        )
        return _envelope(data)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/projects/{project_id}/tasks",
    response_model=ProjectTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_task(
    project_id: str,
    payload: ProjectTaskCreate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        project = projects.get_project_or_404(db, project_id)
        permissions = permission_slugs(db, current_user["id"])
        task = svc.create_task(
            db,
            project=project,
            payload=payload.model_dump(exclude_unset=True),
            actor_user_id=current_user["id"],
            permissions=permissions,
        )
        db.commit()
        db.refresh(task)
        return svc.serialize_tasks(
            db,
            [task],
            actor_user_id=current_user["id"],
            permissions=permissions,
            projects_by_id={project.id: project},
        )[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(
    "/projects/{project_id}/tasks/{task_id}", response_model=ProjectTaskResponse
)
async def update_project_task(
    project_id: str,
    task_id: str,
    payload: ProjectTaskUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        validate_uuid_path(task_id, resource="Task")
        project = projects.get_project_or_404(db, project_id)
        task = svc.get_task_or_404(db, project_id, task_id)
        permissions = permission_slugs(db, current_user["id"])
        svc.update_task(
            db,
            task=task,
            project=project,
            payload=payload.model_dump(exclude_unset=True),
            actor_user_id=current_user["id"],
            permissions=permissions,
        )
        db.commit()
        db.refresh(task)
        return svc.serialize_tasks(
            db,
            [task],
            actor_user_id=current_user["id"],
            permissions=permissions,
            projects_by_id={project.id: project},
        )[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/projects/{project_id}/tasks/{task_id}/status",
    response_model=ProjectTaskResponse,
)
async def change_project_task_status(
    project_id: str,
    task_id: str,
    payload: ProjectTaskStatusChangeRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Escalate needs a person, Stuck needs a reason (AC-N4a), enforced here.

    The dialog in the UI is a convenience. This is the guarantee.
    """
    try:
        validate_uuid_path(project_id, resource="Project")
        validate_uuid_path(task_id, resource="Task")
        project = projects.get_project_or_404(db, project_id)
        task = svc.get_task_or_404(db, project_id, task_id)
        permissions = permission_slugs(db, current_user["id"])
        svc.change_task_status(
            db,
            task=task,
            project=project,
            to_status_id=payload.to_status_id,
            actor_user_id=current_user["id"],
            permissions=permissions,
            escalated_to_user_id=payload.escalated_to_user_id,
            stuck_reason=payload.stuck_reason,
        )
        db.commit()
        db.refresh(task)
        return svc.serialize_tasks(
            db,
            [task],
            actor_user_id=current_user["id"],
            permissions=permissions,
            projects_by_id={project.id: project},
        )[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/projects/{project_id}/tasks/{task_id}")
async def delete_project_task(
    project_id: str,
    task_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        validate_uuid_path(task_id, resource="Task")
        project = projects.get_project_or_404(db, project_id)
        task = svc.get_task_or_404(db, project_id, task_id)
        name = task.name
        svc.delete_task(
            db,
            task=task,
            project=project,
            actor_user_id=current_user["id"],
            permissions=permission_slugs(db, current_user["id"]),
        )
        db.commit()
        return {"message": f'"{name}" deleted'}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/projects/{project_id}/tasks/{task_id}/history",
    response_model=ListResponse[ProjectTaskHistoryEntry],
)
async def project_task_history(
    project_id: str,
    task_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """AC-N7. Read from the audit trail, not a bespoke history table."""
    try:
        validate_uuid_path(project_id, resource="Project")
        validate_uuid_path(task_id, resource="Task")
        projects.get_project_or_404(db, project_id)
        svc.get_task_or_404(db, project_id, task_id)
        return _envelope(svc.task_history(db, task_id))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ------------------------------------------------------------------ my tasks


@router.get("/my-tasks", response_model=ListResponse[ProjectTaskResponse])
async def list_my_tasks(
    include_unassigned_owned: bool = Query(
        False,
        description=(
            "Also include unassigned tasks on projects you own -- still your problem, "
            "otherwise invisible until someone opens the project."
        ),
    ),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """One person's open work across every project, overdue first (AC-N9).

    Deliberately not an ecohub pattern: its tasks live inside a single project because
    its user works one project at a time. Sorento salespeople hold dozens of concurrent
    pursuits.
    """
    try:
        company_id = acting_company_id(db)
        rows, total = svc.my_tasks(
            db,
            user_id=current_user["id"],
            company_id=company_id,
            include_unassigned_owned=include_unassigned_owned,
            page=page,
            limit=limit,
        )
        data = svc.serialize_tasks(
            db,
            rows,
            actor_user_id=current_user["id"],
            permissions=permission_slugs(db, current_user["id"]),
        )
        return _envelope(data, total=total, page=page, limit=limit)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ------------------------------------------------- template checklist admin


@router.get(
    "/config/templates/{template_id}/tasks",
    response_model=ListResponse[ProjectTemplateTaskResponse],
)
async def list_template_tasks(
    template_id: str,
    include_inactive: bool = Query(True),
    _user: dict = Depends(require_permission(CONFIG_VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(template_id, resource="Project Template")
        refs.get_template_or_404(db, template_id)
        rows = svc.list_template_tasks(
            db, template_id=template_id, include_inactive=include_inactive
        )
        return _envelope(svc.serialize_template_tasks(db, rows))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/config/templates/{template_id}/tasks",
    response_model=ProjectTemplateTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template_task(
    template_id: str,
    payload: ProjectTemplateTaskCreate,
    _user: dict = Depends(require_permission(CONFIG_EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(template_id, resource="Project Template")
        template = refs.get_template_or_404(db, template_id)
        row = svc.create_template_task(
            db,
            template_id=template.id,
            company_id=template.company_id or acting_company_id(db),
            payload=payload.model_dump(exclude_unset=True),
        )
        db.commit()
        db.refresh(row)
        return svc.serialize_template_tasks(db, [row])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(
    "/config/templates/{template_id}/tasks/{template_task_id}",
    response_model=ProjectTemplateTaskResponse,
)
async def update_template_task(
    template_id: str,
    template_task_id: str,
    payload: ProjectTemplateTaskUpdate,
    _user: dict = Depends(require_permission(CONFIG_EDIT)),
    db: Session = Depends(get_db),
):
    """Edits the template only. It never retro-applies to live projects (AC-N11)."""
    try:
        validate_uuid_path(template_id, resource="Project Template")
        validate_uuid_path(template_task_id, resource="Checklist item")
        refs.get_template_or_404(db, template_id)
        row = svc.get_template_task_or_404(db, template_task_id)
        svc.update_template_task(
            db, template_task=row, payload=payload.model_dump(exclude_unset=True)
        )
        db.commit()
        db.refresh(row)
        return svc.serialize_template_tasks(db, [row])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/config/templates/{template_id}/tasks/{template_task_id}")
async def delete_template_task(
    template_id: str,
    template_task_id: str,
    _user: dict = Depends(require_permission(CONFIG_EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(template_id, resource="Project Template")
        validate_uuid_path(template_task_id, resource="Checklist item")
        refs.get_template_or_404(db, template_id)
        row = svc.get_template_task_or_404(db, template_task_id)
        name = row.name
        svc.delete_template_task(db, template_task=row)
        db.commit()
        return {"message": f'"{name}" removed from the checklist'}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
