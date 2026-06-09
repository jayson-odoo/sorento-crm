"""Respond.io WhatsApp template sync + default-template configuration routes.

Contract: documented in sorento_crm_frontend/services/whatsappTemplateService.ts
and docs/plans/PLAN-whatsapp-template-fallback.md.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.respond_template import TemplateDefaultUpsertRequest

router = APIRouter()


@router.get("/templates")
def list_templates(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    query: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sort: str = Query("name"),
    dir: str = Query("asc"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("integration.respond_templates.view")),
):
    from app.services.respond_template_service import list_templates as _impl

    return _impl(
        db,
        page=page,
        limit=limit,
        query=query,
        status=status,
        sort=sort,
        direction=dir,
    )


@router.post("/templates/sync")
def sync_templates(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("integration.respond_templates.sync")),
):
    from app.services.respond_template_service import sync_templates as _impl

    return _impl(db)


@router.get("/template-defaults")
def list_template_defaults(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("integration.respond_templates.view")),
):
    from app.services.respond_template_service import get_defaults as _impl

    return _impl(db)


@router.put("/template-defaults/{use_case}")
def set_template_default(
    use_case: str,
    body: TemplateDefaultUpsertRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("integration.respond_templates.edit")),
):
    from app.services.respond_template_service import set_default as _impl

    return _impl(
        db,
        use_case,
        template_id=body.template_id,
        param_mapping=body.param_mapping,
    )


@router.delete("/template-defaults/{use_case}")
def clear_template_default(
    use_case: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("integration.respond_templates.edit")),
):
    from app.services.respond_template_service import clear_default as _impl

    return _impl(db, use_case)
