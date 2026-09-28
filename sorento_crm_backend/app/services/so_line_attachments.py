"""Clarification files on a core sales-order line, sent with the OI handover email
(#1312, PLAN-oi-line-attachments-27sep.md).

Reuses ``EntityAttachmentLink`` exactly as ``app.services.scm.shipment_line_photos``
does for a shipment line - ``entity_type='sales_order_line'``, ``entity_id`` the CORE
``sales_order_lines.id`` (Q1: the AutoCount line, not the project mirror), so the
fulfilment board, the order inquiry Lines tab and the handover email all read the same
files off one id. No new table.

Unlike the shipment photo endpoint, this one accepts more than images (Q3: jpg, jpeg,
png, webp, gif, pdf, xlsx, xls) - a clarification is as often a spec sheet or a signed
PO page as a photo. The extension gate below is still HARDCODED independent of the
seeded attachment type's own ``allowed_extensions`` (same reasoning
``shipment_line_photos._validated_image_ext`` gives): an admin later widening the
type's own config must not turn this into an arbitrary-file upload.
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
from app.models.order import SalesOrderLine
from app.models.resources import Attachment, AttachmentType
from app.services.audit_service import log_audit
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

ENTITY_TYPE = "sales_order_line"
TYPE_CODE = "so_line_attachment"
TYPE_NAME = "Sales Order Line Attachment"

#: Q3 (grill, recommended answer): images, PDF, Excel - what #1311's manual mails
#: already carry. Independent of the seeded type's own ``allowed_extensions`` (module
#: docstring above).
_ALLOWED_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "pdf", "xlsx", "xls"}
_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
_MIME_BY_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
}

#: AC-A5: more than this many ids in one lookup answers 422 (route-level, `Field(...,
#: max_length=...)` on the request schema) rather than this module ever seeing them.
MAX_LOOKUP_IDS = 1000

#: security L1 (fix round 1): the amount actually read off the wire per file,
#: HARDCODED regardless of the attachment type row's own `max_file_size_mb` - an
#: admin widening that column (or a row missing/misconfigured) must not turn this
#: into an unbounded-memory upload. `upload()` reads with `.read(_MAX_BYTES + 1)`
#: rather than `.read()`, so a file over the cap is never fully buffered.
_MAX_BYTES = 10 * 1024 * 1024
#: security L1: files per request, also hardcoded rather than left open-ended.
_MAX_FILES_PER_REQUEST = 10


def _line_or_404(db: Session, line_id: str) -> SalesOrderLine:
    """Scoped by ``CompanyScopedMixin`` (the session's active company scope) - a line
    id outside the caller's company reads exactly like an unknown one (AC-A4)."""
    line = db.query(SalesOrderLine).filter(SalesOrderLine.id == line_id).first()
    if line is None:
        raise handle_not_found("Sales order line", line_id)
    return line


def _type_row(db: Session) -> AttachmentType:
    """Same ``code = ... OR lower(type_name) = ...`` lookup ``shipment_line_photos.
    _photo_type`` uses. Raises rather than skips: the migration seeds this row, so a
    missing one means the seed has not run yet, and the upload IS the point."""
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
            "Attachment Types before uploading line attachments.",
        )
    return row


