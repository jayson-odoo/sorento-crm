"""Notify the uploader when an attachment is sent to the n8n integration webhook."""
from __future__ import annotations

import html
import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)


def flush_notification_email_deliveries(notification_ids: list[str]) -> None:
    """
    Process pending email (and web_push) deliveries immediately.
    Use after creating notifications so Outgoing Mails shows rows and SMTP runs without waiting for RQ worker.
    Safe if a worker also processes the same notification: deliveries flip to sent on first success.
    """
    for nid in notification_ids:
        if not nid:
            continue
        try:
            from app.tasks import notification_tasks

            notification_tasks.send_notification_deliveries(nid)
        except Exception as e:
            logger.warning(
                "Immediate notification delivery failed for notification %s: %s",
                nid,
                e,
                exc_info=True,
            )


def build_attachment_detail_url(attachment_id: str) -> str:
    """Absolute URL to the attachment detail page in the frontend app."""
    base = (settings.frontend_base_url or "").strip().rstrip("/")
    path = f"/resource-management/attachments/{attachment_id}"
    return f"{base}{path}" if base else path


def build_promotion_detail_url(promotion_id: str) -> str:
    """Absolute URL to the promotion detail page in the frontend app."""
    base = (settings.frontend_base_url or "").strip().rstrip("/")
    path = f"/marketing-management/promotions/{promotion_id}"
    return f"{base}{path}" if base else path


def notify_uploaders_after_external_promotion_created(
    db: Session,
    attachment_ids: list[str],
    promotion,
    *,
    notification_batch_id: str,
) -> tuple[list[str], set[str]]:
    """
    In-app + email when POST /external/promotions succeeds and links attachment(s).
    Notifies each distinct uploader (uploaded_by) for this API invocation, with links to the promotion and their file(s).

    notification_batch_id scopes idempotency so each external API call can notify again (e.g. same promo code / resubmit).

    Returns (notification_ids_for_email_flush, uploader_user_ids_notified).
    """
    empty: tuple[list[str], set[str]] = ([], set())
    if not getattr(settings, "notifications_v1_enabled", True):
        return empty

    deduped: list[str] = []
    for aid in attachment_ids or []:
        s = (aid or "").strip()
        if s and s not in deduped:
            deduped.append(s)
    if not deduped:
        return empty

    from app.models.resources import Attachment
    from app.models.user import User
    from app.services.notification_service import NotificationService

    atts = db.query(Attachment).filter(Attachment.id.in_(deduped)).all()
    by_user: dict[str, list] = {}
    for a in atts:
        uid = (getattr(a, "uploaded_by", None) or "").strip()
        if not uid:
            logger.debug("External promotion notify: attachment %s has no uploaded_by", a.id)
            continue
        by_user.setdefault(uid, []).append(a)

    if not by_user:
        return empty

    notification_ids: list[str] = []
    uploader_ids: set[str] = set()

    promo_id = str(getattr(promotion, "id", "") or "")
    promo_code = (getattr(promotion, "promo_code", None) or "").strip() or "—"
    promo_name = (getattr(promotion, "name", None) or "").strip() or promo_code
    promo_url = build_promotion_detail_url(promo_id)
    notify_source_id = f"{promo_id}_{notification_batch_id}"

    notif_svc = NotificationService(db)

    for uid, user_atts in by_user.items():
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            logger.debug("External promotion notify: user %s not found", uid)
            continue

        names = [getattr(x, "original_filename", None) or "file" for x in user_atts]
        names_list = ", ".join(f'"{n}"' for n in names)
        safe_names_html = ", ".join(f"<strong>{html.escape(n)}</strong>" for n in names)

        att_lines_plain = "\n".join(
            f"  - {n}: {build_attachment_detail_url(str(x.id))}" for n, x in zip(names, user_atts)
        )
        att_li_html = "".join(
            f'<li><a href="{html.escape(build_attachment_detail_url(str(x.id)), quote=True)}">{html.escape(n)}</a></li>'
            for n, x in zip(names, user_atts)
        )

        title = f"Promotion created: {promo_code}"
        body_plain = (
            f'A promotion "{promo_name}" ({promo_code}) was created in Sorento CRM using your uploaded file(s): '
            f"{names_list}.\n\n"
            f"This was triggered by the external integration (for example n8n) after your attachment(s) were processed.\n\n"
            f"View promotion:\n{promo_url}\n\n"
            f"Your attachment(s):\n{att_lines_plain}\n\n"
            f"This is a system generated email. Please do not reply."
        )
        body_html = (
            f"<p>A promotion <strong>{html.escape(promo_name)}</strong> "
            f"(<strong>{html.escape(promo_code)}</strong>) was created in Sorento CRM using your uploaded file(s): "
            f"{safe_names_html}.</p>"
            f"<p>This was triggered by the external integration (for example n8n) after your attachment(s) were processed.</p>"
            f'<p><a href="{html.escape(promo_url, quote=True)}">Open promotion in Sorento CRM</a></p>'
            f"<p>Your attachment(s):</p><ul>{att_li_html}</ul>"
            f'<p style="color:#666;font-size:12px;margin-top:1.5em;">This is a system generated email. '
            f"Please do not reply.</p>"
        )

        data = {
            "body_html": body_html,
            "promotion_url": promo_url,
            "promotion_id": promo_id,
            "attachment_ids": [str(x.id) for x in user_atts],
        }

        email = (getattr(user, "email", None) or "").strip()
        try:
            if email:
                n = notif_svc.create(
                    user_id=uid,
                    type="external_promotion_created",
                    title=title,
                    body=body_plain,
                    data=data,
                    source_entity_type="promotion",
                    source_entity_id=notify_source_id,
                    event_type="external_attachment_uploader_notice",
                )
                if n:
                    notification_ids.append(str(n.id))
                    uploader_ids.add(uid)
            else:
                notif_svc.create_in_app_only(
                    user_id=uid,
                    type="external_promotion_created",
                    title=title,
                    body=body_plain,
                    source_entity_type="promotion",
                    source_entity_id=notify_source_id,
                    event_type="external_attachment_uploader_notice",
                )
                uploader_ids.add(uid)
        except Exception as e:
            logger.warning(
                "Failed to notify uploader %s for external promotion %s: %s",
                uid,
                promo_id,
                e,
                exc_info=True,
            )

    return notification_ids, uploader_ids


