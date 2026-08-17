"""Cover letter and terms template administration (S4, UAC Group E).

Setup, not sales: these routes rewrite the letter every future quotation carries, so they gate on
the same ``projects.types.*`` pair the project type and template config already uses rather than on
a salesperson's project grants. No new permission slug, and therefore no grant sweep.

``/merge-fields`` is declared BEFORE ``/{template_id}``, or the literal segment would be captured
as a template id and every picker request would 404 as an unknown template.

Every rule lives in the service: the one-active-per-company-and-kind switch, the 422 on an
undeclared merge token, and the refusal to delete the row a company depends on. The route does not
second-guess any of them, so each is stated once.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import acting_company_id
from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import ListResponse
from app.schemas.projects import (
    QuotationMergeFieldResponse,
    QuotationTemplateCreate,
    QuotationTemplateResponse,
    QuotationTemplateUpdate,
)
from app.services import project_quotation_template_service as templates
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "projects.types.view"
EDIT = "projects.types.edit"


def _envelope(data: list):
    return {
        "data": data,
        "pagination": {"total": len(data), "page": 1, "limit": max(len(data), 1)},
        "empty": not data,
    }


@router.get(
    "/quotation-templates/merge-fields",
    response_model=ListResponse[QuotationMergeFieldResponse],
)
async def list_merge_fields(
    _user: dict = Depends(require_permission(VIEW)),
):
    """The picker's vocabulary, from the one declared registry.

    Served rather than hardcoded in the FE so the picker and the renderer cannot drift: a token
    the picker offered but the renderer did not know would leave a hole in a customer letter, and
    it would look like a frontend bug.
    """
    return _envelope(templates.serialize_merge_fields())


@router.get("/quotation-templates", response_model=ListResponse[QuotationTemplateResponse])
async def list_quotation_templates(
    kind: Optional[str] = Query(None, description="cover_letter | terms"),
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        rows = templates.list_templates(db, company_id=acting_company_id(db), kind=kind)
        return _envelope(templates.serialize_templates(rows))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/quotation-templates/{template_id}", response_model=QuotationTemplateResponse
)
async def get_quotation_template(
    template_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(template_id, resource="Quotation template")
        return templates.serialize_template(templates.get_template_or_404(db, template_id))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/quotation-templates",
    response_model=QuotationTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_quotation_template(
    payload: QuotationTemplateCreate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        template = templates.create_template(
            db,
            company_id=acting_company_id(db),
            payload=payload.model_dump(exclude_unset=True),
            actor_user_id=current_user["id"],
        )
        db.commit()
        db.refresh(template)
        return templates.serialize_template(template)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(
    "/quotation-templates/{template_id}", response_model=QuotationTemplateResponse
)
async def update_quotation_template(
    template_id: str,
    payload: QuotationTemplateUpdate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Editing the template does NOT touch a document already created (AC-E2): the document holds
    its own rendered copy, and that is the whole point of the column."""
    try:
        validate_uuid_path(template_id, resource="Quotation template")
        template = templates.get_template_or_404(db, template_id)
        templates.update_template(
            db, template=template, payload=payload.model_dump(exclude_unset=True)
        )
        db.commit()
        db.refresh(template)
        return templates.serialize_template(template)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/quotation-templates/{template_id}/activate", response_model=QuotationTemplateResponse
)
async def activate_quotation_template(
    template_id: str,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Switch the letter every future document carries. Deactivates the incumbent in the same
    transaction, so "the active template" never names two rows."""
    try:
        validate_uuid_path(template_id, resource="Quotation template")
        template = templates.get_template_or_404(db, template_id)
        templates.activate_template(db, template=template)
        db.commit()
        db.refresh(template)
        return templates.serialize_template(template)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/quotation-templates/{template_id}")
async def delete_quotation_template(
    template_id: str,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Hard delete, refused by the service for the active template (a company would be left with
    no letter and nothing would report it)."""
    try:
        validate_uuid_path(template_id, resource="Quotation template")
        template = templates.get_template_or_404(db, template_id)
        name = template.name
        templates.delete_template(db, template=template)
        db.commit()
        return {"message": f"{name} deleted"}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
