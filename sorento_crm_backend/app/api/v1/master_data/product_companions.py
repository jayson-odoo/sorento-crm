""""Supplied with" companion rules (PLAN-scm-supplied-with-companions.md S4).

Gated on the products permission - `master_data.products.view` to read, `.edit` to
write - never a dedicated `product_companions.*` slug, since the rule is configured on
the product page itself (the plan's own S4, and the frontend contract comment at the
top of `productCompanionService.ts`).

Mounted at `/product-companion-rules` under `master_data`'s own router, which already
carries the `require_module_enabled_with_api_key("product")` guard.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.product_companion import ProductCompanionRuleCreate, ProductCompanionRuleOut
from app.services.error_handler import AppException
from app.services.product_companion_service import ProductCompanionService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "master_data.products.view"
EDIT = "master_data.products.edit"


@router.get("")
def list_product_companion_rules(
    companion_product_id: Optional[str] = Query(None),
    host_product_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    if bool(companion_product_id) == bool(host_product_id):
        raise AppException(
            status_code=422,
            message="Pass exactly one of companion_product_id or host_product_id",
        )
    service = ProductCompanionService(db)
    if companion_product_id:
        validate_uuid_path(companion_product_id, resource="Product")
        data = service.list_for_companion(companion_product_id)
    else:
        validate_uuid_path(host_product_id, resource="Product")
        data = service.list_for_host(host_product_id)
    return {"data": data}


@router.post("", response_model=ProductCompanionRuleOut, status_code=status.HTTP_201_CREATED)
def create_product_companion_rule(
    payload: ProductCompanionRuleCreate,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    created = ProductCompanionService(db).create(
        payload.model_dump(), created_by=current_user.get("id")
    )
    return created


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_companion_rule(
    rule_id: str,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(rule_id, resource="Product companion rule")
    ProductCompanionService(db).delete(rule_id)
    return None
