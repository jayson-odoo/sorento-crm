"""Stock List attachment archive-and-replace (PLAN-autocount-pull-review.md, P7).

Moved out of the `POST .../attachments/replace-latest-stock-list` route body
(`app/api/v1/resources/attachments.py`) so the AutoCount pull's stock Confirm
(SR4, AC-SC-3/AC-SC-4) can call the SAME logic the manual n8n upload uses -
archive every live `Stock_List` attachment, upload the new one through the
storage router, same webhook. The route keeps its own macro-strip step
(`.xlsm` -> values-only `.xlsx`, `excel_macro_stripper.extract_macro_
template_xlsx`) and hands this function the ALREADY-clean bytes; every caller
here (the manual route post-strip, the apply task's generated workbook) is
handing over genuine `.xlsx` content, so the mime is fixed rather than
threaded through as a parameter - keeps the signature to exactly what both
callers naturally have: file bytes, a filename, the acting user.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_STOCK_LIST_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def replace_latest_stock_list(db: Session, *, file_bytes: bytes, filename: str, user_id: str):
    """Archives every live `Stock_List` attachment and uploads `file_bytes` as the new
    one. Returns the created `Attachment` ORM row - the caller (route or apply task)
    decides what to do with it (build an HTTP response, or nothing at all)."""
    from app.api.v1.resources.attachments import STOCK_LIST_TYPE_NAMES
    from app.models.resources import Attachment, AttachmentType
    from app.schemas.resources import AttachmentCreate
    from app.services.attachment_webhook_helper import create_and_send_webhook
    from app.services.contact_access_type_service import ContactAccessTypeService
    from app.services.resources_service import AttachmentService
    from app.services.storage_router import cdn_base_url, default_provider, get_backend

    attachment_type = (
        db.query(AttachmentType).filter(AttachmentType.type_name.in_(STOCK_LIST_TYPE_NAMES)).first()
    )
    if not attachment_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attachment type 'Stock List' not found. Create an attachment type with name 'Stock List' first.",
        )

    # Archive any existing non-archived attachment with this type (only 1 allowed).
    existing = (
        db.query(Attachment)
        .filter(
            Attachment.attachment_type_id == str(attachment_type.id),
            Attachment.is_deleted == False,  # noqa: E712
        )
        .all()
    )
    now = datetime.utcnow()
    for att in existing:
        att.is_deleted = True
        att.deleted_at = now
        att.deleted_by = user_id
    if existing:
        db.commit()

    file_size = len(file_bytes)
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    original_filename = filename or "stock_list.xlsx"
    safe_filename = (
        "".join(c for c in original_filename if c.isalnum() or c in (" ", "-", "_", ".")).strip()
        or "stock_list.xlsx"
    )
    entity_type = (attachment_type.type_name or "general").lower().replace(" ", "_")
    s3_file_path = f"{entity_type}/{safe_filename}"

    provider = default_provider()
    backend = get_backend(provider)
    try:
        s3_key, _ = backend.upload_file(
            file_content=file_bytes, file_path=s3_file_path, content_type=_STOCK_LIST_MIME,
        )
    except Exception as storage_error:
        logger.error(
            "Storage upload failed for replace_latest_stock_list (provider=%s): %s",
            provider, storage_error,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file to storage: {storage_error}",
        )
    stored_file_path = cdn_base_url(provider, s3_key)

    access_svc = ContactAccessTypeService(db)
    access_levels_payload = access_svc.get_default_access_levels()
    attachment_data = AttachmentCreate(
        attachment_type_id=str(attachment_type.id),
        original_filename=original_filename,
        stored_filename=safe_filename,
        file_path=stored_file_path,
        file_size_bytes=file_size,
        mime_type=_STOCK_LIST_MIME,
        file_hash=file_hash,
        entity_type=entity_type,
        entity_id=None,
        directory_id=None,
        description="Latest stock list",
        access_levels=access_levels_payload,
        storage_provider=provider,
    )
    attachment = AttachmentService(db).create_attachment(attachment_data, user_id)

    try:
        create_and_send_webhook(
            db, attachment, attachment_type, access_levels_payload, user_id,
            event_type="attachment_uploaded",
        )
    except Exception as webhook_error:
        logger.warning(
            "Webhook failed for replace_latest_stock_list attachment %s: %s",
            getattr(attachment, "id", None), webhook_error,
        )

    return attachment
