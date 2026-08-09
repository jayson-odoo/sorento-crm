"""Warranty product kinds - what a thing IS, for warranty purposes (AC-D1).

A SHARED vocabulary: "Water Closet" is one physical thing whichever brand sells it,
so Kinds are not company-scoped and the screen says so (AC-P10).

The list carries `rule_count`, `term_count` and the two explicit zero flags
(AC-P7 / AC-P7a / AC-P17). That is the whole point of this slice: 29 of the 31
Kinds on the live database are unreachable by any rule, and nothing on any screen
says so.

A bare array, not `ListResponse` (AC-P14): tens of rows, no server-side paging, and
the frontend casts the body straight to an array.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.warranty_config import (
    KindCreate,
    KindResponse,
    KindUpdate,
    WarrantyKindRef,
)
from app.services.uuid_path_param import validate_uuid_path
from app.services.warranty_config_service import WarrantyConfigService

router = APIRouter()


@router.get("", response_model=List[KindResponse])
async def list_warranty_kinds(
    query: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    current_user: dict = Depends(require_permission_with_api_key("warranty.kinds.view")),
    db: Session = Depends(get_db),
):
    return WarrantyConfigService(db).list_kinds(query=query, is_active=is_active, limit=limit)


@router.get("/select", response_model=List[WarrantyKindRef])
async def list_warranty_kind_options(
    query: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    current_user: dict = Depends(require_permission_with_api_key("warranty.kinds.view")),
    db: Session = Depends(get_db),
):
    """The dropdown feed for the Term and Rule editors. `code` AND `name`, because
    the cursor rule forbids a UUID on screen."""
    return WarrantyConfigService(db).list_kind_options(query=query, limit=limit)


@router.post("", response_model=KindResponse, status_code=status.HTTP_201_CREATED)
async def create_warranty_kind(
    payload: KindCreate,
    current_user: dict = Depends(require_permission("warranty.kinds.add")),
    db: Session = Depends(get_db),
):
    return WarrantyConfigService(db).create_kind(payload)


@router.patch("/{kind_id}", response_model=KindResponse)
async def update_warranty_kind(
    kind_id: str,
    payload: KindUpdate,
    current_user: dict = Depends(require_permission("warranty.kinds.edit")),
    db: Session = Depends(get_db),
):
    validate_uuid_path(kind_id, resource="Warranty Product Kind")
    return WarrantyConfigService(db).update_kind(kind_id, payload)


@router.delete("/{kind_id}")
async def delete_warranty_kind(
    kind_id: str,
    current_user: dict = Depends(require_permission("warranty.kinds.delete")),
    db: Session = Depends(get_db),
):
    """Refused while any Term or Kind Rule references it (AC-P12), naming both
    counts. Both FKs cascade, so the obvious hard delete would silently remove
    warranty promises from every policy at once."""
    validate_uuid_path(kind_id, resource="Warranty Product Kind")
    return WarrantyConfigService(db).delete_kind(kind_id)
