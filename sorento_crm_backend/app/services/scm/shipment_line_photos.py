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

The attachment type (``Shipment Line Photo``) IS seeded by migration
``485_shipment_line_photo_type`` (review round 1, item 3): unlike
``packing_list_service``'s own best-effort "Packing List" type, this endpoint has no
fallback - filing the photo IS the point of it - so a fresh deploy with nobody having
created the row yet would otherwise 400 on the very first upload. The lookup still
tolerates an admin later renaming or re-coding the row (the ``code = ... OR
lower(type_name) = ...`` match below), it just no longer depends on someone doing that
FIRST.
"""
from __future__ import annotations

import logging
import mimetypes
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

#: What this endpoint ever accepts, independent of the attachment type row's own
#: ``allowed_extensions`` (review round 1, item 2): the type is admin-editable, and
#: an admin widening it later (e.g. to file a PDF spec sheet under the same type)
#: must not turn a "photo" upload into an arbitrary-file one.
_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
_IMAGE_MIME_BY_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}


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


def _validated_image_ext(filename: str) -> str:
    """The extension, only when it is one of the images this endpoint ever accepts
    (review round 1, item 2). A 400 named after the actual file, not a generic
    "unsupported type" - this is the one gate that must hold regardless of what the
    attachment type row's own ``allowed_extensions`` happens to say."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _IMAGE_EXTS:
        raise AppException(
            400, f"{filename} is not an image (jpg, jpeg, png, webp or gif)."
        )
    return ext


def _content_type_for(filename: str, ext: str, content_type: Optional[str]) -> str:
    """The browser's own ``content_type``, else derived from the extension (review
    round 1, item 2) - a bare multipart part with no ``Content-Type`` header must
    still store and thumbnail as the image it is, not as
    ``application/octet-stream``."""
    if content_type:
        return content_type
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or _IMAGE_MIME_BY_EXT.get(ext, "application/octet-stream")


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


def _line_photos(db: Session, line_id: str) -> list[dict]:
    by_line = EntityAttachmentService(db).list_links_for_entities(ENTITY_TYPE, [line_id])
    return [_serialize(link) for link in by_line.get(line_id, [])]


def _err_message(exc: Exception) -> str:
    if isinstance(exc, AppException) and isinstance(exc.detail, dict):
        return exc.detail.get("message") or str(exc)
    return str(exc)


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
    Returns the line's FULL photo list afterwards (review round 1, item 10) - not just
    the files this call added - so the caller never has to merge two lists itself.

    Never calls the n8n intake webhook: a line photo is not a document a downstream
    integration needs notified about, same convention
    ``packing_list_service.file_supplier_document`` follows for its own filed copy.

    Each file is stored and linked inside its own try/except (review round 1, item 4):
    a failure partway through a multi-file batch purges whatever THAT file already put
    in storage (object + thumbnail, both best-effort) and re-raises naming which files
    landed before it - the ones before it stay linked, exactly as committed.
    """
    line = _line_or_404(db, shipment_id, line_id)
    attachment_type = _photo_type(db)
    entity_svc = EntityAttachmentService(db)

    provider = default_provider()
    backend = get_backend(provider)

    landed: list[str] = []
    for upload in files:
        content = await upload.read()
        original_filename = sanitize_storage_filename(upload.filename or "photo.jpg")
        ext = _validated_image_ext(original_filename)
        content_type = _content_type_for(original_filename, ext, upload.content_type)

        s3_key: Optional[str] = None
        thumbnail_path: Optional[str] = None
        try:
            entity_svc.check_quota(attachment_type, ENTITY_TYPE, str(line.id), len(content), ext)

            object_key = f"{TYPE_CODE}/{line.id}/{uuid_module.uuid4()}-{original_filename}"
            # Real network PUT via sync boto3 - must not run on the event loop directly,
            # or one slow upload freezes every other request this worker is holding
            # (same concern `resources/attachments.py`'s own upload route guards
            # against).
            s3_key, _ = await run_in_threadpool(
                backend.upload_file,
                file_content=content,
                file_path=object_key,
                content_type=content_type,
            )
            thumbnail_path = await run_in_threadpool(
                store_thumbnail, backend, provider, s3_key, content, content_type
            )

            from app.schemas.resources import AttachmentCreate
            from app.services.resources_service import AttachmentService

            attachment_data = AttachmentCreate(
                attachment_type_id=str(attachment_type.id),
                original_filename=original_filename,
                stored_filename=original_filename,
                file_path=cdn_base_url(provider, s3_key),
                file_size_bytes=len(content),
                mime_type=content_type,
                storage_provider=provider,
                thumbnail_path=thumbnail_path,
                # The type's own default folder (review round 1, item 6) - same
                # convention `packing_list_service._file_the_upload` reads
                # `default_directory_id` by; NULL files nowhere in particular, same
                # as today.
                directory_id=attachment_type.default_directory_id,
            )
            # Commits internally (`AttachmentService.create_attachment`) and stamps
            # `company_id` off the active company scope - the same call every other
            # upload path in this codebase makes, so a photo is scoped exactly like
            # any other file.
            attachment = AttachmentService(db).create_attachment(attachment_data, actor_id)
            entity_svc.link_existing_attachment(
                entity_type=ENTITY_TYPE,
                entity_id=str(line.id),
                attachment_id=str(attachment.id),
                created_by=actor_id,
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            # The object (and its thumbnail) may already be sitting in storage before
            # whatever failed - an object outliving its row is an orphan nothing on
            # screen ever points at, so it is purged here rather than left billing
            # forever.
            if s3_key:
                delete_object_best_effort(provider, s3_key)
            if thumbnail_path:
                thumb_key = extract_key(thumbnail_path)
                if thumb_key:
                    delete_object_best_effort(provider, thumb_key)
            message = _err_message(exc)
            if landed:
                message = f"Uploaded {', '.join(landed)}. {original_filename} failed: {message}"
            status_code = exc.status_code if isinstance(exc, AppException) else 400
            raise AppException(status_code, message) from exc

        landed.append(original_filename)

    return _line_photos(db, str(line.id))


def purge_for_lines(db: Session, line_ids: list[str]) -> list[tuple[str, str]]:
    """Deletes every photo link + attachment row for the given line ids and returns the
    storage ``(provider, key)`` pairs still to purge (browser-test round, finding 1).

    Called when a shipment LINE ITSELF is about to be deleted (a re-uploaded packing list
    drops a product that used to be on the container) - without this the line's photo
    links become orphans nothing on screen ever points at again
    (``entity_attachment_links`` carries no real FK onto ``inbound_shipment_lines``, so
    the row would just sit there naming an id nothing resolves).

    Flushes only, never commits: the caller (`procurement_service._upsert_shipment_lines`)
    is mid its own unit of work, the same convention that unit of work already follows
    for the proforma-invoice links a departing line carries. The best-effort storage
    purge is the CALLER's job, run after ITS OWN commit - same ordering `delete_photo`
    uses (DB rows first, bytes after), so a purge that fails never leaves a broken link
    behind.
    """
    if not line_ids:
        return []
    ids = [str(i) for i in line_ids]
    links = (
        db.query(EntityAttachmentLink)
        .filter(
            EntityAttachmentLink.entity_type == ENTITY_TYPE,
            EntityAttachmentLink.entity_id.in_(ids),
        )
        .all()
    )
    if not links:
        return []
    attachments = {
        str(a.id): a
        for a in db.query(Attachment)
        .filter(Attachment.id.in_([link.attachment_id for link in links]))
        .all()
    }
    objects: list[tuple[str, str]] = []
    for link in links:
        attachment = attachments.get(str(link.attachment_id))
        if attachment is not None:
            provider = normalize_provider(attachment.storage_provider)
            for path in (attachment.file_path, attachment.thumbnail_path):
                key = extract_key(path)
                if key:
                    objects.append((provider, key))
            db.delete(attachment)
        else:
            db.delete(link)
    db.flush()
    return objects


def delete_photo(db: Session, shipment_id: str, line_id: str, photo_id: str) -> None:
    """Removes the link row AND the attachment row AND the stored bytes.

    Scoped to ``shipment_id``/``line_id`` (review round 1, item 1):
    ``EntityAttachmentLink`` carries no company scope of its own, so matching on
    ``photo_id`` alone would let a caller who merely GUESSES another shipment's photo
    id delete it. ``_line_or_404`` 404s a shipment/line mismatch before the link is
    even looked up, and the link's own ``entity_id`` is asserted against THIS line -
    a link somehow pointing elsewhere 404s the same way rather than being trusted.

    DB rows commit first, the object purges after (same ordering
    ``dealer_kit.asset_service``'s own delete uses): an object outliving its row is an
    orphan and costs storage; a row outliving its object is a broken link nothing on
    screen can explain. Deleting the ``Attachment`` row cascades the link row too
    (``entity_attachment_links.attachment_id`` is ``ON DELETE CASCADE``), so only one
    delete is needed.
    """
    line = _line_or_404(db, shipment_id, line_id)

    link = (
        db.query(EntityAttachmentLink)
        .filter(
            EntityAttachmentLink.id == photo_id,
            EntityAttachmentLink.entity_type == ENTITY_TYPE,
        )
        .first()
    )
    if link is None or link.entity_id != str(line.id):
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
