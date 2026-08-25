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
from app.dependencies import require_permission_with_api_key
from app.schemas.price_tag import (
    ProductSearchItem,
    ProductSetSearchItem,
    ProductSetTagData,
    ProductTagData,
)
from app.services.dealer_kit import tag_data_service
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tag-data"])

_VIEW = require_permission_with_api_key("dealer_kit.tag_templates.view")


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


@router.get("/products/{product_id}/tag-data", response_model=ProductTagData)
def get_product_tag_data(
    product_id: str,
    promotion_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Everything a product block draws, resolved now (never stored - ADR 0008)."""
    product = tag_data_service.get_product(db, product_id)
    if product is None:
        raise AppException(
            status_code=404, message="Product not found.", code="NOT_FOUND"
        )
    return ProductTagData.model_validate(
        tag_data_service.product_tag_data(
            db, product, tag_data_service.staff_viewer(), promotion_id
        )
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
