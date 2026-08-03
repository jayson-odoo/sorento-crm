"""The Respond outbox screen's read model (AC-H8, AC-H9, AC-H10).

Separate from ``integrations/logs`` because that route is the generic integration-log
list and this one answers a different question: what have we actually told this person,
about which event, and did it arrive.

Authenticated only, and worth stating why: the payload carries customer phone numbers
and the text of messages sent to them.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.schemas.common import MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error
from app.services.respond_outbox_service import list_outbox

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("")
async def get_respond_outbox(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    business_id: Optional[str] = Query(None, description="Scope to one case / entity row"),
    business_table: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="success | failed | pending"),
    event_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Outbound Respond.io sends with their event context, newest first."""
    try:
        return list_outbox(
            db,
            page=page,
            limit=limit,
            business_id=business_id,
            business_table=business_table,
            status=status,
            event_type=event_type,
        )
    except Exception as e:  # noqa: BLE001
        logger.error("Error listing the Respond outbox: %s", e, exc_info=True)
        raise handle_internal_error(str(e))
