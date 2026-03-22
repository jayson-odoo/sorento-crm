"""Notification API routes: list, unread count, mark read, archive, resolve."""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.config import settings as app_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.services.notification_service import NotificationService
from app.services.audit_service import log_audit
from app.models.notification import PushSubscription
from app.schemas.notification import (
    NotificationResponse,
    UnreadCountResponse,
    PushSubscribeRequest,
    BulkDeleteNotificationsRequest,
)
from app.schemas.common import ListResponse
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


@router.get("/", response_model=ListResponse[NotificationResponse])
async def list_notifications(
    tab: Optional[str] = Query(None, description="all | inbox | archived"),
    status: Optional[str] = Query(None, description="read | unread"),
    type: Optional[str] = Query(None, description="Filter by notification type"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
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


@router.post("/push-subscribe")
async def push_subscribe(
    body: PushSubscribeRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register a browser push subscription for the current user. Idempotent by endpoint."""
    _require_notifications_enabled()
    try:
        existing = (
            db.query(PushSubscription)
            .filter(
                PushSubscription.user_id == current_user["id"],
                PushSubscription.endpoint == body.endpoint,
            )
            .first()
        )
        if existing:
            existing.p256dh = body.p256dh
            existing.auth = body.auth
            db.commit()
            return {"message": "Subscription updated"}
        sub = PushSubscription(
            user_id=current_user["id"],
            endpoint=body.endpoint,
            p256dh=body.p256dh,
            auth=body.auth,
        )
        db.add(sub)
        db.commit()
        return {"message": "Subscription saved"}
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
