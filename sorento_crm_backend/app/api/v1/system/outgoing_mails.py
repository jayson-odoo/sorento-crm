"""Outgoing email log API routes (notification deliveries)."""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional

from app.database import get_db
from app.dependencies import require_permission
from app.models.notification import Notification, NotificationDelivery
from app.models.user import User
from app.schemas.common import ListResponse
from app.schemas.outgoing_mail import OutgoingMailResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/outgoing-mails", response_model=ListResponse[OutgoingMailResponse])
async def list_outgoing_mails(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None, description="pending | sent | failed"),
    query: Optional[str] = Query(None, description="Search by recipient email or subject"),
    current_user: dict = Depends(require_permission("system.outgoing_mails.view")),
    db: Session = Depends(get_db),
):
    """List outgoing email deliveries (from notifications)."""
    try:
        q = (
            db.query(NotificationDelivery, Notification, User)
            .join(Notification, Notification.id == NotificationDelivery.notification_id)
            .join(User, User.id == Notification.user_id)
            .filter(NotificationDelivery.channel == "email")
        )
        if status and status.strip():
            q = q.filter(NotificationDelivery.status == status.strip())
        if query and query.strip():
            term = f"%{query.strip()}%"
            q = q.filter(or_(User.email.ilike(term), Notification.title.ilike(term)))

        total = q.count()
        offset = (page - 1) * limit
        rows = (
            q.order_by(NotificationDelivery.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        data: list[OutgoingMailResponse] = []
        for delivery, notif, user in rows:
            notif_data = getattr(notif, "data", None) or {}
            if not isinstance(notif_data, dict):
                notif_data = {}
            to_email = ", ".join(notif_data["recipient_emails"]) if notif_data.get("recipient_emails") else str(user.email or "")
            # Email content: notification.body, or from data (body_text / body_html)
            body = getattr(notif, "body", None) or notif_data.get("body_text") or notif_data.get("body_html")
            data.append(
                OutgoingMailResponse(
                    id=str(delivery.id),
                    notification_id=str(notif.id),
                    user_id=str(user.id),
                    to_email=to_email,
                    subject=str(notif.title or ""),
                    body=body,
                    status=str(delivery.status or ""),
                    created_at=delivery.created_at,
                    sent_at=delivery.sent_at,
                    error_message=delivery.error_message,
                    notification_type=getattr(notif, "type", None),
                    source_entity_type=getattr(notif, "source_entity_type", None),
                    source_entity_id=getattr(notif, "source_entity_id", None),
                    event_type=getattr(notif, "event_type", None),
                )
            )

        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise handle_internal_error(str(exc))

