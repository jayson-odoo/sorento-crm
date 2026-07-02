"""Notification API routes: list, unread count, mark read, archive, resolve."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.config import settings as app_settings
from app.services.uuid_path_param import validate_uuid_path
from app.database import get_db
from app.dependencies import get_current_user
from app.services.notification_service import NotificationService
from app.services.audit_service import log_audit
from app.models.user import User
from app.services.user_sla_daily_summary_service import (
    verify_unsubscribe_token,
    set_user_daily_summary_subscription,
)
from app.schemas.notification import (
    NotificationResponse,
    UnreadCountResponse,
    BulkDeleteNotificationsRequest,
)
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()


def _require_notifications_enabled() -> None:
    if not getattr(app_settings, "notifications_v1_enabled", True):
        raise HTTPException(status_code=404, detail="Notifications feature is not enabled")


def _to_response(n):
    return NotificationResponse(
        id=str(n.id),
        user_id=n.user_id,
        type=n.type,
        title=n.title,
        body=n.body,
        data=n.data,
        read_at=n.read_at,
        archived_at=n.archived_at,
        resolved_at=n.resolved_at,
        created_at=n.created_at,
        source_entity_type=n.source_entity_type,
        source_entity_id=n.source_entity_id,
        event_type=n.event_type,
    )


@router.get("/preferences/daily-sla-summary")
async def get_daily_sla_summary_preference(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's subscription setting for daily SLA summary newsletter."""
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"subscribed": bool(getattr(user, "daily_sla_summary_subscribed", True))}


