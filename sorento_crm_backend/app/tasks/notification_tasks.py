"""Background tasks for notification delivery (email, web push)."""
import os
import logging
from datetime import datetime

from app.database import SessionLocal
from app.models.notification import Notification, NotificationDelivery, PushSubscription
from app.models.user import User, SystemSetting
from app.services.notification_email import (
    send_notification_email,
    send_notification_email_multi,
    _smtp_config_from_settings,
)

logger = logging.getLogger(__name__)


def send_notification_deliveries(notification_id: str) -> None:
    """
    Process pending email and web_push deliveries for a notification.
    Updates each delivery row to sent or failed with error_message.
    """
    db = SessionLocal()
    try:
        notification = db.query(Notification).filter(Notification.id == notification_id).first()
        if not notification:
            logger.warning("Notification not found: %s", notification_id)
            return
        user = db.query(User).filter(User.id == notification.user_id).first()
        if not user:
            logger.warning("User not found for notification %s", notification_id)
            return

        pending = (
            db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.notification_id == notification_id,
                NotificationDelivery.status == "pending",
            )
            .all()
        )

        settings = db.query(SystemSetting).first()
        smtp_config = _smtp_config_from_settings(settings) if settings else None

        for delivery in pending:
            if delivery.channel == "email":
                data = notification.data or {}
                if data.get("single_email_to_all") and data.get("recipient_emails"):
                    body_html = data.get("body_html")
                    err = send_notification_email_multi(
                        to_list=data["recipient_emails"],
                        subject=notification.title,
                        body_text=notification.body or notification.title,
                        body_html=body_html,
                        smtp_config=smtp_config,
                    )
                else:
                    err = send_notification_email(
                        to=user.email,
                        subject=notification.title,
                        body_text=notification.body or notification.title,
                        smtp_config=smtp_config,
                    )
                delivery.status = "failed" if err else "sent"
                delivery.sent_at = datetime.utcnow() if not err else None
                delivery.error_message = err
                db.commit()
            elif delivery.channel == "web_push":
                _send_web_push_for_notification(db, notification, notification.user_id, delivery)
    finally:
        db.close()


def _send_web_push_for_notification(
    db,
    notification: Notification,
    user_id: str,
    delivery: NotificationDelivery,
) -> None:
    """Send web push to all subscriptions for user; update delivery row."""
    subs = (
        db.query(PushSubscription)
        .filter(PushSubscription.user_id == user_id)
        .all()
    )
    vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY")
    if not vapid_private_key:
        delivery.status = "failed"
        delivery.error_message = "VAPID not configured"
        db.commit()
        return
    if not subs:
        delivery.status = "sent"  # No subscriptions is not a failure
        delivery.sent_at = datetime.utcnow()
        db.commit()
        return

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        delivery.status = "failed"
        delivery.error_message = "pywebpush not installed"
        db.commit()
        return

    import json
    payload = json.dumps({
        "title": notification.title,
        "body": notification.body or "",
        "data": notification.data or {},
    })
    last_error = None
    sent_any = False
    for sub in subs:
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": "mailto:noreply@localhost"},
            )
            sent_any = True
        except WebPushException as e:
            last_error = str(e)
            logger.warning("Web push failed for subscription %s: %s", sub.id, e)
    delivery.status = "sent" if sent_any else "failed"
    delivery.sent_at = datetime.utcnow() if sent_any else None
    delivery.error_message = None if sent_any else (last_error or "No subscription succeeded")
    db.commit()
