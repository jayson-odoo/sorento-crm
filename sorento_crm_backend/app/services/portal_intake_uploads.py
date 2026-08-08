"""Keep what a consumer uploaded, whatever the extractor made of it.

The lodge journey opens by asking for a photo of the receipt and of the problem, and
until now those bytes were read into memory, posted to a model, and dropped on the floor.
Nothing persisted them. So a consumer who photographed a receipt got a complaint with no
receipt on it, and when extraction misread the date - which is the ordinary case, not the
edge case - CS had nothing to check it against.

The upload is evidence FIRST and extractor input second. Whether the model recognises a
receipt, a warranty card or a blurry thumb is a judgement about the file; it is never a
reason to keep or discard it. So this stores every accepted file before extraction runs,
and returns ids the caller can link to whatever record the journey eventually creates.

**Attachments are created unlinked.** There is no complaint to link to yet - the consumer
is on step one of five, and may never finish. An unlinked `attachments` row is the honest
representation of "uploaded, not yet part of anything". `lodge_complaint` links the ones
that make it to a submission; the rest stay unlinked and are a cleanup job's problem, not
a reason to lose the file of everyone who does finish.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.resources import Attachment
from app.services.entity_attachment_service import EntityAttachmentService

logger = logging.getLogger(__name__)

# Imported, never redeclared: a second copy of this string would drift from the one the
# portal's own upload endpoint uses, and these files would quietly land in a category of
# one that no quota, filter or directory view knows about.
from app.services.portal_service import PORTAL_ATTACHMENT_TYPE_CODE


@dataclass(frozen=True)
class StoredUpload:
    attachment_id: str
    filename: str
    size_bytes: int


def store_portal_upload(
    db: Session,
    *,
    contact_id: Optional[str],
    filename: Optional[str],
    content_type: Optional[str],
    data: bytes,
) -> Optional[StoredUpload]:
    """Persist one uploaded file and return its attachment id.

    Best-effort by design: returns None instead of raising. This runs on the path to
    extraction, and a storage outage must not stop a consumer reporting a broken toilet.
    Losing the copy is bad; refusing the complaint is worse, and the words they typed are
    the part CS actually acts on.
    """
    try:
        from app.services.storage_router import default_provider, get_backend

        provider = default_provider()
        backend = get_backend(provider)
        name = (filename or "upload").strip() or "upload"
        extension = os.path.splitext(name)[1][:10]
        key = f"portal/{contact_id or 'anonymous'}/{uuid.uuid4()}{extension}"
        backend.upload_file(data, key, content_type=content_type)

        # Grid thumbnail for images. Best-effort inside a best-effort: a missing
        # thumbnail costs a placeholder, a raised exception costs the file.
        thumbnail = None
        try:
            from app.services.image_thumbnailer import store_thumbnail

            thumbnail = store_thumbnail(backend, provider, key, data, content_type)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Portal intake thumbnail failed for %s: %s", name, exc)

        service = EntityAttachmentService(db)
        attachment = Attachment(
            attachment_type_id=service.get_attachment_type_by_code(
                PORTAL_ATTACHMENT_TYPE_CODE
            ).id,
            original_filename=name[:255],
            stored_filename=name[:255],
            file_path=key[:500],
            thumbnail_path=thumbnail,
            file_size_bytes=len(data),
            storage_provider=provider,
            mime_type=(content_type or None),
            uploader_kind="contact",
            uploaded_by_contact_id=contact_id,
        )
        db.add(attachment)
        db.flush()
        return StoredUpload(
            attachment_id=str(attachment.id),
            filename=name,
            size_bytes=len(data),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Portal intake upload could not be stored (%s): %s", filename, exc)
        db.rollback()
        return None


def link_uploads_to_entity(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    attachment_ids: list[str],
) -> list[str]:
    """Attach previously-stored uploads to the record the journey produced.

    Skips anything already linked or since deleted rather than failing the submission:
    the complaint is the thing that must not be lost, and a client that retries a submit
    would otherwise 409 on its own earlier success.
    """
    service = EntityAttachmentService(db)
    linked: list[str] = []
    for attachment_id in attachment_ids:
        candidate = (attachment_id or "").strip()
        if not candidate:
            continue
        try:
            service.link_existing_attachment(
                entity_type=entity_type,
                entity_id=entity_id,
                attachment_id=candidate,
                created_by=None,
            )
            linked.append(candidate)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not link portal upload %s to %s %s: %s",
                candidate,
                entity_type,
                entity_id,
                exc,
            )
    return linked