@router.patch("/preferences/daily-sla-summary")
async def set_daily_sla_summary_preference(
    subscribed: bool = Query(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update current user's subscription setting for daily SLA summary newsletter."""
    ok = set_user_daily_summary_subscription(db, current_user["id"], subscribed)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"subscribed": bool(subscribed)}


@router.get("/preferences/daily-sla-summary/unsubscribe")
async def unsubscribe_daily_sla_summary_via_token(
    token: str = Query(..., min_length=10),
    db: Session = Depends(get_db),
):
    """Public endpoint for one-click unsubscribe from email link."""
    try:
        user_id = verify_unsubscribe_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    ok = set_user_daily_summary_subscription(db, user_id, False)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Unsubscribed from daily SLA summary emails.", "subscribed": False}


_SLA_NOTIFY_FIELDS = (
    "notify_email_on_assignment",
    "notify_email_on_escalation",
    "notify_whatsapp_on_assignment",
    "notify_whatsapp_on_escalation",
    "notify_email_on_deadline_extended",
    "notify_whatsapp_on_deadline_extended",
)


class _ChannelPrefsUpdate(BaseModel):
    notify_whatsapp: Optional[bool] = None
    notify_whatsapp_summary: Optional[bool] = None
    daily_sla_summary_subscribed: Optional[bool] = None
    notify_email_on_assignment: Optional[bool] = None
    notify_email_on_escalation: Optional[bool] = None
    notify_whatsapp_on_assignment: Optional[bool] = None
    notify_whatsapp_on_escalation: Optional[bool] = None
    notify_email_on_deadline_extended: Optional[bool] = None
    notify_whatsapp_on_deadline_extended: Optional[bool] = None


def _channel_prefs(user) -> dict:
    out = {
        "daily_sla_summary_subscribed": bool(getattr(user, "daily_sla_summary_subscribed", True)),
        "notify_whatsapp": bool(getattr(user, "notify_whatsapp", False)),
        "notify_whatsapp_summary": bool(getattr(user, "notify_whatsapp_summary", False)),
    }
    # Email defaults true, whatsapp false — match the column server_defaults.
    for f in _SLA_NOTIFY_FIELDS:
        out[f] = bool(getattr(user, f, f.startswith("notify_email")))
    return out


@router.get("/preferences/channels")
async def get_channel_preferences(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Current user's per-channel notification toggles (self-service)."""
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _channel_prefs(user)


@router.patch("/preferences/channels")
async def set_channel_preferences(
    payload: _ChannelPrefsUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the current user's own channel toggles. Self-service only — a user
    can only change their own preferences (keyed off the authenticated id)."""
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    data = payload.model_dump(exclude_unset=True)
    for field in (
        "notify_whatsapp",
        "notify_whatsapp_summary",
        "daily_sla_summary_subscribed",
        *_SLA_NOTIFY_FIELDS,
    ):
        if field in data and data[field] is not None:
            setattr(user, field, bool(data[field]))
    db.commit()
    db.refresh(user)
    return _channel_prefs(user)


class _PushKeys(BaseModel):
    p256dh: str
    auth: str


class _PushSubscriptionIn(BaseModel):
    endpoint: str
    keys: _PushKeys


@router.post("/push/subscriptions", status_code=status.HTTP_201_CREATED)
async def subscribe_web_push(
    payload: _PushSubscriptionIn,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register (or refresh) a browser web-push subscription for the current user."""
    from app.models.notification import PushSubscription

    existing = (
        db.query(PushSubscription)
        .filter(
            PushSubscription.user_id == current_user["id"],
            PushSubscription.endpoint == payload.endpoint,
        )
        .first()
    )
    if existing:
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
    else:
        db.add(PushSubscription(
            user_id=current_user["id"],
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
        ))
    db.commit()
    return {"subscribed": True}


@router.delete("/push/subscriptions")
async def unsubscribe_web_push(
    endpoint: str = Query(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a browser web-push subscription for the current user."""
    from app.models.notification import PushSubscription

    db.query(PushSubscription).filter(
        PushSubscription.user_id == current_user["id"],
        PushSubscription.endpoint == endpoint,
    ).delete()
    db.commit()
    return {"subscribed": False}


@router.get("/", response_model=ListResponse[NotificationResponse])
async def list_notifications(
    tab: Optional[str] = Query(None, description="all | inbox | archived"),
    status: Optional[str] = Query(None, description="read | unread"),
    type: Optional[str] = Query(None, description="Filter by notification type"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List notifications for the current user."""
    _require_notifications_enabled()
    try:
        service = NotificationService(db)
        items, total = service.list(
            user_id=current_user["id"],
            tab=tab,
            status=status,
            type_filter=type,
            page=page,
            limit=limit,
        )
        return {
            "data": [_to_response(n) for n in items],
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    include_archived: bool = Query(False),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return unread notification count (for bell badge)."""
    _require_notifications_enabled()
    try:
        service = NotificationService(db)
        count = service.unread_count(current_user["id"], include_archived=include_archived)
        return {"count": count}
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a single notification as read."""
    _require_notifications_enabled()
    try:
        validate_uuid_path(notification_id, resource="Notification")
        service = NotificationService(db)
        n = service.mark_read(notification_id, current_user["id"])
        if not n:
            raise HTTPException(status_code=404, detail="Notification not found")
        log_audit(db, "notification", notification_id, "UPDATE", user_id=current_user["id"], new_values={"operation": "mark_read"})
        db.commit()
        return _to_response(n)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{notification_id}/unread", response_model=NotificationResponse)
async def mark_unread(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a single notification as unread (clear read status)."""
    _require_notifications_enabled()
    try:
        validate_uuid_path(notification_id, resource="Notification")
        service = NotificationService(db)
        n = service.mark_unread(notification_id, current_user["id"])
        if not n:
            raise HTTPException(status_code=404, detail="Notification not found")
        log_audit(db, "notification", notification_id, "UPDATE", user_id=current_user["id"], new_values={"operation": "mark_unread"})
        db.commit()
        return _to_response(n)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/mark-all-read")
async def mark_all_read(
    archived: Optional[bool] = Query(None, description="If set, only mark all in that tab"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark all notifications as read."""
    _require_notifications_enabled()
    try:
        service = NotificationService(db)
        count = service.mark_all_read(current_user["id"], archived=archived)
        # Use sentinel UUID for bulk ops so entity_id is valid if column is UUID type
        log_audit(db, "notification", "00000000-0000-0000-0000-000000000000", "UPDATE", user_id=current_user["id"], new_values={"operation": "mark_all_read", "count": count})
        db.commit()
        return {"message": "Marked as read", "count": count}
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{notification_id}/archive", response_model=NotificationResponse)
async def archive_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Archive a single notification."""
    _require_notifications_enabled()
    try:
        validate_uuid_path(notification_id, resource="Notification")
        service = NotificationService(db)
        n = service.archive(notification_id, current_user["id"])
        if not n:
            raise HTTPException(status_code=404, detail="Notification not found")
        log_audit(db, "notification", notification_id, "UPDATE", user_id=current_user["id"], new_values={"operation": "archive"})
        db.commit()
        return _to_response(n)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/archive-all")
async def archive_all(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Archive all notifications."""
    _require_notifications_enabled()
    try:
        service = NotificationService(db)
        count = service.archive_all(current_user["id"])
        log_audit(db, "notification", "00000000-0000-0000-0000-000000000000", "UPDATE", user_id=current_user["id"], new_values={"operation": "archive_all", "count": count})
        db.commit()
        return {"message": "Archived", "count": count}
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/bulk-delete")
async def bulk_delete_notifications(
    body: BulkDeleteNotificationsRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete multiple notifications for the current user."""
    _require_notifications_enabled()
    try:
        service = NotificationService(db)
        count = service.delete_many(body.ids, current_user["id"])
        log_audit(
            db,
            "notification",
            "00000000-0000-0000-0000-000000000000",
            "DELETE",
            user_id=current_user["id"],
            new_values={"operation": "bulk_delete", "count": count},
        )
        db.commit()
        return {"message": "Deleted", "count": count}
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/delete-all")
async def delete_all_notifications(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete all notifications for the current user."""
    _require_notifications_enabled()
    try:
        service = NotificationService(db)
        count = service.delete_all(current_user["id"])
        log_audit(
            db,
            "notification",
            "00000000-0000-0000-0000-000000000000",
            "DELETE",
            user_id=current_user["id"],
            new_values={"operation": "delete_all", "count": count},
        )
        db.commit()
        return {"message": "Deleted", "count": count}
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete a single notification."""
    _require_notifications_enabled()
    try:
        validate_uuid_path(notification_id, resource="Notification")
        service = NotificationService(db)
        ok = service.delete(notification_id, current_user["id"])
        if not ok:
            raise HTTPException(status_code=404, detail="Notification not found")
        log_audit(
            db,
            "notification",
            notification_id,
            "DELETE",
            user_id=current_user["id"],
            new_values={"operation": "delete"},
        )
        db.commit()
        return {"message": "Deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{notification_id}/resolve", response_model=NotificationResponse)
async def resolve_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a notification as resolved (for actionable items)."""
    _require_notifications_enabled()
    try:
        validate_uuid_path(notification_id, resource="Notification")
        service = NotificationService(db)
        n = service.resolve(notification_id, current_user["id"])
        if not n:
            raise HTTPException(status_code=404, detail="Notification not found")
        log_audit(db, "notification", notification_id, "UPDATE", user_id=current_user["id"], new_values={"operation": "resolve"})
        db.commit()
        return _to_response(n)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
