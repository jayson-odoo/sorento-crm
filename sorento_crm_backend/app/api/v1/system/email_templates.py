"""Email templates CRUD + preview API."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT, SuccessResponse
from app.schemas.email_template import (
    EmailTemplateCreate,
    EmailTemplatePreviewRequest,
    EmailTemplatePreviewResponse,
    EmailTemplateResponse,
    EmailTemplateUpdate,
    TemplateVariable,
    TemplateVariablesCatalog,
)
from app.services.email_template_service import (
    TEMPLATE_VARIABLE_CATALOG,
    EmailTemplateService,
)

router = APIRouter()


@router.get("/email-templates", response_model=ListResponse[EmailTemplateResponse])
async def list_email_templates(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: dict = Depends(require_permission("email_templates.templates.view")),
    db: Session = Depends(get_db),
):
    rows, total = EmailTemplateService(db).list(
        page=page, limit=limit, query=query, is_active=is_active
    )
    return {
        "data": [EmailTemplateResponse.model_validate(r) for r in rows],
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }


@router.get("/email-templates/variables/catalog", response_model=TemplateVariablesCatalog)
async def get_email_template_variable_catalog(
    current_user: dict = Depends(require_permission("email_templates.templates.view")),
):
    return TemplateVariablesCatalog(
        variables=[TemplateVariable(**v) for v in TEMPLATE_VARIABLE_CATALOG]
    )


@router.get("/email-templates/{template_id}", response_model=EmailTemplateResponse)
async def get_email_template(
    template_id: str,
    current_user: dict = Depends(require_permission("email_templates.templates.view")),
    db: Session = Depends(get_db),
):
    service = EmailTemplateService(db)
    row = service.get(template_id)
    if not row:
        from app.services.error_handler import AppException

        raise AppException(status_code=404, message="Email template not found")
    return EmailTemplateResponse.model_validate(row)


@router.post("/email-templates", response_model=EmailTemplateResponse, status_code=201)
async def create_email_template(
    payload: EmailTemplateCreate,
    current_user: dict = Depends(require_permission("email_templates.templates.add")),
    db: Session = Depends(get_db),
):
    service = EmailTemplateService(db)
    row = service.create(
        payload.model_dump(),
        user_id=str(current_user.get("id")) if current_user else None,
    )
    return EmailTemplateResponse.model_validate(row)


@router.put("/email-templates/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template(
    template_id: str,
    payload: EmailTemplateUpdate,
    current_user: dict = Depends(require_permission("email_templates.templates.edit")),
    db: Session = Depends(get_db),
):
    row = EmailTemplateService(db).update(
        template_id, payload.model_dump(exclude_unset=True)
    )
    return EmailTemplateResponse.model_validate(row)


@router.delete("/email-templates/{template_id}", response_model=SuccessResponse)
async def delete_email_template(
    template_id: str,
    current_user: dict = Depends(require_permission("email_templates.templates.delete")),
    db: Session = Depends(get_db),
):
    EmailTemplateService(db).delete(template_id)
    return {"message": "Email template deleted"}


@router.post(
    "/email-templates/{template_id}/preview",
    response_model=EmailTemplatePreviewResponse,
)
async def preview_email_template(
    template_id: str,
    payload: EmailTemplatePreviewRequest,
    current_user: dict = Depends(require_permission("email_templates.templates.view")),
    db: Session = Depends(get_db),
):
    rendered = EmailTemplateService(db).preview(template_id, payload.context)
    return EmailTemplatePreviewResponse(**rendered)
