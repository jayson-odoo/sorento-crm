"""Audit logs API routes."""
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.services.audit_service import list_audit_logs
from app.schemas.audit import AuditLogResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.models.user import User
from app.models.access import RespondContact

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


def _contact_display_names(db: Session, contact_ids: list[str]) -> dict[str, str]:
    """Return map of respond_contacts.id -> display name (name, else first+last, else phone)."""
    ids = [cid for cid in contact_ids if cid]
    if not ids:
        return {}
    rows = db.query(
        RespondContact.id, RespondContact.name,
        RespondContact.first_name, RespondContact.last_name,
        RespondContact.phone_number,
    ).filter(RespondContact.id.in_(ids)).all()
    out: dict[str, str] = {}
    for r in rows:
        name = (r.name or "").strip()
        if not name:
            name = " ".join(p for p in ((r.first_name or "").strip(), (r.last_name or "").strip()) if p).strip()
        out[str(r.id)] = name or (r.phone_number or str(r.id))
    return out


# Human-readable one-liner for a status transition, e.g. "status: pending → approved".
# Derived at serialize time from the JSONB diff — no schema/storage change.
def _derive_description(it) -> Optional[str]:
    if it.description:
        return it.description
    old = it.old_values or {}
    new = it.new_values or {}
    # Attachment upload activity: surface the filename + what happened.
    if it.entity_type == "attachment":
        fname = new.get("original_filename") or old.get("original_filename")
        if it.action in ("CREATE", "INSERT"):
            return f"Uploaded {fname}" if fname else "Uploaded a file"
        if it.action == "DELETE":
            return f"Deleted {fname}" if fname else "Deleted a file"
        # UPDATE: prefer a rename, else a description edit, else generic.
        if new.get("stored_filename") and new.get("stored_filename") != old.get("stored_filename"):
            return f"Renamed to {new.get('stored_filename')}"
        if new.get("description") != old.get("description"):
            return f"Edited file details{f' — {fname}' if fname else ''}"
        return f"Updated {fname}" if fname else "Updated a file"
    for key in ("status", "approval_status", "order_status"):
        if key in new and new.get(key) != old.get(key):
            frm = old.get(key)
            to = new.get(key)
            return f"{key}: {frm if frm is not None else '∅'} → {to}"
    return None


@router.get("/", response_model=ListResponse[AuditLogResponse])
def get_audit_logs(
    entity_type: Optional[str] = Query(None, description="Filter by entity type (e.g. complaint, stock_inquiry, purchase_request)"),
    entity_id: Optional[str] = Query(None, description="Filter by entity id"),
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None, description="INSERT, UPDATE, or DELETE"),
    trace_id: Optional[str] = Query(None, description="Filter by request correlation id (groups a multi-row change)"),
    changed_from: Optional[datetime] = Query(None, description="Filter changed_at >= (ISO); e.g. a day bar drill-down"),
    changed_to: Optional[datetime] = Query(None, description="Filter changed_at <= (ISO)"),
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
        changed_from=changed_from,
        changed_to=changed_to,
        page=page,
        limit=limit,
    )
    user_ids = list({str(it.user_id) for it in items if it.user_id is not None})
    contact_ids = list({str(it.contact_id) for it in items if getattr(it, "contact_id", None) is not None})
    user_names = _user_display_names(db, user_ids)
    contact_names = _contact_display_names(db, contact_ids)
    data = []
    for it in items:
        payload = AuditLogResponse.model_validate(it).model_dump()
        # Attribution precedence: acting contact -> staff user -> "System".
        if getattr(it, "contact_id", None) is not None and contact_names.get(str(it.contact_id)):
            payload["user_display_name"] = contact_names[str(it.contact_id)]
        elif it.user_id is not None:
            payload["user_display_name"] = user_names.get(str(it.user_id)) or "System"
        else:
            payload["user_display_name"] = "System"
        payload["description"] = _derive_description(it)
        data.append(AuditLogResponse(**payload))
    return {
        "data": data,
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }
