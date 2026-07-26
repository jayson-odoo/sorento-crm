"""Payment methods — read-only AutoCount mirror + annotation (Slice 2)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.payment_method import PaymentMethod
from app.schemas.autocount_mirror import MirrorAnnotationUpdate, PaymentMethodResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.autocount_mirror_service import MirrorReadService
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()
_RESOURCE = "Payment Method"


@router.get("/", response_model=ListResponse[PaymentMethodResponse])
async def list_payment_methods(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    current_user: dict = Depends(require_permission_with_api_key("master_data.payment_methods.view")),
    db: Session = Depends(get_db),
):
    try:
        return MirrorReadService(db).list(
            PaymentMethod,
            search_columns=[PaymentMethod.payment_method, PaymentMethod.description],
            page=page, limit=limit, query=query, sort=sort, dir=dir,
        )
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{payment_method_id}", response_model=PaymentMethodResponse)
async def get_payment_method(
    payment_method_id: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.payment_methods.view")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(payment_method_id, resource=_RESOURCE)
        return MirrorReadService(db).get(PaymentMethod, payment_method_id, resource=_RESOURCE)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{payment_method_id}/annotation", response_model=PaymentMethodResponse)
async def annotate_payment_method(
    payment_method_id: str,
    payload: MirrorAnnotationUpdate,
    current_user: dict = Depends(require_permission("master_data.payment_methods.edit")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(payment_method_id, resource=_RESOURCE)
        fields = payload.model_fields_set
        return MirrorReadService(db).annotate(
            PaymentMethod, payment_method_id, resource=_RESOURCE,
            internal_note=payload.internal_note, follow_up=payload.follow_up,
            set_note="internal_note" in fields, set_follow_up="follow_up" in fields,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
