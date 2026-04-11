"""Background tasks for notification delivery (email, web push)."""
import os
import logging
import importlib
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
            channel = str(getattr(delivery, "channel", ""))
            if channel == "email":
                raw_data = getattr(notification, "data", None)
                data = raw_data if isinstance(raw_data, dict) else {}
                notification_title = str(getattr(notification, "title", ""))
                notification_body = getattr(notification, "body", None)
                body_text = str(notification_body) if notification_body is not None else notification_title
                if data.get("single_email_to_all") and data.get("recipient_emails"):
                    body_html = data.get("body_html")
                    recipient_emails = [str(email) for email in data.get("recipient_emails", [])]
                    err = send_notification_email_multi(
                        to_list=recipient_emails,
                        subject=notification_title,
                        body_text=body_text,
                        body_html=body_html,
                        smtp_config=smtp_config,
                    )
                else:
                    body_html = data.get("body_html")
                    err = send_notification_email(
                        to=str(getattr(user, "email", "")),
                        subject=notification_title,
                        body_text=body_text,
                        body_html=body_html,
                        smtp_config=smtp_config,
                    )
                setattr(delivery, "status", "failed" if err else "sent")
                setattr(delivery, "sent_at", datetime.utcnow() if err is None else None)
                setattr(delivery, "error_message", err)
                db.commit()
            elif channel == "web_push":
                _send_web_push_for_notification(
                    db,
                    notification,
                    str(getattr(notification, "user_id")),
                    delivery,
                )
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
        setattr(delivery, "status", "failed")
        setattr(delivery, "error_message", "VAPID not configured")
        db.commit()
        return
    if not subs:
        setattr(delivery, "status", "sent")  # No subscriptions is not a failure
        setattr(delivery, "sent_at", datetime.utcnow())
        db.commit()
        return

    try:
        pywebpush_module = importlib.import_module("pywebpush")
        webpush = getattr(pywebpush_module, "webpush")
        WebPushException = getattr(pywebpush_module, "WebPushException")
    except Exception:
        setattr(delivery, "status", "failed")
        setattr(delivery, "error_message", "pywebpush not installed")
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
    setattr(delivery, "status", "sent" if sent_any else "failed")
    setattr(delivery, "sent_at", datetime.utcnow() if sent_any else None)
    setattr(delivery, "error_message", None if sent_any else (last_error or "No subscription succeeded"))
    db.commit()
