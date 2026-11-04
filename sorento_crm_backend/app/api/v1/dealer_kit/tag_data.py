"""What the tag canvas asks the catalogue: product search and resolved tag data.

Mounted at ``/api/v1/dealer-kit`` behind
``require_module_enabled_with_api_key("dealer_kit")``.

Gated on ``dealer_kit.tag_templates.view``: these routes exist for the tag
editor and the tag sheet designer, and both are already behind that permission.
Nothing new is granted, so no role sweep is needed.

Prices and photos are resolved for the STAFF viewer (see
``tag_data_service.staff_viewer``) - marketing is designing a proof of the tag
they are about to print, so they see the figure the tag will carry.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.price_tag import (
    ComboSearchOut,
    ProductSearchItem,
    ProductSetSearchItem,
    ProductSetTagData,
    ProductTagData,
    ProductTagTemplateItem,
    ProductTagTemplatesUpdate,
    SpecKeyItem,
)
from app.services.dealer_kit import product_tag_template_service, tag_data_service
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tag-data"])

_VIEW = require_permission_with_api_key("dealer_kit.tag_templates.view")
# PRICETAG-TEMPLATE-PER-PRODUCT (card Q5 a): the links are marketing's, same
# permission as editing the templates themselves.
_MANAGE = require_permission("dealer_kit.tag_templates.manage")


@router.get("/products/search", response_model=list[ProductSearchItem])
def search_products(
    q: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Products for the editor's picker, in the caller's company scope."""
    return [
        ProductSearchItem.model_validate(product)
        for product in tag_data_service.search_products(db, q, limit=limit)
    ]


@router.get("/tag-data/combos", response_model=ComboSearchOut)
def search_combos(
    query: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Combos for the template editor's Preview combo picker, in the caller's company scope."""
    return {"data": tag_data_service.search_combos(db, query, limit=limit)}


@router.get("/products/{product_id}/tag-data", response_model=ProductTagData)
def get_product_tag_data(
    product_id: str,
    promotion_id: Optional[str] = Query(None),
    combo_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Everything a product block draws, resolved now (never stored - ADR 0008)."""
    product = tag_data_service.get_product(db, product_id)
    if product is None:
        raise AppException(
            status_code=404, message="Product not found.", code="NOT_FOUND"
        )
    data = tag_data_service.product_tag_data(
        db, product, tag_data_service.staff_viewer(), promotion_id
    )
    return ProductTagData.model_validate(
        tag_data_service.with_preview_combo(db, product, data, combo_id)
    )


@router.get("/product-sets/search", response_model=list[ProductSetSearchItem])
def search_product_sets(
    q: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    return [
        ProductSetSearchItem.model_validate(product_set)
        for product_set in tag_data_service.search_product_sets(db, q, limit=limit)
    ]


@router.get("/product-sets/{set_id}/tag-data", response_model=ProductSetTagData)
def get_product_set_tag_data(
    set_id: str,
    promotion_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    product_set = tag_data_service.get_product_set(db, set_id)
    if product_set is None:
        raise AppException(
            status_code=404, message="Product set not found.", code="NOT_FOUND"
        )
    return ProductSetTagData.model_validate(
        tag_data_service.product_set_tag_data(
            db, product_set, tag_data_service.staff_viewer(), promotion_id
        )
    )


@router.get("/spec-keys", response_model=list[SpecKeyItem])
def list_spec_keys(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The spec vocabulary, for the Insert field dialog's Specs group (D58).

    Read here rather than from ``/master-data/spec-registry`` because that route
    is gated on ``master_data.products.view``, which the marketing role that
    designs a tag has no reason to hold. Same rows, same service, the gate the
    rest of the editor already uses. A key added to the registry therefore shows
    up in the dialog with no code change.
    """
    from app.services.product_spec_registry import active_registry

    return [
        SpecKeyItem(key=row.spec_key, label=row.label, unit=row.unit)
        for row in active_registry(db)
    ]


@router.get(
    "/products/{product_id}/tag-templates", response_model=list[ProductTagTemplateItem]
)
def list_product_tag_templates(
    product_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The templates linked to this product (product page, Overview)."""
    from app.services.uuid_path_param import validate_uuid_path

    product_id = validate_uuid_path(product_id, resource="Product")
    if not product_tag_template_service.product_exists(db, product_id):
        raise AppException(status_code=404, message="Product not found.", code="NOT_FOUND")
    return [
        ProductTagTemplateItem(**item)
        for item in product_tag_template_service.linked_items(db, product_id)
    ]


@router.put(
    "/products/{product_id}/tag-templates", response_model=list[ProductTagTemplateItem]
)
def set_product_tag_templates(
    product_id: str,
    payload: ProductTagTemplatesUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(_MANAGE),
):
    """Replace this product's links with ``template_ids``."""
    from app.services.uuid_path_param import validate_uuid_path

    product_id = validate_uuid_path(product_id, resource="Product")
    product_tag_template_service.set_product_templates(
        db,
        product_id,
        payload.template_ids,
        user_id=(user or {}).get("id"),
        default_template_id=payload.default_template_id,
    )
    db.commit()
    return [
        ProductTagTemplateItem(**item)
        for item in product_tag_template_service.linked_items(db, product_id)
    ]


@router.get(
    "/combos/{combo_id}/tag-templates", response_model=list[ProductTagTemplateItem]
)
def list_combo_tag_templates(
    combo_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The templates linked to this combo (its host product's company scopes it)."""
    from app.services.uuid_path_param import validate_uuid_path

    combo_id = validate_uuid_path(combo_id, resource="Combo")
    if not product_tag_template_service.combo_exists(db, combo_id):
        raise AppException(status_code=404, message="Combo not found.", code="NOT_FOUND")
    return [
        ProductTagTemplateItem(**item)
        for item in product_tag_template_service.linked_combo_items(db, combo_id)
    ]


@router.put(
    "/combos/{combo_id}/tag-templates", response_model=list[ProductTagTemplateItem]
)
def set_combo_tag_templates(
    combo_id: str,
    payload: ProductTagTemplatesUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(_MANAGE),
):
    """Replace this combo's links with ``template_ids``."""
    from app.services.uuid_path_param import validate_uuid_path

    combo_id = validate_uuid_path(combo_id, resource="Combo")
    product_tag_template_service.set_combo_templates(
        db,
        combo_id,
        payload.template_ids,
        user_id=(user or {}).get("id"),
        default_template_id=payload.default_template_id,
    )
    db.commit()
    return [
        ProductTagTemplateItem(**item)
        for item in product_tag_template_service.linked_combo_items(db, combo_id)
    ]
