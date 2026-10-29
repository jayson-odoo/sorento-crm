"""Item Class API routes (ITEM-CLASS, PLAN-item-class-29oct.md D4): the countries routes'
shape, gated by `master_data.item_classes.*`."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    require_permission,
    require_permission_with_api_key,
    require_session_or_api_key_permission,
)
from app.schemas.common import MAX_PAGE_LIMIT, ListResponse
from app.schemas.item_class import (
    ItemClassCreate,
    ItemClassResponse,
    ItemClassSelectItem,
    ItemClassUpdate,
)
from app.services.error_handler import handle_internal_error
from app.services.item_class_service import ItemClassService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()


@router.get("/", response_model=ListResponse[ItemClassResponse])
def get_item_classes(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key("master_data.item_classes.view")),
    db: Session = Depends(get_db),
):
    try:
        return ItemClassService(db).list_item_classes(
            page=page, limit=limit, query=query, sort=sort, sort_dir=dir
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/select", response_model=List[ItemClassSelectItem])
def get_item_classes_select(
    query: Optional[str] = Query(None),
    brand_id: Optional[str] = Query(None, description="Only classes some product of this brand carries."),
    # Any signed-in user (never-stuck L10, the brands select rule); an API key needs the slug.
    current_user: dict = Depends(require_session_or_api_key_permission("master_data.item_classes.view")),
    db: Session = Depends(get_db),
):
    try:
        if brand_id:
            validate_uuid_path(brand_id, resource="Brand")
        return ItemClassService(db).select(query=query, brand_id=brand_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{item_class_id}", response_model=ItemClassResponse)
def get_item_class(
    item_class_id: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.item_classes.view")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(item_class_id, resource="Item Class")
        return ItemClassService(db).get_detail(item_class_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=ItemClassResponse, status_code=status.HTTP_201_CREATED)
def create_item_class(
    data: ItemClassCreate,
    current_user: dict = Depends(require_permission("master_data.item_classes.add")),
    db: Session = Depends(get_db),
):
    try:
        return ItemClassService(db).create(data)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{item_class_id}", response_model=ItemClassResponse)
def update_item_class(
    item_class_id: str,
    data: ItemClassUpdate,
    current_user: dict = Depends(require_permission("master_data.item_classes.edit")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(item_class_id, resource="Item Class")
        return ItemClassService(db).update(item_class_id, data)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{item_class_id}", status_code=status.HTTP_200_OK)
def delete_item_class(
    item_class_id: str,
    current_user: dict = Depends(require_permission("master_data.item_classes.delete")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(item_class_id, resource="Item Class")
        return ItemClassService(db).delete(item_class_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
