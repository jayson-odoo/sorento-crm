"""Shared helper for creating and sending attachment webhooks (used by upload API and bulk-import task)."""
import os
import json
import logging
import threading
from typing import Optional
from urllib.parse import urlparse, unquote
from sqlalchemy.orm import Session

from app.services.integration_service import IntegrationLogService
from app.schemas.integration import IntegrationLogCreate

logger = logging.getLogger(__name__)


def _build_signed_attachment_url(file_path: Optional[str]) -> Optional[str]:
    """Build a short-lived signed URL for webhook consumers."""
    if not file_path:
        return file_path
    try:
        from app.services.s3_service import S3Service

        s3 = S3Service()
        if file_path.startswith(("https://", "http://")):
            parsed = urlparse(file_path)
            # Always re-sign from the object path so expired Policy/Signature query strings are replaced
            key = unquote((parsed.path or "").lstrip("/"))
            return s3.get_signed_url(key) if key else file_path
        return s3.get_signed_url(unquote(file_path))
    except Exception as e:
        logger.warning("Could not generate signed attachment URL for webhook: %s", e)
        return file_path


def build_signed_attachment_url_for_webhook(file_path: Optional[str]) -> Optional[str]:
    """Public alias: always generate a fresh CloudFront signed URL from stored base URL or S3 key."""
    return _build_signed_attachment_url(file_path)


def create_and_send_webhook(
    db: Session,
    attachment,
    attachment_type,
    access_levels_payload: Optional[list],
    current_user_id: str,
) -> None:
    """Create integration log for attachment and send webhook in background (same behaviour as single upload)."""
    n8n_webhook_url = os.getenv("N8N_WEBHOOK_URL", "").strip()
    if not n8n_webhook_url:
        return
    if not n8n_webhook_url.startswith(("http://", "https://")):
        if n8n_webhook_url.startswith("//"):
            n8n_webhook_url = "https:" + n8n_webhook_url
        else:
            n8n_webhook_url = "https://" + n8n_webhook_url
    integration_service = IntegrationLogService(db)
    integration_log_data = IntegrationLogCreate(
        integration_channel="n8n",
        business_table="attachments",
        business_id=attachment.id,
        direction="outbound",
        endpoint=n8n_webhook_url,
        http_method="POST",
        created_by=current_user_id,
        status="pending",
    )
    integration_log = integration_service.create_integration_log(integration_log_data)
    signed_attachment_url = _build_signed_attachment_url(getattr(attachment, "file_path", None))
    webhook_payload = {
        "integration_log_id": integration_log.id,
        "attachment_url": signed_attachment_url,
        "s3_url": signed_attachment_url,
        "file_path": attachment.file_path,
        "attachment_id": attachment.id,
        "attachment_filename": attachment.original_filename,
        "attachment_mime_type": attachment.mime_type,
        "file_size": getattr(attachment, "file_size_bytes", None),
        "attachment_type": attachment_type.type_name if attachment_type else None,
        "access_levels": access_levels_payload,
    }
    integration_log.request_payload = json.dumps(webhook_payload)
    db.commit()
    db.refresh(integration_log)

    def send_webhook_async():
        try:
            from app.database import SessionLocal
            bg_db = SessionLocal()
            try:
                bg_service = IntegrationLogService(bg_db)
                bg_service.send_webhook_for_log(integration_log.id)
            finally:
                bg_db.close()
        except Exception as e:
            logger.error("Background webhook send failed for log %s: %s", integration_log.id, e, exc_info=True)

    threading.Thread(target=send_webhook_async, daemon=True).start()
    logger.info("Created integration log %s for attachment %s", integration_log.id, attachment.id)
