"""Accessories library + product / combo lists (PRICETAG-ACCESSORIES).

Gated on the products permission (owner ruling Q2 (a), 6 Nov: whoever may edit products
maintains the library): `master_data.products.view` to read, `.edit` to write. Mounted with no
prefix under `master_data`'s router (which carries the module guard), because the routes live
under three path roots, like `product_combos.py`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.accessory import (
    AccessoryCreate,
    AccessoryIdsIn,
    AccessoryImageOut,
    AccessoryListOut,
    AccessoryOut,
    AccessoryUpdate,
)
from app.schemas.common import MAX_PAGE_LIMIT, ListResponse
from app.services.accessory_service import AccessoryService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "master_data.products.view"
EDIT = "master_data.products.edit"


@router.get("/accessories", response_model=ListResponse[AccessoryOut])
def list_accessories(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    return AccessoryService(db).list(page=page, limit=limit, query=query)


@router.post("/accessories", response_model=AccessoryOut, status_code=status.HTTP_201_CREATED)
def create_accessory(
    payload: AccessoryCreate,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    return AccessoryService(db).create(payload.model_dump(), created_by=current_user.get("id"))


@router.get("/accessories/{accessory_id}", response_model=AccessoryOut)
def get_accessory(
    accessory_id: str,
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(accessory_id, resource="Accessory")
    return AccessoryService(db).get(accessory_id)


@router.patch("/accessories/{accessory_id}", response_model=AccessoryOut)
def update_accessory(
    accessory_id: str,
    payload: AccessoryUpdate,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(accessory_id, resource="Accessory")
    return AccessoryService(db).update(accessory_id, payload.model_dump(exclude_unset=True))


@router.delete("/accessories/{accessory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_accessory(
    accessory_id: str,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(accessory_id, resource="Accessory")
    AccessoryService(db).delete(accessory_id)
    return None


@router.post("/accessories/{accessory_id}/image", response_model=AccessoryImageOut)
def upload_accessory_image(
    accessory_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(accessory_id, resource="Accessory")
    return AccessoryService(db).upload_image(
        accessory_id,
        content=file.file.read(),
        filename=file.filename or "accessory",
        content_type=file.content_type,
        user_id=current_user.get("id"),
    )


@router.delete("/accessories/{accessory_id}/image", status_code=status.HTTP_204_NO_CONTENT)
def delete_accessory_image(
    accessory_id: str,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(accessory_id, resource="Accessory")
    AccessoryService(db).delete_image(accessory_id)
    return None


@router.get("/products/{product_id}/accessories", response_model=AccessoryListOut)
def list_product_accessories(
    product_id: str,
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(product_id, resource="Product")
    return {"data": AccessoryService(db).product_list(product_id)}


@router.put("/products/{product_id}/accessories", response_model=AccessoryListOut)
def set_product_accessories(
    product_id: str,
    payload: AccessoryIdsIn,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(product_id, resource="Product")
    for value in payload.accessory_ids:
        validate_uuid_path(value, resource="Accessory")
    return {"data": AccessoryService(db).set_product_list(product_id, payload.accessory_ids)}


@router.get("/product-combos/{combo_id}/accessories", response_model=AccessoryListOut)
def list_combo_accessories(
    combo_id: str,
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(combo_id, resource="Combo")
    return {"data": AccessoryService(db).combo_list(combo_id)}


@router.put("/product-combos/{combo_id}/accessories", response_model=AccessoryListOut)
def set_combo_accessories(
    combo_id: str,
    payload: AccessoryIdsIn,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(combo_id, resource="Combo")
    for value in payload.accessory_ids:
        validate_uuid_path(value, resource="Accessory")
    return {"data": AccessoryService(db).set_combo_list(combo_id, payload.accessory_ids)}
