"""Product combos - the catalogue package a product is sold as (PLAN D1, slice S1).

Gated on the products permission - `master_data.products.view` to read,
`.edit` to write - never a dedicated `product_combos.*` slug, since the combo is
configured on the product page itself (AC-X-5, and the contract comment at the top
of `productComboService.ts`).

Mounted with NO prefix under `master_data`'s own router, which already carries the
`require_module_enabled_with_api_key("product")` guard: the eight routes live under
three different path roots (`/products/{id}/...`, `/product-combos/...`,
`/product-combo-parts/...`), so one prefix cannot serve them.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.product_combo import (
    ProductComboCreate,
    ProductComboListOut,
    ProductComboOut,
    ProductComboPartCreate,
    ProductComboPartOut,
    ProductComboPartUpdate,
    ProductComboUpdate,
    ProductSoldWithListOut,
)
from app.services.product_combo_service import ProductComboService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "master_data.products.view"
EDIT = "master_data.products.edit"


@router.get("/products/{product_id}/combos", response_model=ProductComboListOut)
def list_product_combos(
    product_id: str,
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(product_id, resource="Product")
    return {"data": ProductComboService(db).list_for_host(product_id)}


@router.post(
    "/products/{product_id}/combos",
    response_model=ProductComboOut,
    status_code=status.HTTP_201_CREATED,
)
def create_product_combo(
    product_id: str,
    payload: ProductComboCreate,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(product_id, resource="Product")
    return ProductComboService(db).create(
        product_id, payload.name, created_by=current_user.get("id")
    )


@router.get("/products/{product_id}/sold-with", response_model=ProductSoldWithListOut)
def list_product_sold_with(
    product_id: str,
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(product_id, resource="Product")
    return {"data": ProductComboService(db).list_sold_with(product_id)}


@router.patch("/product-combos/{combo_id}", response_model=ProductComboOut)
def update_product_combo(
    combo_id: str,
    payload: ProductComboUpdate,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(combo_id, resource="Combo")
    return ProductComboService(db).update(combo_id, payload.model_dump(exclude_unset=True))


@router.delete("/product-combos/{combo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_combo(
    combo_id: str,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(combo_id, resource="Combo")
    ProductComboService(db).delete(combo_id)
    return None


@router.post(
    "/product-combos/{combo_id}/parts",
    response_model=ProductComboPartOut,
    status_code=status.HTTP_201_CREATED,
)
def add_product_combo_part(
    combo_id: str,
    payload: ProductComboPartCreate,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(combo_id, resource="Combo")
    validate_uuid_path(payload.part_product_id, resource="Product")
    return ProductComboService(db).add_part(
        combo_id, payload.part_product_id, payload.choice_group
    )


@router.patch("/product-combo-parts/{part_id}", response_model=ProductComboPartOut)
def update_product_combo_part(
    part_id: str,
    payload: ProductComboPartUpdate,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(part_id, resource="Combo part")
    return ProductComboService(db).update_part(
        part_id, payload.model_dump(exclude_unset=True), fields_set=payload.model_fields_set
    )


@router.delete("/product-combo-parts/{part_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_combo_part(
    part_id: str,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(part_id, resource="Combo part")
    ProductComboService(db).delete_part(part_id)
    return None