def notify_external_promotion_explicit_user(
    db: Session,
    promotion,
    user_id: str,
    *,
    notification_batch_id: str,
) -> list[str]:
    """
    Notify a CRM user by id that a promotion was created via the external API (no attachment uploader path).
    Used when the API key is 'system' (created_by is null) or when n8n passes notify_user_id.
    """
    if not getattr(settings, "notifications_v1_enabled", True):
        return []

    uid = (user_id or "").strip()
    if not uid:
        return []

    from app.models.user import User
    from app.services.notification_service import NotificationService

    user = db.query(User).filter(User.id == uid).first()
    if not user:
        logger.warning("external promotion notify_user_id: user not found: %s", uid)
        return []

    promo_id = str(getattr(promotion, "id", "") or "")
    promo_code = (getattr(promotion, "promo_code", None) or "").strip() or "—"
    promo_name = (getattr(promotion, "name", None) or "").strip() or promo_code
    promo_url = build_promotion_detail_url(promo_id)

    title = f"Promotion created: {promo_code}"
    body_plain = (
        f'A promotion "{promo_name}" ({promo_code}) was created in Sorento CRM via the external integration API '
        f"(for example n8n).\n\n"
        f"View promotion:\n{promo_url}\n\n"
        f"This is a system generated email. Please do not reply."
    )
    body_html = (
        f"<p>A promotion <strong>{html.escape(promo_name)}</strong> "
        f"(<strong>{html.escape(promo_code)}</strong>) was created in Sorento CRM via the external integration API "
        f"(for example n8n).</p>"
        f'<p><a href="{html.escape(promo_url, quote=True)}">Open promotion in Sorento CRM</a></p>'
        f'<p style="color:#666;font-size:12px;margin-top:1.5em;">This is a system generated email. '
        f"Please do not reply.</p>"
    )
    data = {"body_html": body_html, "promotion_url": promo_url, "promotion_id": promo_id}
    notify_source_id = f"{promo_id}_{notification_batch_id}"

    notif_svc = NotificationService(db)
    email = (getattr(user, "email", None) or "").strip()
    try:
        if email:
            n = notif_svc.create(
                user_id=uid,
                type="external_promotion_created",
                title=title,
                body=body_plain,
                data=data,
                source_entity_type="promotion",
                source_entity_id=notify_source_id,
                event_type="external_promotion_explicit_notify",
            )
            return [str(n.id)] if n else []
        notif_svc.create_in_app_only(
            user_id=uid,
            type="external_promotion_created",
            title=title,
            body=body_plain,
            source_entity_type="promotion",
            source_entity_id=notify_source_id,
            event_type="external_promotion_explicit_notify",
        )
        return []
    except Exception as e:
        logger.warning("Failed explicit external promotion notify for %s: %s", uid, e, exc_info=True)
        return []


