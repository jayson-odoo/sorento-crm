"""Item packages — read-only AutoCount mirror + annotation (Slice 3).

Read + annotate only. Ingest (via /external/item-packages/ingest) owns creation
and every business column, including the package lines. The detail response
embeds the resolved lines (product code/name, not UUIDs).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.item_package import ItemPackage
from app.schemas.autocount_mirror import ItemPackageResponse, MirrorAnnotationUpdate
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.autocount_mirror_service import MirrorReadService
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()
_RESOURCE = "Item Package"


@router.get("/", response_model=ListResponse[ItemPackageResponse])
async def list_item_packages(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    current_user: dict = Depends(require_permission_with_api_key("master_data.item_packages.view")),
    db: Session = Depends(get_db),
):
    try:
        return MirrorReadService(db).list(
            ItemPackage,
            search_columns=[ItemPackage.package_code, ItemPackage.description, ItemPackage.bar_code],
            page=page, limit=limit, query=query, sort=sort, dir=dir,
        )
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{item_package_id}", response_model=ItemPackageResponse)
async def get_item_package(
    item_package_id: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.item_packages.view")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(item_package_id, resource=_RESOURCE)
        return MirrorReadService(db).get(ItemPackage, item_package_id, resource=_RESOURCE)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{item_package_id}/annotation", response_model=ItemPackageResponse)
async def annotate_item_package(
    item_package_id: str,
    payload: MirrorAnnotationUpdate,
    current_user: dict = Depends(require_permission("master_data.item_packages.edit")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(item_package_id, resource=_RESOURCE)
        fields = payload.model_fields_set
        return MirrorReadService(db).annotate(
            ItemPackage, item_package_id, resource=_RESOURCE,
            internal_note=payload.internal_note, follow_up=payload.follow_up,
            set_note="internal_note" in fields, set_follow_up="follow_up" in fields,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
