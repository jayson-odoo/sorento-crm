"""Cross-Entity Activity Timeline API.

``GET /api/v1/audit/activity`` - a human-readable, label-resolved view over the
raw ``audit_logs`` table (see ``app.services.activity_service``). Auth-only, same
as the Audit Logs listing; no bespoke permission slug.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.schemas.common import MAX_PAGE_LIMIT
from app.services.activity_service import get_activity_feed

router = APIRouter()


@router.get("/activity")
async def get_activity(
    entity_type: Optional[list[str]] = Query(
        None,
        description="Repeatable or CSV FE entity type(s): complaint, order, user, "
        "supplier, promotion, form, ticket, stock_inquiry, purchase_request, product, "
        "customer",
    ),
    action: Optional[str] = Query(
        None, description="created | updated | deleted"
    ),
    user_id: Optional[str] = Query(None, description="Actor filter (users.id)"),
    date_from: Optional[str] = Query(None, description="yyyy-MM-dd inclusive (changed_at)"),
    date_to: Optional[str] = Query(None, description="yyyy-MM-dd inclusive (changed_at)"),
    q: Optional[str] = Query(None, description="Free text over entity_id + description"),
    trace_id: Optional[str] = Query(None, description="Group one multi-row action"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Return ``{items, actors, pagination}`` for the activity timeline."""
    # Accept both repeatable (?entity_type=a&entity_type=b) and CSV (?entity_type=a,b).
    entity_types: Optional[list[str]] = None
    if entity_type:
        entity_types = [
            part.strip()
            for value in entity_type
            for part in value.split(",")
            if part.strip()
        ] or None

    return get_activity_feed(
        db,
        entity_types=entity_types,
        action=action,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
        trace_id=trace_id,
        page=page,
        limit=limit,
    )
