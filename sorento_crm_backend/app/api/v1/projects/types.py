"""Project type and template configuration API - UAC Group C (AC-C1, AC-C2)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import acting_company_id
from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import ListResponse
from app.schemas.projects import (
    ProjectTemplateCreate,
    ProjectTemplateResponse,
    ProjectTemplateUpdate,
    ProjectTypeCreate,
    ProjectTypeResponse,
    ProjectTypeUpdate,
)
from app.services import project_reference_service as refs
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "projects.types.view"
EDIT = "projects.types.edit"


@router.get("/types", response_model=ListResponse[ProjectTypeResponse])
async def list_types(
    include_inactive: bool = Query(False),
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        rows = refs.list_types(
            db, company_id=acting_company_id(db), include_inactive=include_inactive
        )
        data = refs.serialize_types(db, rows)
        return {
            "data": data,
            "pagination": {"total": len(data), "page": 1, "limit": max(len(data), 1)},
            "empty": not data,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/types", response_model=ProjectTypeResponse, status_code=status.HTTP_201_CREATED
)
async def create_type(
    payload: ProjectTypeCreate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        project_type = refs.create_type(
            db,
            company_id=acting_company_id(db),
            payload=payload.model_dump(exclude_unset=True),
        )
        db.commit()
        db.refresh(project_type)
        return refs.serialize_types(db, [project_type])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put("/types/{type_id}", response_model=ProjectTypeResponse)
async def update_type(
    type_id: str,
    payload: ProjectTypeUpdate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(type_id, resource="Project Type")
        project_type = refs.get_type_or_404(db, type_id)
        refs.update_type(db, project_type, payload.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(project_type)
        return refs.serialize_types(db, [project_type])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/types/{type_id}")
async def delete_type(
    type_id: str,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(type_id, resource="Project Type")
        project_type = refs.get_type_or_404(db, type_id)
        name = project_type.name
        refs.delete_type(db, project_type)
        db.commit()
        return {"message": f"{name} deleted"}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/templates", response_model=ListResponse[ProjectTemplateResponse])
async def list_templates(
    type_id: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        rows = refs.list_templates(
            db,
            company_id=acting_company_id(db),
            type_id=type_id,
            include_inactive=include_inactive,
        )
        data = refs.serialize_templates(db, rows)
        return {
            "data": data,
            "pagination": {"total": len(data), "page": 1, "limit": max(len(data), 1)},
            "empty": not data,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/templates",
    response_model=ProjectTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    payload: ProjectTemplateCreate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        template = refs.create_template(
            db,
            company_id=acting_company_id(db),
            payload=payload.model_dump(exclude_unset=True),
        )
        db.commit()
        db.refresh(template)
        return refs.serialize_templates(db, [template])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put("/templates/{template_id}", response_model=ProjectTemplateResponse)
async def update_template(
    template_id: str,
    payload: ProjectTemplateUpdate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(template_id, resource="Project Template")
        template = refs.get_template_or_404(db, template_id)
        refs.update_template(db, template, payload.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(template)
        return refs.serialize_templates(db, [template])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(template_id, resource="Project Template")
        template = refs.get_template_or_404(db, template_id)
        name = template.name
        refs.delete_template(db, template)
        db.commit()
        return {"message": f"{name} deleted"}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
