"""Tag template CRUD endpoints.

Mounted at ``/api/v1/dealer-kit`` behind
``require_module_enabled_with_api_key("dealer_kit")``.

Permission gates:
  * ``dealer_kit.tag_templates.view``   - list + detail
  * ``dealer_kit.tag_templates.manage`` - create, update, delete
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.dealer_kit import TagTemplate
from app.schemas.price_tag import (
    TagTemplateCreate,
    TagTemplateResponse,
    TagTemplateUpdate,
)
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tag-templates", tags=["tag-templates"])

_VIEW = require_permission_with_api_key("dealer_kit.tag_templates.view")
_MANAGE = require_permission("dealer_kit.tag_templates.manage")


def _user_id(user: dict) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


@router.get("", response_model=list[TagTemplateResponse])
def list_tag_templates(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    templates = db.query(TagTemplate).order_by(TagTemplate.family, TagTemplate.name).all()
    return [TagTemplateResponse.model_validate(t) for t in templates]


@router.get("/{template_id}", response_model=TagTemplateResponse)
def get_tag_template(
    template_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    t = db.query(TagTemplate).filter(TagTemplate.id == template_id).first()
    if not t:
        raise AppException(
            status_code=404,
            message="Tag template not found.",
            code="NOT_FOUND",
        )
    return TagTemplateResponse.model_validate(t)


@router.post("", response_model=TagTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_tag_template(
    payload: TagTemplateCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(_MANAGE),
):
    t = TagTemplate(
        name=payload.name,
        family=payload.family,
        doc=payload.doc,
        print_size=payload.print_size,
        created_by=_user_id(user),
    )
    db.add(t)
    db.flush()
    db.commit()
    return TagTemplateResponse.model_validate(t)


@router.put("/{template_id}", response_model=TagTemplateResponse)
def update_tag_template(
    template_id: str,
    payload: TagTemplateUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    t = db.query(TagTemplate).filter(TagTemplate.id == template_id).first()
    if not t:
        raise AppException(
            status_code=404,
            message="Tag template not found.",
            code="NOT_FOUND",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(t, key, value)

    db.flush()
    db.commit()
    return TagTemplateResponse.model_validate(t)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag_template(
    template_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    t = db.query(TagTemplate).filter(TagTemplate.id == template_id).first()
    if not t:
        raise AppException(
            status_code=404,
            message="Tag template not found.",
            code="NOT_FOUND",
        )
    db.delete(t)
    db.commit()
