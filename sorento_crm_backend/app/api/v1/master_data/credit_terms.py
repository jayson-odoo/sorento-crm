"""Credit terms — read-only AutoCount mirror + annotation (Slice 1).

Ingest (via the ESB, /external/ingest/credit_terms) owns creation and every
business column. This surface is read + annotate only: no POST/PUT/DELETE of the
record. The single write is PATCH /{id}/annotation, which touches only the two
Sorento-only columns.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.credit_term import CreditTerm
from app.schemas.autocount_mirror import CreditTermResponse, MirrorAnnotationUpdate
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.autocount_mirror_service import MirrorReadService
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()
_RESOURCE = "Credit Term"


@router.get("/", response_model=ListResponse[CreditTermResponse])
async def list_credit_terms(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    current_user: dict = Depends(require_permission_with_api_key("master_data.credit_terms.view")),
    db: Session = Depends(get_db),
):
    try:
        return MirrorReadService(db).list(
            CreditTerm,
            search_columns=[CreditTerm.display_term, CreditTerm.terms],
            page=page,
            limit=limit,
            query=query,
            sort=sort,
            dir=dir,
        )
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{credit_term_id}", response_model=CreditTermResponse)
async def get_credit_term(
    credit_term_id: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.credit_terms.view")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(credit_term_id, resource=_RESOURCE)
        return MirrorReadService(db).get(CreditTerm, credit_term_id, resource=_RESOURCE)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{credit_term_id}/annotation", response_model=CreditTermResponse)
async def annotate_credit_term(
    credit_term_id: str,
    payload: MirrorAnnotationUpdate,
    current_user: dict = Depends(require_permission("master_data.credit_terms.edit")),
    db: Session = Depends(get_db),
):
    """Update ONLY the Sorento-only note / follow-up flag. Survives re-sync."""
    try:
        validate_uuid_path(credit_term_id, resource=_RESOURCE)
        fields = payload.model_fields_set
        return MirrorReadService(db).annotate(
            CreditTerm,
            credit_term_id,
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
