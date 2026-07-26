"""Tax entities — read-only AutoCount mirror + annotation (Slice 2)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.tax_entity import TaxEntity
from app.schemas.autocount_mirror import MirrorAnnotationUpdate, TaxEntityResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.autocount_mirror_service import MirrorReadService
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()
_RESOURCE = "Tax Entity"


@router.get("/", response_model=ListResponse[TaxEntityResponse])
async def list_tax_entities(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    current_user: dict = Depends(require_permission_with_api_key("master_data.tax_entities.view")),
    db: Session = Depends(get_db),
):
    try:
        return MirrorReadService(db).list(
            TaxEntity,
            search_columns=[TaxEntity.tax_entity_id, TaxEntity.name, TaxEntity.tin],
            page=page, limit=limit, query=query, sort=sort, dir=dir,
        )
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{tax_entity_id}", response_model=TaxEntityResponse)
async def get_tax_entity(
    tax_entity_id: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.tax_entities.view")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(tax_entity_id, resource=_RESOURCE)
        return MirrorReadService(db).get(TaxEntity, tax_entity_id, resource=_RESOURCE)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{tax_entity_id}/annotation", response_model=TaxEntityResponse)
async def annotate_tax_entity(
    tax_entity_id: str,
    payload: MirrorAnnotationUpdate,
    current_user: dict = Depends(require_permission("master_data.tax_entities.edit")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(tax_entity_id, resource=_RESOURCE)
        fields = payload.model_fields_set
        return MirrorReadService(db).annotate(
            TaxEntity, tax_entity_id, resource=_RESOURCE,
            internal_note=payload.internal_note, follow_up=payload.follow_up,
            set_note="internal_note" in fields, set_follow_up="follow_up" in fields,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
