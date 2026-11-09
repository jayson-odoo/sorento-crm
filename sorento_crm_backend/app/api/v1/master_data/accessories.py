"""Accessories library + product / combo lists (PRICETAG-ACCESSORIES).

Gated on the products permission (owner ruling Q2 (a), 6 Nov: whoever may edit products
maintains the library): `master_data.products.view` to read (session or API key), `.edit` to write
(a signed-in user only, as the product write routes: no integration writes these). Mounted with no
prefix under `master_data`'s router (which carries the module guard), because the routes live
under three path roots, like `product_combos.py`.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.accessory import (
    AccessoryCopyIn,
    AccessoryCopyOut,
    AccessoryCreate,
    AccessoryItemsIn,
    AccessoryColourOut,
    AccessoryColoursIn,
    AccessoryImageOrderIn,
    AccessoryImageOut,
    AccessoryImagePatch,
    AccessoryListOut,
    AccessoryOut,
    AccessoryPictureOut,
    AccessoryUpdate,
)
from app.schemas.common import MAX_PAGE_LIMIT, ListResponse
from app.services.error_handler import AppException
from app.services.accessory_service import MAX_IMAGE_BYTES, UNSET, AccessoryService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()


def _items(payload: AccessoryItemsIn) -> list[dict]:
    """The ordered entries, each id checked to be a UUID (a malformed one is a 422, not a 500)."""
    out = []
    for item in payload.items:
        if item.accessory_id:
            validate_uuid_path(item.accessory_id, resource="Accessory")
        if item.product_id:
            validate_uuid_path(item.product_id, resource="Product")
        out.append(item.model_dump())
    return out

def _style(payload: AccessoryItemsIn):
    """`box_style_id`: absent from the body = unchanged (the service's `_UNSET`), null = cleared."""
    if "box_style_id" not in payload.model_fields_set:
        return UNSET
    if payload.box_style_id:
        validate_uuid_path(payload.box_style_id, resource="Accessories template")
    return payload.box_style_id or None


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
    current_user: dict = Depends(require_permission(EDIT)),
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
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(accessory_id, resource="Accessory")
    return AccessoryService(db).update(accessory_id, payload.model_dump(exclude_unset=True))


@router.delete("/accessories/{accessory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_accessory(
    accessory_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(accessory_id, resource="Accessory")
    AccessoryService(db).delete(accessory_id)
    return None


@router.post(
    "/accessories/{accessory_id}/images",
    response_model=AccessoryImageOut,
    status_code=status.HTTP_201_CREATED,
)
def add_accessory_image(
    accessory_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(accessory_id, resource="Accessory")
    content = file.file.read(MAX_IMAGE_BYTES + 1)
    return AccessoryService(db).add_image(
        accessory_id,
        content=content,
        filename=file.filename or "accessory",
        user_id=current_user.get("id"),
    )


@router.put("/accessories/{accessory_id}/colours", response_model=List[AccessoryColourOut])
def set_accessory_colours(
    accessory_id: str,
    payload: AccessoryColoursIn,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(accessory_id, resource="Accessory")
    return AccessoryService(db).set_colours(accessory_id, [c.model_dump() for c in payload.colours])


@router.put("/accessories/{accessory_id}/images/order", response_model=List[AccessoryImageOut])
def order_accessory_images(
    accessory_id: str,
    payload: AccessoryImageOrderIn,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(accessory_id, resource="Accessory")
    return AccessoryService(db).order_images(accessory_id, payload.ids)


@router.patch("/accessories/{accessory_id}/images/{image_id}", response_model=AccessoryImageOut)
def patch_accessory_image(
    accessory_id: str,
    image_id: str,
    payload: AccessoryImagePatch,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(accessory_id, resource="Accessory")
    validate_uuid_path(image_id, resource="Image")
    return AccessoryService(db).patch_image(accessory_id, image_id, payload.model_dump(exclude_unset=True))


@router.delete("/accessories/{accessory_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_accessory_picture(
    accessory_id: str,
    image_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(accessory_id, resource="Accessory")
    validate_uuid_path(image_id, resource="Image")
    AccessoryService(db).delete_picture(accessory_id, image_id)
    return None


@router.post("/accessories/{accessory_id}/image", response_model=AccessoryPictureOut)
def upload_accessory_image(
    accessory_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(accessory_id, resource="Accessory")
    # At most one byte past the limit: a larger body is refused without holding all of it.
    content = file.file.read(MAX_IMAGE_BYTES + 1)
    return AccessoryService(db).upload_image(
        accessory_id,
        content=content,
        filename=file.filename or "accessory",
        content_type=file.content_type,
        user_id=current_user.get("id"),
    )


@router.delete("/accessories/{accessory_id}/image", status_code=status.HTTP_204_NO_CONTENT)
def delete_accessory_image(
    accessory_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
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
    service = AccessoryService(db)
    return {"data": service.product_list(product_id), "box_style_id": service.box_style_id_of(product_id=product_id)}


@router.put("/products/{product_id}/accessories", response_model=AccessoryListOut)
def set_product_accessories(
    product_id: str,
    payload: AccessoryItemsIn,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(product_id, resource="Product")
    service = AccessoryService(db)
    data = service.set_product_list(product_id, _items(payload), _style(payload))
    return {"data": data, "box_style_id": service.box_style_id_of(product_id=product_id)}


@router.post("/products/{product_id}/accessories/copy", response_model=AccessoryCopyOut)
def copy_product_accessories(
    product_id: str,
    payload: AccessoryCopyIn,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """ACC-COPY-TO-PRODUCTS: add this product's entries to hand-picked products, one transaction."""
    validate_uuid_path(product_id, resource="Product")
    for value in payload.target_product_ids:
        try:
            uuid.UUID(value)
        except ValueError:
            raise AppException(status_code=422, message="Each target must be a product id")
    return AccessoryService(db).copy_product_list(
        product_id, payload.target_product_ids, dry_run=payload.dry_run
    )


@router.get("/product-combos/{combo_id}/accessories", response_model=AccessoryListOut)
def list_combo_accessories(
    combo_id: str,
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(combo_id, resource="Combo")
    service = AccessoryService(db)
    return {"data": service.combo_list(combo_id), "box_style_id": service.box_style_id_of(combo_id=combo_id)}


@router.put("/product-combos/{combo_id}/accessories", response_model=AccessoryListOut)
def set_combo_accessories(
    combo_id: str,
    payload: AccessoryItemsIn,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(combo_id, resource="Combo")
    service = AccessoryService(db)
    data = service.set_combo_list(combo_id, _items(payload), _style(payload))
    return {"data": data, "box_style_id": service.box_style_id_of(combo_id=combo_id)}