def notify_after_external_promotion_created(
    db: Session,
    promotion,
    attachment_ids: list[str],
    notify_user_id: Optional[str],
) -> None:
    """
    After POST /external/promotions succeeds: notify attachment uploaders and/or notify_user_id, then send email immediately.

    External API auth uses the system key, so promotion.created_by is usually null — pass notify_user_id from n8n
    (CRM user UUID) when attachment_ids are missing or uploaded_by is not set on files.
    """
    if not getattr(settings, "notifications_v1_enabled", True):
        return

    batch_id = uuid.uuid4().hex[:16]
    ids: list[str] = []
    uploaders: set[str] = set()

    try:
        n_ids, up = notify_uploaders_after_external_promotion_created(
            db,
            attachment_ids,
            promotion,
            notification_batch_id=batch_id,
        )
        ids.extend(n_ids)
        uploaders.update(up)
    except Exception as e:
        logger.warning("External promotion uploader notification failed: %s", e, exc_info=True)

    nu = (notify_user_id or "").strip()
    if nu and nu not in uploaders:
        try:
            ids.extend(notify_external_promotion_explicit_user(db, promotion, nu, notification_batch_id=batch_id))
        except Exception as e:
            logger.warning("External promotion notify_user_id failed: %s", e, exc_info=True)

    if ids:
        flush_notification_email_deliveries(ids)


def _integration_context_line(entity_type: Optional[str]) -> str:
    """Short, professional line about what integration may do (varies by linked entity)."""
    et = (entity_type or "").strip().lower()
    if et == "promotion":
        return (
            "Depending on your automation, this file may be processed for promotion-related updates "
            "(for example via your external promotion API)."
        )
    if et in ("inbound_shipment", "packing_list"):
        return (
            "Depending on your automation, this file may be processed for packing list or "
            "inbound shipment workflows."
        )
    if et in ("workflow_form", "workflow_submission", "workflow"):
        return (
            "Depending on your automation, this file may be processed for workflow form "
            "or submission workflows."
        )
    if et == "product":
        return (
            "Depending on your automation, this file may be processed for product-related "
            "attachments."
        )
    return (
        "Your integration workflow will process this file according to your automation rules."
    )


def notify_uploader_after_attachment_webhook(
    db: Session,
    attachment,
    actor_user_id: str,
) -> None:
    """
    In-app notification + email to the uploader (uploaded_by, else actor) when the n8n webhook is queued.
    Email is only sent if the user has an email address; otherwise in-app only.
    """
    if not getattr(settings, "notifications_v1_enabled", True):
        return

    uid = (getattr(attachment, "uploaded_by", None) or actor_user_id or "").strip()
    if not uid:
        logger.debug("Skipping attachment webhook notification: no uploader user id")
        return

    from app.models.user import User
    from app.services.notification_service import NotificationService

    user = db.query(User).filter(User.id == uid).first()
    if not user:
        logger.debug("Skipping attachment webhook notification: user %s not found", uid)
        return

    filename = getattr(attachment, "original_filename", None) or "your file"
    safe_name = html.escape(filename)
    detail_url = build_attachment_detail_url(str(attachment.id))
    href_attr = html.escape(detail_url, quote=True)
    context_line = _integration_context_line(getattr(attachment, "entity_type", None))

    title = "Attachment sent for processing"
    body_plain = (
        f'Your file "{filename}" was uploaded successfully and has been sent for automated processing '
        f"via the integration workflow.\n\n"
        f"{context_line}\n\n"
        f"View attachment: {detail_url}\n\n"
        f"This is a system generated email. Please do not reply."
    )
    body_html = (
        f"<p>Your file <strong>{safe_name}</strong> was uploaded successfully and has been sent for "
        f"automated processing via the integration workflow.</p>"
        f"<p>{html.escape(context_line)}</p>"
        f'<p><a href="{href_attr}">Open attachment in Sorento CRM</a></p>'
        f'<p style="color:#666;font-size:12px;margin-top:1.5em;">This is a system generated email. '
        f"Please do not reply.</p>"
    )

    data = {
        "body_html": body_html,
        "attachment_url": detail_url,
        "attachment_id": str(attachment.id),
    }

    notif_svc = NotificationService(db)
    email = (getattr(user, "email", None) or "").strip()

    try:
        if email:
            notif_svc.create(
                user_id=uid,
                type="attachment_integration_webhook",
                title=title,
                body=body_plain,
                data=data,
                source_entity_type="attachment",
                source_entity_id=str(attachment.id),
                event_type="webhook_submitted",
            )
        else:
            notif_svc.create_in_app_only(
                user_id=uid,
                type="attachment_integration_webhook",
                title=title,
                body=body_plain,
                source_entity_type="attachment",
                source_entity_id=str(attachment.id),
                event_type="webhook_submitted",
            )
    except Exception as e:
        logger.warning("Failed to create attachment webhook notification for user %s: %s", uid, e, exc_info=True)
