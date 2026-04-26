"""Quotation customer email templates (tokenized)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import ListResponse, PaginationResponse
from app.modules.commercial_core.schemas.quotation_email_template import (
    QuotationEmailTemplateCreate,
    QuotationEmailTemplateOut,
    QuotationEmailTemplatePatch,
)
from app.services.error_handler import AppException, handle_internal_error
from app.modules.commercial_core.services.quotation_email_template_service import QuotationEmailTemplateService

router = APIRouter()


def _out(row) -> QuotationEmailTemplateOut:
    return QuotationEmailTemplateOut(
        id=str(row.id),
        code=row.code,
        name=row.name,
        subject_template=row.subject_template or "",
        body_html_template=row.body_html_template or "",
        is_active=bool(row.is_active),
        is_default=bool(row.is_default),
        sort_order=int(row.sort_order or 0),
    )


@router.get("/quotation-email-templates", response_model=ListResponse[QuotationEmailTemplateOut])
async def list_quotation_email_templates(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    _current_user: dict = Depends(require_permission("commercial_core.master_quotations.view")),
):
    try:
        svc = QuotationEmailTemplateService(db)
        rows = svc.list_templates(active_only=active_only)
        data: List[QuotationEmailTemplateOut] = [_out(r) for r in rows]
        return ListResponse(
            data=data,
            pagination=PaginationResponse(total=len(data), page=1, limit=max(len(data), 1)),
            empty=len(data) == 0,
        )
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/quotation-email-templates",
    response_model=QuotationEmailTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_quotation_email_template(
    body: QuotationEmailTemplateCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    try:
        svc = QuotationEmailTemplateService(db)
        row = svc.create(
            code=body.code,
            name=body.name,
            subject_template=body.subject_template,
            body_html_template=body.body_html_template,
            is_active=body.is_active,
            is_default=body.is_default,
            sort_order=body.sort_order,
        )
        db.commit()
        return _out(row)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.patch("/quotation-email-templates/{template_id}", response_model=QuotationEmailTemplateOut)
async def patch_quotation_email_template(
    template_id: str,
    body: QuotationEmailTemplatePatch,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    try:
        svc = QuotationEmailTemplateService(db)
        patch = body.model_dump(exclude_unset=True)
        row = svc.update(template_id, **patch)
        db.commit()
        return _out(row)
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.delete("/quotation-email-templates/{template_id}", status_code=status.HTTP_200_OK)
async def delete_quotation_email_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("commercial_core.master_quotations.edit")),
):
    try:
        svc = QuotationEmailTemplateService(db)
        svc.soft_delete(template_id)
        db.commit()
        return {"message": "Template deactivated."}
    except AppException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))
