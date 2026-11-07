"""Saved accessories box designs (PRICETAG-ACCESSORY-DESIGNER).

Mounted at ``/api/v1/dealer-kit/accessory-templates``. Permission gates are the tag template slugs,
as tag sizes: ``dealer_kit.tag_templates.view`` to read, ``.manage`` to write.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.dealer_kit import AccessoryBoxPreset
from app.models.user import User
from app.schemas.accessory_template import (
    AccessoryTemplateCreate,
    AccessoryTemplateOut,
    AccessoryTemplateUpdate,
    AccessoryTemplateUsageOut,
)
from app.services.dealer_kit import accessory_template_service as service

router = APIRouter(prefix="/accessory-templates", tags=["accessory-templates"])

_VIEW = require_permission_with_api_key("dealer_kit.tag_templates.view")
_MANAGE = require_permission("dealer_kit.tag_templates.manage")


def _user_id(user: dict) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


def _out(db: Session, row: AccessoryBoxPreset, names: dict | None = None, rewritten: int = 0) -> AccessoryTemplateOut:
    if names is None:
        names = dict(db.query(User.id, User.name).filter(User.id == row.created_by).all()) if row.created_by else {}
    out = AccessoryTemplateOut.model_validate(row)
    out.used_in = len(service.usage(db, row.id))
    out.created_by_name = names.get(row.created_by)
    out.rewritten = rewritten
    return out


@router.get("", response_model=list[AccessoryTemplateOut])
def list_accessory_templates(db: Session = Depends(get_db), _user: dict = Depends(_VIEW)):
    rows = service.list_presets(db)
    creator_ids = {row.created_by for row in rows if row.created_by}
    names = dict(db.query(User.id, User.name).filter(User.id.in_(creator_ids)).all()) if creator_ids else {}
    return [_out(db, row, names) for row in rows]


@router.post("", response_model=AccessoryTemplateOut, status_code=status.HTTP_201_CREATED)
def create_accessory_template(
    payload: AccessoryTemplateCreate, db: Session = Depends(get_db), user: dict = Depends(_MANAGE)
):
    row = service.create_preset(db, name=payload.name, design=payload.design, user_id=_user_id(user))
    return _out(db, row)


@router.get("/{preset_id}", response_model=AccessoryTemplateOut)
def get_accessory_template(preset_id: str, db: Session = Depends(get_db), _user: dict = Depends(_VIEW)):
    return _out(db, service.get_preset(db, preset_id))


@router.get("/{preset_id}/usage", response_model=AccessoryTemplateUsageOut)
def accessory_template_usage(preset_id: str, db: Session = Depends(get_db), _user: dict = Depends(_VIEW)):
    row = service.get_preset(db, preset_id)
    return {"templates": service.usage(db, row.id)}


@router.put("/{preset_id}", response_model=AccessoryTemplateOut)
def update_accessory_template(
    preset_id: str,
    payload: AccessoryTemplateUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(_MANAGE),
):
    changes = payload.model_dump(exclude_unset=True)
    row, rewritten = service.update_preset(
        db, preset_id, name=changes.get("name"), design=changes.get("design"), user_id=_user_id(user)
    )
    return _out(db, row, rewritten=rewritten)


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_accessory_template(preset_id: str, db: Session = Depends(get_db), _user: dict = Depends(_MANAGE)):
    """The immediate delete; the deferred `accessory_box_preset.delete` calls the SAME service function."""
    service.delete_preset(db, preset_id)
