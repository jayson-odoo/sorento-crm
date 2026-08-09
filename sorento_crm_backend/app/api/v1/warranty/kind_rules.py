"""Warranty kind rules - how a product reaches a Kind (AC-D2), plus the tester.

Kind rules ride the KINDS permission slug (AC-P11): a rule has no life apart from
the Kind it points at.

The tester answers from `rank_kind_matches` - the PRODUCTION ranking (AC-P6a). A
tester with its own ranking agrees with production right up to the day it matters,
and the day it matters is the day an admin uses it to decide that a mapping is safe.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.warranty_config import (
    KindRuleCreate,
    KindRuleResponse,
    KindRuleTestRequest,
    KindRuleTestResponse,
    KindRuleUpdate,
)
from app.services.uuid_path_param import validate_uuid_path
from app.services.warranty_config_service import WarrantyConfigService

router = APIRouter()


@router.get("", response_model=List[KindRuleResponse])
async def list_warranty_kind_rules(
    kind_id: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    current_user: dict = Depends(require_permission_with_api_key("warranty.kinds.view")),
    db: Session = Depends(get_db),
):
    return WarrantyConfigService(db).list_kind_rules(kind_id=kind_id, limit=limit)


@router.post("/test", response_model=KindRuleTestResponse)
async def test_warranty_kind_rules(
    payload: KindRuleTestRequest,
    current_user: dict = Depends(require_permission_with_api_key("warranty.kinds.view")),
    db: Session = Depends(get_db),
):
    """AC-P6 / AC-P6b / AC-P6c. Names the resolved Kind, the rule that decided it,
    and every rule that matched in rank order - so an admin can tell a working
    mapping from a lucky one BEFORE saving. The optional candidate rule is ranked
    alongside the saved ones and is never written.

    A read: it answers a question, it changes nothing.
    """
    return WarrantyConfigService(db).test_kind_rules(payload)


@router.post("", response_model=KindRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_warranty_kind_rule(
    payload: KindRuleCreate,
    current_user: dict = Depends(require_permission("warranty.kinds.add")),
    db: Session = Depends(get_db),
):
    return WarrantyConfigService(db).create_kind_rule(payload)


@router.patch("/{rule_id}", response_model=KindRuleResponse)
async def update_warranty_kind_rule(
    rule_id: str,
    payload: KindRuleUpdate,
    current_user: dict = Depends(require_permission("warranty.kinds.edit")),
    db: Session = Depends(get_db),
):
    validate_uuid_path(rule_id, resource="Warranty Kind Rule")
    return WarrantyConfigService(db).update_kind_rule(rule_id, payload)


@router.delete("/{rule_id}")
async def delete_warranty_kind_rule(
    rule_id: str,
    current_user: dict = Depends(require_permission("warranty.kinds.delete")),
    db: Session = Depends(get_db),
):
    validate_uuid_path(rule_id, resource="Warranty Kind Rule")
    return WarrantyConfigService(db).delete_kind_rule(rule_id)
