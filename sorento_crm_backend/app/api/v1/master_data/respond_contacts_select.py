"""Internal (CRM staff) "Requested by" contact picker.

Same eligible set as the portal picker (`app.services.requestor_options_service`)
so there is one definition of "who can be a requestor" across both surfaces
(PLAN-requested-by-contact-routing.md D7). Names only, no phone / email /
respond_io_id.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.services.error_handler import handle_internal_error
from app.services.requestor_options_service import (
    DEFAULT_LIMIT,
    filter_form_referenced_ids,
    list_requestor_options,
)

router = APIRouter()


@router.get("/requestor-select")
async def get_requestor_select(
    q: Optional[str] = Query(None),
    include_ids: Optional[str] = Query(None, description="Comma-separated ids always included"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Contacts eligible to be picked as "Requested by" / "Salesperson".

    `include_ids` lets a CRM edit form always keep the row's submitting contact
    and the currently-saved requestor selectable, even if that contact belongs
    to no flagged segment (never silently blank the field on edit). It is
    filtered to ids already referenced by a form row, so the endpoint can't be
    used to resolve an arbitrary contact id to a name.
    """
    try:
        raw_ids = [v.strip() for v in include_ids.split(",") if v.strip()] if include_ids else None
        ids = filter_form_referenced_ids(db, raw_ids) if raw_ids else None
        items, has_more = list_requestor_options(
            db, q=q, limit=DEFAULT_LIMIT, include_ids=ids
        )
        return {"items": items, "has_more": has_more}
    except Exception as e:
        raise handle_internal_error(str(e))
