"""Warranty policies - the dated documents a complaint is judged against (AC-P1).

Thin by design: every rule lives in `warranty_config_service`. Reads take
`require_permission_with_api_key`, writes take `require_permission` (AC-P11) -
`require_permission_with_api_key` is documented as read-oriented, and the two write
exceptions in this codebase both carry a second real-user gate at the assistant
layer that nothing in S7b has.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.warranty_config import (
    PolicyCreate,
    PolicyResponse,
    PolicyUpdate,
    SupersedeResponse,
)
from app.services.uuid_path_param import validate_uuid_path
from app.services.warranty_config_service import WarrantyConfigService

router = APIRouter()


@router.get("", response_model=ListResponse[PolicyResponse])
async def list_warranty_policies(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key("warranty.policies.view")),
    db: Session = Depends(get_db),
):
    return WarrantyConfigService(db).list_policies(
        page=page, limit=limit, query=query, sort=sort, dir=dir
    )


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_warranty_policy(
    policy_id: str,
    current_user: dict = Depends(require_permission_with_api_key("warranty.policies.view")),
    db: Session = Depends(get_db),
):
    validate_uuid_path(policy_id, resource="Warranty Policy")
    return WarrantyConfigService(db).get_policy(policy_id)


@router.post("", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_warranty_policy(
    payload: PolicyCreate,
    current_user: dict = Depends(require_permission("warranty.policies.add")),
    db: Session = Depends(get_db),
):
    return WarrantyConfigService(db).create_policy(payload)


@router.patch("/{policy_id}", response_model=PolicyResponse)
async def update_warranty_policy(
    policy_id: str,
    payload: PolicyUpdate,
    current_user: dict = Depends(require_permission("warranty.policies.edit")),
    db: Session = Depends(get_db),
):
    validate_uuid_path(policy_id, resource="Warranty Policy")
    return WarrantyConfigService(db).update_policy(policy_id, payload)


@router.delete("/{policy_id}")
async def delete_warranty_policy(
    policy_id: str,
    current_user: dict = Depends(require_permission("warranty.policies.delete")),
    db: Session = Depends(get_db),
):
    """Hard delete. The Terms go with it (AC-P13) - they have no life apart from the
    Policy that dates them, which is why `term_count` rides on the row so the
    confirmation can name how many."""
    validate_uuid_path(policy_id, resource="Warranty Policy")
    return WarrantyConfigService(db).delete_policy(policy_id)


@router.post(
    "/{policy_id}/supersede",
    response_model=SupersedeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def supersede_warranty_policy(
    policy_id: str,
    payload: PolicyCreate,
    current_user: dict = Depends(require_permission("warranty.policies.add")),
    db: Session = Depends(get_db),
):
    """AC-P2a: close the incumbent the day before the new version starts and create
    the new version, in ONE transaction.

    AC-P2's refusal is right and, alone, turns the screen's main job - publishing
    version N+1 - into a two-step an admin must perform in the correct order.
    """
    validate_uuid_path(policy_id, resource="Warranty Policy")
    return WarrantyConfigService(db).supersede_policy(policy_id, payload)