def _validated_ext(filename: str) -> str:
    """The extension, only when it is one of the ones this endpoint ever accepts
    (Q3) - a 400 named after the actual file, independent of the attachment type
    row's own configurable ``allowed_extensions``."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTS:
        raise AppException(
            400,
            f"{filename} is not a supported file type "
            "(jpg, jpeg, png, webp, gif, pdf, xlsx or xls).",
        )
    return ext


def _serialize(link: EntityAttachmentLink) -> dict:
    att = link.attachment
    provider = normalize_provider(getattr(att, "storage_provider", None))
    # `strict=True`: a file that cannot be signed must render as no file, never as a
    # broken link the FE has no way to explain (same rule `shipment_line_photos`
    # applies to its own thumbnails).
    thumb = resolve_signed_url(
        getattr(att, "thumbnail_path", None), provider=provider, strict=True
    )
    full = resolve_signed_url(getattr(att, "file_path", None), provider=provider, strict=True)
    return {
        "id": str(link.id),
        "attachment_id": str(link.attachment_id),
        "filename": getattr(att, "original_filename", None),
        "size_bytes": getattr(att, "file_size_bytes", None),
        "content_type": getattr(att, "mime_type", None),
        "url": full,
        "thumbnail_url": thumb or full,
    }


def _line_attachments(db: Session, line_id: str) -> list[dict]:
    by_line = EntityAttachmentService(db).list_links_for_entities(ENTITY_TYPE, [line_id])
    return [_serialize(link) for link in by_line.get(line_id, [])]


def _err_message(exc: Exception) -> str:
    if isinstance(exc, AppException) and isinstance(exc.detail, dict):
        return exc.detail.get("message") or str(exc)
    return str(exc)


def lookup(db: Session, line_ids: list[str]) -> dict[str, list[dict]]:
    """Every listed line's files, keyed by line id - for exactly the lines that both
    hold files AND are visible in the caller's company scope (AC-A5). One read for a
    whole grid, never one per row.

    ``EntityAttachmentLink`` carries no company scope of its own (module docstring),
    so the ids are narrowed against ``SalesOrderLine`` - which IS scoped - before
    anything is looked up on it.
    """
    if not line_ids:
        return {}
    ids = [str(i) for i in line_ids]
    visible_ids = [
        str(row[0])
        for row in db.query(SalesOrderLine.id).filter(SalesOrderLine.id.in_(ids)).all()
    ]
    if not visible_ids:
        return {}
    by_line = EntityAttachmentService(db).list_links_for_entities(ENTITY_TYPE, visible_ids)
    return {line_id: [_serialize(link) for link in links] for line_id, links in by_line.items()}


async def upload(
    db: Session,
    *,
    line_id: str,
    files: list[UploadFile],
    actor_id: Optional[str],
) -> list[dict]:
    """Store each file and link it to the line, in upload order (AC-A1). Returns the
    line's FULL list afterwards, this upload included - never just the files this call
    added, so the caller never has to merge two lists itself.

    Each file is stored and linked inside its own try/except (mirrors
    ``shipment_line_photos.upload_photos``): a failure partway through a multi-file
    batch purges whatever THAT file already put in storage and re-raises naming it -
    the files before it stay linked, exactly as committed.
    """
    if len(files) > _MAX_FILES_PER_REQUEST:
        raise AppException(
            400, f"Upload up to {_MAX_FILES_PER_REQUEST} files at a time."
        )

    line = _line_or_404(db, line_id)
    attachment_type = _type_row(db)
    entity_svc = EntityAttachmentService(db)

    provider = default_provider()
    backend = get_backend(provider)

    landed: list[str] = []
    for upload_file in files:
        # security nit: the extension is checked off the FILENAME alone, before a
        # single byte of the body is read - a disallowed file costs nothing here.
        original_filename = sanitize_storage_filename(upload_file.filename or "file")
        ext = _validated_ext(original_filename)
        # security M1: the client's own `Content-Type` header is NEVER trusted - a
        # browser (or a hand-crafted request) can claim anything regardless of the
        # actual bytes, so what gets stored and thumbnailed is always derived from
        # the (already-validated) extension instead.
        content_type = _MIME_BY_EXT[ext]

        # security L1: bounded read - `.read(_MAX_BYTES + 1)` never buffers more
        # than one byte past the cap, so an oversized file is rejected before it
        # costs real memory, and the 10 MB ceiling holds regardless of what the
        # attachment type row's own (admin-editable) `max_file_size_mb` says.
        content = await upload_file.read(_MAX_BYTES + 1)
        if len(content) > _MAX_BYTES:
            raise AppException(
                400,
                f"{original_filename} exceeds the {_MAX_BYTES // (1024 * 1024)} MB limit.",
            )

        s3_key: Optional[str] = None
        thumbnail_path: Optional[str] = None
        try:
            entity_svc.check_quota(attachment_type, ENTITY_TYPE, str(line.id), len(content), ext)

            object_key = f"{TYPE_CODE}/{line.id}/{uuid_module.uuid4()}-{original_filename}"
            s3_key, _ = await run_in_threadpool(
                backend.upload_file,
                file_content=content,
                file_path=object_key,
                content_type=content_type,
            )
            if ext in _IMAGE_EXTS:
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
                directory_id=attachment_type.default_directory_id,
            )
            # Commits internally and stamps `company_id` off the active company scope -
            # the same call every other upload path in this codebase makes.
            attachment = AttachmentService(db).create_attachment(attachment_data, actor_id)
            entity_svc.link_existing_attachment(
                entity_type=ENTITY_TYPE,
                entity_id=str(line.id),
                attachment_id=str(attachment.id),
                created_by=actor_id,
            )
            # AC-A7: one audit row per file, on the LINE (not the attachment - that
            # already carries its own declarative INSERT audit).
            log_audit(
                db,
                "sales_order_line",
                str(line.id),
                "UPDATE",
                new_values={"attachment_added": original_filename},
                user_id=actor_id,
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            # The object (and its thumbnail) may already be sitting in storage before
            # whatever failed - purged here so an object never outlives the row that
            # would have pointed at it.
            if s3_key:
                delete_object_best_effort(provider, s3_key)
            if thumbnail_path:
                thumb_key = extract_key(thumbnail_path)
                if thumb_key:
                    delete_object_best_effort(provider, thumb_key)
            message = _err_message(exc)
            prefix = f"Uploaded {', '.join(landed)}. " if landed else ""
            message = f"{prefix}{original_filename}: {message}"
            status_code = exc.status_code if isinstance(exc, AppException) else 400
            raise AppException(status_code, message) from exc

        landed.append(original_filename)

    return _line_attachments(db, str(line.id))


def delete(db: Session, line_id: str, link_id: str, actor_id: Optional[str]) -> None:
    """Removes the link, the attachment row and the stored bytes.

    Scoped to ``line_id`` (mirrors ``shipment_line_photos.delete_photo``'s own review
    finding): a link id under another line answers 404 rather than being trusted, and
    nothing is deleted on that path (AC-A6).
    """
    line = _line_or_404(db, line_id)

    link = (
        db.query(EntityAttachmentLink)
        .filter(
            EntityAttachmentLink.id == link_id,
            EntityAttachmentLink.entity_type == ENTITY_TYPE,
        )
        .first()
    )
    if link is None or link.entity_id != str(line.id):
        raise handle_not_found("Attachment", link_id)

    attachment = db.query(Attachment).filter(Attachment.id == link.attachment_id).first()
    filename = getattr(attachment, "original_filename", None)
    # AC-A7: the removal's own audit row, before the delete - `old_values` states what
    # is about to be gone.
    log_audit(
        db,
        "sales_order_line",
        str(line.id),
        "UPDATE",
        old_values={"attachment_removed": filename},
        user_id=actor_id,
    )

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


def handover_attachments(db: Session, core_line_ids: list[str]) -> dict[str, list[dict]]:
    """``{core_line_id: [{filename, size_bytes, storage_provider, storage_key}]}``, in
    link (upload) order - what ``_fire_pending_handover`` folds into the handover
    dispatch context (AC-E1). A file whose storage key cannot be resolved is skipped
    rather than raised: a missing/broken file must never block the email itself.

    Runs on the drain's own FRESH session, over ids `_record_handover` already
    resolved and trusts (not user input), so no company-scope narrowing is applied
    here (unlike `lookup` above) - but a scope must still be SET, or reads UNSET
    (fail-closed). `fresh = SessionLocal()` (`_fire_pending_handover`) never sets
    one, and `Attachment` is company-scoped (`__company_shared__`, so UNSET reads
    only its NULL-company rows) - a real upload is stamped with the uploader's own
    company, so without this every real attachment was invisible here (fix round 1
    blocker 1: the handover never actually attached anything in production). `None`
    means "every company", the same fallback `AutomationService._stamp_expiry_batch`
    uses for its own drain-time re-query.
    """
    if not core_line_ids:
        return {}
    ids = sorted({str(i) for i in core_line_ids if i})
    if not ids:
        return {}
    from app.models.base import company_scope

    with company_scope(db, None):
        by_line = EntityAttachmentService(db).list_links_for_entities(ENTITY_TYPE, ids)
        if not by_line:
            return {}
        attachment_ids = [link.attachment_id for links in by_line.values() for link in links]
        attachments = {
            str(a.id): a
            for a in db.query(Attachment).filter(Attachment.id.in_(attachment_ids)).all()
        }
    out: dict[str, list[dict]] = {}
    for line_id, links in by_line.items():
        items: list[dict] = []
        for link in links:
            att = attachments.get(str(link.attachment_id))
            if att is None:
                continue
            key = extract_key(getattr(att, "file_path", None))
            if not key:
                continue
            items.append(
                {
                    "filename": att.original_filename,
                    "size_bytes": att.file_size_bytes or 0,
                    "storage_provider": normalize_provider(att.storage_provider),
                    "storage_key": key,
                }
            )
        if items:
            out[line_id] = items
    return out
