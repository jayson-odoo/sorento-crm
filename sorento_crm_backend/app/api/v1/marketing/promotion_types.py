"""Promotion types API routes.

The vocabulary that decides what happens to a promotion after its end date, and
how an uploaded file is classified. Admin-maintained, so a sixth kind of
promotion is a row here rather than a deploy.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.schemas.common import ListResponse
from app.schemas.marketing import (
    PromotionTypeCreate,
    PromotionTypeResponse,
    PromotionTypeUpdate,
)
from app.services.error_handler import handle_internal_error
from app.services.marketing_service import PromotionTypeService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()


@router.get("/", response_model=ListResponse[PromotionTypeResponse])
async def get_promotion_types(
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Every promotion type, in display order."""
    try:
        types = PromotionTypeService(db).list_promotion_types()
        return {
            "data": types,
            "pagination": {"total": len(types), "page": 1, "limit": max(len(types), 1)},
            "empty": len(types) == 0,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{type_id}", response_model=PromotionTypeResponse)
async def get_promotion_type(
    type_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(type_id, resource="Promotion Type")
        return PromotionTypeService(db).get_promotion_type(type_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=PromotionTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_promotion_type(
    type_data: PromotionTypeCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return PromotionTypeService(db).create_promotion_type(type_data)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{type_id}", response_model=PromotionTypeResponse)
async def update_promotion_type(
    type_id: str,
    type_data: PromotionTypeUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(type_id, resource="Promotion Type")
        return PromotionTypeService(db).update_promotion_type(type_id, type_data)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{type_id}", status_code=status.HTTP_200_OK)
async def delete_promotion_type(
    type_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Hard delete. Promotions of this type become unclassified and are served
    under the default type's policy."""
    try:
        validate_uuid_path(type_id, resource="Promotion Type")
        return PromotionTypeService(db).delete_promotion_type(type_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
