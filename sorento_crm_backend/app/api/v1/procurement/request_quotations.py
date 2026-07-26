"""Request quotations — read-only AutoCount mirror + annotation (Slice 7).

Read + annotate only. Ingest (via /external/request-quotations/ingest) owns
creation and every business column, including the lines. The detail response
embeds the resolved lines (product code/name) and supplier (code/name), not UUIDs.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.request_quotation import RequestQuotation
from app.schemas.autocount_mirror import RequestQuotationResponse, MirrorAnnotationUpdate
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.autocount_mirror_service import MirrorReadService
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()
_RESOURCE = "Request Quotation"


@router.get("/", response_model=ListResponse[RequestQuotationResponse])
async def list_request_quotations(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    current_user: dict = Depends(require_permission_with_api_key("procurement.request_quotations.view")),
    db: Session = Depends(get_db),
):
    try:
        return MirrorReadService(db).list(
            RequestQuotation,
            search_columns=[
                RequestQuotation.rq_number,
                RequestQuotation.source_doc_no,
                RequestQuotation.creditor_code,
                RequestQuotation.creditor_name,
            ],
            page=page, limit=limit, query=query, sort=sort, dir=dir,
        )
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{request_quotation_id}", response_model=RequestQuotationResponse)
async def get_request_quotation(
    request_quotation_id: str,
    current_user: dict = Depends(require_permission_with_api_key("procurement.request_quotations.view")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(request_quotation_id, resource=_RESOURCE)
        return MirrorReadService(db).get(RequestQuotation, request_quotation_id, resource=_RESOURCE)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{request_quotation_id}/annotation", response_model=RequestQuotationResponse)
async def annotate_request_quotation(
    request_quotation_id: str,
    payload: MirrorAnnotationUpdate,
    current_user: dict = Depends(require_permission("procurement.request_quotations.edit")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(request_quotation_id, resource=_RESOURCE)
        fields = payload.model_fields_set
        return MirrorReadService(db).annotate(
            RequestQuotation, request_quotation_id, resource=_RESOURCE,
            internal_note=payload.internal_note, follow_up=payload.follow_up,
            set_note="internal_note" in fields, set_follow_up="follow_up" in fields,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
