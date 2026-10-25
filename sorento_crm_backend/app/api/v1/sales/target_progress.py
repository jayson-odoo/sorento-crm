"""`GET /api/v1/sales/target-progress`: the chatbot's sales target answer (SALES-TARGET-CHAT).

Reuses the target engine (`target_service.period_progress`); who sees which target is
`target_chat_scope`. Gates, in order: `sales.reports.view` on the act-as principal (the route
dependency, the sibling sales analysis route's gate), the `sales` module (router guard), both
contact ids (422 `contact_identity_required`), then the CONTACT's own `sales.sales_target`
reveal key (403 `sales_target_not_enabled`).

API key only, for the reason `analysis.py` gives: the figures are the CONTACT's, which says
nothing about a Bearer caller's own grant.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.services.error_handler import AppException

router = APIRouter()

_GATE = require_permission_with_api_key("sales.reports.view")

GRANT = "sales.sales_target"


@router.get("/target-progress")
def get_target_progress(
    request: Request,
    contact_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    customer_ids: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(_GATE),
):
    from app.services.contact_field_reveal_service import granted_keys
    from app.services.field_access import resolve_contact_with_null_workspace_fallback
    from app.services.sales import target_chat_scope

    if not request.headers.get("X-API-Key"):
        raise AppException(status_code=403, message="This route is for the chatbot only", code="api_key_required")
    if not contact_id or not space_id:
        raise AppException(
            status_code=422, message="contact_id and space_id are required", code="contact_identity_required"
        )
    if date_from and date_to and date_from > date_to:
        raise AppException(status_code=422, message="date_from is after date_to", code="date_range_inverted")
    resolved = resolve_contact_with_null_workspace_fallback(db, contact_id=contact_id, space_id=space_id)
    if not resolved or GRANT not in granted_keys(db, resolved):
        raise AppException(
            status_code=403, message="Sales target is not enabled for your account.", code="sales_target_not_enabled"
        )
    return target_chat_scope.target_progress(
        db,
        contact_id=str(resolved),
        date_from=date_from,
        date_to=date_to,
        customer_ids=[c for raw in customer_ids or [] for c in raw.split(",") if c],
    )
