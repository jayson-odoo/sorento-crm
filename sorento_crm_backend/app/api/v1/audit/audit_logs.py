"""Audit logs API routes."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.services.audit_service import list_audit_logs
from app.schemas.audit import AuditLogResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.models.user import User

router = APIRouter()


def _user_display_names(db: Session, user_ids: list[str]) -> dict[str, str]:
    """Return map of user_id -> name (or email fallback) for given ids."""
    ids = [uid for uid in user_ids if uid]
    if not ids:
        return {}
    users = db.query(User.id, User.name, User.email).filter(User.id.in_(ids)).all()
    return {
        str(u.id): (u.name.strip() if u.name and u.name.strip() else u.email or str(u.id))
        for u in users
    }


@router.get("/", response_model=ListResponse[AuditLogResponse])
async def get_audit_logs(
    entity_type: Optional[str] = Query(None, description="Filter by entity type (e.g. complaint, stock_inquiry, purchase_request)"),
    entity_id: Optional[str] = Query(None, description="Filter by entity id"),
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None, description="INSERT, UPDATE, or DELETE"),
    trace_id: Optional[str] = Query(None, description="Filter by request correlation id (groups a multi-row change)"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """List audit log entries, optionally filtered by entity_type and entity_id (for per-record history)."""
    items, total = list_audit_logs(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        trace_id=trace_id,
        page=page,
        limit=limit,
    )
    user_ids = list({str(it.user_id) for it in items if it.user_id is not None})
    user_names = _user_display_names(db, user_ids)
    data = []
    for it in items:
        payload = AuditLogResponse.model_validate(it).model_dump()
        payload["user_display_name"] = (
            user_names.get(str(it.user_id)) if it.user_id is not None else "System"
        )
        data.append(AuditLogResponse(**payload))
    return {
        "data": data,
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }
