"""Supplier photos on a shipment line (R25, section 12, purchasing consolidation batch
6 Sep 2026, lane C, slice C3).

Reuses ``EntityAttachmentLink`` - the same generic, ordered attachment-linkage table
every other linked-attachment feature (complaint / stock-inquiry / purchase-request
manual attachments, the external entity-attachment route) already uses - rather than a
new ``inbound_shipment_line_photos`` join table the plan offered as the alternative.
``entity_type='inbound_shipment_line'``, ``entity_id`` the line's id. No migration:
``entity_attachment_links`` already carries ``sort_order``, a CASCADE FK onto
``attachments``, and the unique ``(entity_type, entity_id, attachment_id)`` the plan
asked for. See ``## Deviations (lane C)`` in the plan.

No cap per line (Q5, ruled 6 Sep 2026): a line can hold as many photos as it is given.

The attachment type (``Shipment Line Photo``) is admin data, never auto-created - same
convention ``packing_list_service._PACKING_LIST_TYPE_CODE`` reads by: the captain sets
the code (or just the name) after deploy, and a missing type is a 400 that says so
rather than a silent skip, because filing the photo IS the point of this endpoint (a
missing "Packing List" type there is a best-effort aside on an apply that succeeds
either way; there is no such fallback here).
"""
from __future__ import annotations

import logging
import uuid as uuid_module
from typing import Optional

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entity_attachment import EntityAttachmentLink
from app.models.procurement import InboundShipmentLine
from app.models.resources import Attachment, AttachmentType
from app.services.entity_attachment_service import EntityAttachmentService
from app.services.error_handler import AppException, handle_not_found
from app.services.image_thumbnailer import store_thumbnail
from app.services.storage_router import (
    cdn_base_url,
    default_provider,
    delete_object_best_effort,
    extract_key,
    get_backend,
    normalize_provider,
    resolve_signed_url,
    sanitize_storage_filename,
)

logger = logging.getLogger(__name__)

ENTITY_TYPE = "inbound_shipment_line"
TYPE_CODE = "shipment_line_photo"
TYPE_NAME = "Shipment Line Photo"


def _line_or_404(db: Session, shipment_id: str, line_id: str) -> InboundShipmentLine:
    line = (
        db.query(InboundShipmentLine)
        .filter(
            InboundShipmentLine.id == line_id,
            InboundShipmentLine.shipment_id == shipment_id,
        )
        .first()
    )
    if line is None:
        raise handle_not_found("Shipment line", line_id)
    return line


def _photo_type(db: Session) -> AttachmentType:
    """Same ``code = ... OR lower(type_name) = ...`` lookup lane A's
    ``packing_list_service`` uses (case-insensitive: R4/this type is admin-set, never
    guaranteed to carry a code). Raises rather than skips - see module docstring."""
    row = (
        db.query(AttachmentType)
        .filter(
            (AttachmentType.code == TYPE_CODE)
            | (func.lower(AttachmentType.type_name) == TYPE_NAME.lower())
        )
        .first()
    )
    if row is None:
        raise AppException(
            400,
            f"No attachment type named '{TYPE_NAME}' (or code '{TYPE_CODE}') is "
            "configured. Ask an admin to create one in Resource Management > "
            "Attachment Types before uploading shipment line photos.",
        )
    return row


def _serialize(link: EntityAttachmentLink) -> dict:
    att = link.attachment
    provider = normalize_provider(getattr(att, "storage_provider", None))
    # `strict=True`: a photo that cannot be signed must render as no photo, never as a
    # broken image the FE has no way to explain (see `storage_router.resolve_signed_url`
    # docstring - the same reasoning product images and the dealer kit already apply).
    thumb = resolve_signed_url(
        getattr(att, "thumbnail_path", None), provider=provider, strict=True
    )
    full = resolve_signed_url(getattr(att, "file_path", None), provider=provider, strict=True)
    return {
        "id": str(link.id),
        "attachment_id": str(link.attachment_id),
        "sort_order": link.sort_order,
        "thumbnail_url": thumb or full,
        "url": full,
        "filename": getattr(att, "original_filename", None),
    }


def list_for_shipment(db: Session, shipment_id: str) -> dict[str, list[dict]]:
    """Every line's photos on this shipment, keyed by line id - one read for the whole
    Lines tab rather than one per row."""
    line_ids = [
        str(row[0])
        for row in db.query(InboundShipmentLine.id)
        .filter(InboundShipmentLine.shipment_id == shipment_id)
        .all()
    ]
    if not line_ids:
        return {}
    by_line = EntityAttachmentService(db).list_links_for_entities(ENTITY_TYPE, line_ids)
    return {line_id: [_serialize(link) for link in links] for line_id, links in by_line.items()}


async def upload_photos(
    db: Session,
    *,
    shipment_id: str,
    line_id: str,
    files: list[UploadFile],
    actor_id: Optional[str],
) -> list[dict]:
    """Store each file as a Shipment Line Photo attachment and link it to the line, in
    upload order (``sort_order`` appends, via ``link_existing_attachment`` - R25).

    Never calls the n8n intake webhook: a line photo is not a document a downstream
    integration needs notified about, same convention
    ``packing_list_service.file_supplier_document`` follows for its own filed copy.
    """
    line = _line_or_404(db, shipment_id, line_id)
    attachment_type = _photo_type(db)
    entity_svc = EntityAttachmentService(db)

    provider = default_provider()
    backend = get_backend(provider)

    created: list[dict] = []
    for upload in files:
        content = await upload.read()
        original_filename = sanitize_storage_filename(upload.filename or "photo.jpg")
        ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
        entity_svc.check_quota(attachment_type, ENTITY_TYPE, str(line.id), len(content), ext)

        object_key = f"{TYPE_CODE}/{line.id}/{uuid_module.uuid4()}-{original_filename}"
        # Real network PUT via sync boto3 - must not run on the event loop directly, or
        # one slow upload freezes every other request this worker is holding (same
        # concern `resources/attachments.py`'s own upload route guards against).
        s3_key, _ = await run_in_threadpool(
            backend.upload_file,
            file_content=content,
            file_path=object_key,
            content_type=upload.content_type,
        )
        thumbnail_path = await run_in_threadpool(
            store_thumbnail, backend, provider, s3_key, content, upload.content_type
        )

        from app.schemas.resources import AttachmentCreate
        from app.services.resources_service import AttachmentService

        attachment_data = AttachmentCreate(
            attachment_type_id=str(attachment_type.id),
            original_filename=original_filename,
            stored_filename=original_filename,
            file_path=cdn_base_url(provider, s3_key),
            file_size_bytes=len(content),
            mime_type=upload.content_type,
            storage_provider=provider,
            thumbnail_path=thumbnail_path,
        )
        # Commits internally (`AttachmentService.create_attachment`) and stamps
        # `company_id` off the active company scope - the same call every other upload
        # path in this codebase makes, so a photo is scoped exactly like any other file.
        attachment = AttachmentService(db).create_attachment(attachment_data, actor_id)
        link = entity_svc.link_existing_attachment(
            entity_type=ENTITY_TYPE,
            entity_id=str(line.id),
            attachment_id=str(attachment.id),
            created_by=actor_id,
        )
        db.commit()
        db.refresh(link)
        created.append(_serialize(link))

    return created


def delete_photo(db: Session, photo_id: str) -> None:
    """Removes the link row AND the attachment row AND the stored bytes.

    DB rows commit first, the object purges after (same ordering
    ``dealer_kit.asset_service``'s own delete uses): an object outliving its row is an
    orphan and costs storage; a row outliving its object is a broken link nothing on
    screen can explain. Deleting the ``Attachment`` row cascades the link row too
    (``entity_attachment_links.attachment_id`` is ``ON DELETE CASCADE``), so only one
    delete is needed.
    """
    link = (
        db.query(EntityAttachmentLink)
        .filter(
            EntityAttachmentLink.id == photo_id,
            EntityAttachmentLink.entity_type == ENTITY_TYPE,
        )
        .first()
    )
    if link is None:
        raise handle_not_found("Photo", photo_id)

    attachment = db.query(Attachment).filter(Attachment.id == link.attachment_id).first()
    objects: list[tuple[str, str]] = []
    if attachment is not None:
        provider = normalize_provider(attachment.storage_provider)
        for path in (attachment.file_path, attachment.thumbnail_path):
            key = extract_key(path)
            if key:
                objects.append((provider, key))
        db.delete(attachment)
    else:
        db.delete(link)
    db.commit()

    for object_provider, key in objects:
        delete_object_best_effort(object_provider, key)
