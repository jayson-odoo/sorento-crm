"""Email templates CRUD + preview API.

Plain `def` handlers on purpose: rendering is CPU-bound Jinja, and FastAPI runs a sync
handler in its thread pool instead of on the event loop (security review B2)."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT, SuccessResponse
from app.schemas.email_template import (
    EmailTemplateCreate,
    EmailTemplateDraftPreviewRequest,
    EmailTemplatePreviewRequest,
    EmailTemplatePreviewResponse,
    EmailTemplateResponse,
    EmailTemplateUpdate,
    EmailThemePreviewRequest,
    EmailThemeResponse,
    TemplateVariable,
    TemplateVariablesCatalog,
)
from app.services.email_layout import EmailTheme
from app.services.email_template_service import EmailTemplateService, variables_for

router = APIRouter()


@router.get("/email-templates", response_model=ListResponse[EmailTemplateResponse])
def list_email_templates(
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
def get_email_template_variable_catalog(
    code: Optional[str] = Query(None, max_length=80),
    current_user: dict = Depends(require_permission("email_templates.templates.view")),
):
    return TemplateVariablesCatalog(
        variables=[TemplateVariable(**v) for v in variables_for(code)]
    )


@router.post("/email-templates/preview-draft", response_model=EmailTemplatePreviewResponse)
def preview_email_template_draft(
    payload: EmailTemplateDraftPreviewRequest,
    # edit, not view: this renders caller-supplied Jinja, which saving a template has
    # always required edit/add for (security review B2).
    current_user: dict = Depends(require_permission("email_templates.templates.edit")),
    db: Session = Depends(get_db),
):
    """Render the editor's UNSAVED template (#1349 AC-EM031). Stores nothing."""
    rendered = EmailTemplateService(db).preview_draft(payload.model_dump(mode="json"))
    return EmailTemplatePreviewResponse(**rendered)


# --------------------------------------------------------------------------- #
# Email theme (#1349): one object on the system_settings singleton, read with #
# the email-templates view permission and saved with its edit permission.     #
# --------------------------------------------------------------------------- #


@router.get("/email-theme", response_model=EmailThemeResponse)
def get_email_theme(
    current_user: dict = Depends(require_permission("email_templates.templates.view")),
    db: Session = Depends(get_db),
):
    return EmailTemplateService(db).get_theme()


@router.put("/email-theme", response_model=EmailThemeResponse)
def save_email_theme(
    payload: EmailTheme,
    current_user: dict = Depends(require_permission("email_templates.templates.edit")),
    db: Session = Depends(get_db),
):
    return EmailTemplateService(db).save_theme(payload)


@router.post("/email-theme/preview", response_model=EmailTemplatePreviewResponse)
def preview_email_theme(
    payload: EmailThemePreviewRequest,
    current_user: dict = Depends(require_permission("email_templates.templates.view")),
    db: Session = Depends(get_db),
):
    return EmailTemplatePreviewResponse(**EmailTemplateService(db).preview_theme(payload.theme))


@router.get("/email-templates/{template_id}", response_model=EmailTemplateResponse)
def get_email_template(
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
def create_email_template(
    payload: EmailTemplateCreate,
    current_user: dict = Depends(require_permission("email_templates.templates.add")),
    db: Session = Depends(get_db),
):
    service = EmailTemplateService(db)
    row = service.create(
        payload.model_dump(mode="json"),
        user_id=str(current_user.get("id")) if current_user else None,
    )
    return EmailTemplateResponse.model_validate(row)


@router.put("/email-templates/{template_id}", response_model=EmailTemplateResponse)
def update_email_template(
    template_id: str,
    payload: EmailTemplateUpdate,
    current_user: dict = Depends(require_permission("email_templates.templates.edit")),
    db: Session = Depends(get_db),
):
    row = EmailTemplateService(db).update(
        template_id, payload.model_dump(mode="json", exclude_unset=True)
    )
    return EmailTemplateResponse.model_validate(row)


@router.delete("/email-templates/{template_id}", response_model=SuccessResponse)
def delete_email_template(
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
def preview_email_template(
    template_id: str,
    payload: EmailTemplatePreviewRequest,
    current_user: dict = Depends(require_permission("email_templates.templates.view")),
    db: Session = Depends(get_db),
):
    rendered = EmailTemplateService(db).preview(template_id, payload.context)
    return EmailTemplatePreviewResponse(**rendered)
