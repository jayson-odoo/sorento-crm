"""Tax codes — read-only AutoCount mirror + annotation (Slice 1).

Read + annotate only (see credit_terms.py). Ingest owns the record.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.tax_code import TaxCode
from app.schemas.autocount_mirror import MirrorAnnotationUpdate, TaxCodeResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.autocount_mirror_service import MirrorReadService
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()
_RESOURCE = "Tax Code"


@router.get("/", response_model=ListResponse[TaxCodeResponse])
async def list_tax_codes(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    current_user: dict = Depends(require_permission_with_api_key("master_data.tax_codes.view")),
    db: Session = Depends(get_db),
):
    try:
        return MirrorReadService(db).list(
            TaxCode,
            search_columns=[TaxCode.tax_code, TaxCode.supply_purchase],
            page=page,
            limit=limit,
            query=query,
            sort=sort,
            dir=dir,
        )
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{tax_code_id}", response_model=TaxCodeResponse)
async def get_tax_code(
    tax_code_id: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.tax_codes.view")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(tax_code_id, resource=_RESOURCE)
        return MirrorReadService(db).get(TaxCode, tax_code_id, resource=_RESOURCE)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{tax_code_id}/annotation", response_model=TaxCodeResponse)
async def annotate_tax_code(
    tax_code_id: str,
    payload: MirrorAnnotationUpdate,
    current_user: dict = Depends(require_permission("master_data.tax_codes.edit")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(tax_code_id, resource=_RESOURCE)
        fields = payload.model_fields_set
        return MirrorReadService(db).annotate(
            TaxCode,
            tax_code_id,
            resource=_RESOURCE,
            internal_note=payload.internal_note,
            follow_up=payload.follow_up,
            set_note="internal_note" in fields,
            set_follow_up="follow_up" in fields,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
