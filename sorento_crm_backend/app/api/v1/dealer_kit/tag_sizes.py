"""Tag size preset endpoints (PLAN-price-tag-ux-r3.md S4, D2).

Mounted at ``/api/v1/dealer-kit`` behind
``require_module_enabled_with_api_key("dealer_kit")``.

Permission gates (D9 - reuses the tag template slugs; no new grant sweep):
  * ``dealer_kit.tag_templates.view``   - list
  * ``dealer_kit.tag_templates.manage`` - create, update, delete
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.dealer_kit import TagSizePreset
from app.models.user import User
from app.schemas.price_tag import (
    TagSizePresetCreate,
    TagSizePresetResponse,
    TagSizePresetUpdate,
)
from app.services.dealer_kit import tag_size_service

router = APIRouter(prefix="/tag-sizes", tags=["tag-sizes"])

_VIEW = require_permission_with_api_key("dealer_kit.tag_templates.view")
_MANAGE = require_permission("dealer_kit.tag_templates.manage")


def _user_id(user: dict) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


def _creator_name(db: Session, created_by: str | None) -> str | None:
    if not created_by:
        return None
    return db.query(User.name).filter(User.id == created_by).scalar()


def _response_for(row: TagSizePreset, created_by_name: str | None) -> TagSizePresetResponse:
    resp = TagSizePresetResponse.model_validate(row)
    resp.created_by_name = created_by_name
    return resp


@router.get("", response_model=list[TagSizePresetResponse])
def list_tag_sizes(db: Session = Depends(get_db), _user: dict = Depends(_VIEW)):
    rows = tag_size_service.list_presets(db)
    creator_ids = {row.created_by for row in rows if row.created_by}
    names: dict[str, str] = {}
    if creator_ids:
        names = dict(db.query(User.id, User.name).filter(User.id.in_(creator_ids)).all())
    return [_response_for(row, names.get(row.created_by)) for row in rows]


@router.post("", response_model=TagSizePresetResponse, status_code=status.HTTP_201_CREATED)
def create_tag_size(
    payload: TagSizePresetCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(_MANAGE),
):
    created_by = _user_id(user)
    row = tag_size_service.create_preset(
        db,
        name=payload.name,
        width_mm=payload.width_mm,
        height_mm=payload.height_mm,
        created_by=created_by,
    )
    return _response_for(row, _creator_name(db, created_by))


@router.put("/{preset_id}", response_model=TagSizePresetResponse)
def update_tag_size(
    preset_id: str,
    payload: TagSizePresetUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    update_data = payload.model_dump(exclude_unset=True)
    row = tag_size_service.update_preset(db, preset_id, **update_data)
    return _response_for(row, _creator_name(db, row.created_by))


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag_size(
    preset_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    """The immediate delete. The deferred one (`tag_size_preset.delete`, the
    listing's row menu and the Tag Size control's saved-size `x`) calls the
    SAME service method, so the two cannot drift."""
    tag_size_service.delete_preset(db, preset_id)
