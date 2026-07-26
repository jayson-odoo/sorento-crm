"""Quotations — read-only AutoCount mirror + annotation (Slice 6).

Read + annotate only. Ingest (via /external/quotations/ingest) owns creation and
every business column, including the lines. The detail response embeds the
resolved lines (product code/name, not UUIDs).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.quotation import Quotation
from app.schemas.autocount_mirror import QuotationResponse, MirrorAnnotationUpdate
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.autocount_mirror_service import MirrorReadService
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()
_RESOURCE = "Quotation"


@router.get("/", response_model=ListResponse[QuotationResponse])
async def list_quotations(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    current_user: dict = Depends(require_permission_with_api_key("order_management.quotations.view")),
    db: Session = Depends(get_db),
):
    try:
        return MirrorReadService(db).list(
            Quotation,
            search_columns=[
                Quotation.quote_number,
                Quotation.source_doc_no,
                Quotation.debtor_code,
                Quotation.debtor_name,
            ],
            page=page, limit=limit, query=query, sort=sort, dir=dir,
        )
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{quotation_id}", response_model=QuotationResponse)
async def get_quotation(
    quotation_id: str,
    current_user: dict = Depends(require_permission_with_api_key("order_management.quotations.view")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(quotation_id, resource=_RESOURCE)
        return MirrorReadService(db).get(Quotation, quotation_id, resource=_RESOURCE)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{quotation_id}/annotation", response_model=QuotationResponse)
async def annotate_quotation(
    quotation_id: str,
    payload: MirrorAnnotationUpdate,
    current_user: dict = Depends(require_permission("order_management.quotations.edit")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(quotation_id, resource=_RESOURCE)
        fields = payload.model_fields_set
        return MirrorReadService(db).annotate(
            Quotation, quotation_id, resource=_RESOURCE,
            internal_note=payload.internal_note, follow_up=payload.follow_up,
            set_note="internal_note" in fields, set_follow_up="follow_up" in fields,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
