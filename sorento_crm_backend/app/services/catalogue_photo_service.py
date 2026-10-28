"""Catalogue photo readings: upload, read on the worker, review, attach (CATALOG-IMAGES).

Plan: ``documentation/plans/products/PLAN-catalog-image-extract-27oct.md`` "Build".

Nothing here writes to a product until ``attach``. The upload stores the PDF in its own folder
and queues the read; the worker stores every photo as an ordinary file in that folder (type
"Product Photos" when it exists, and no n8n upload webhook, so n8n's intake never sees them);
review edits rows of ``catalogue_photos``; attach writes ordinary ``product_attachments`` links.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.catalogue_photos import CataloguePhoto, CataloguePhotoReading
from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment, AttachmentDirectory, AttachmentType
from app.services.dealer_kit import flyer_reading_service as flyer_svc
from app.services.dealer_kit.catalog_photo_matching import already_on_file, match_codes
from app.services.dealer_kit.catalog_photos import (
    CATALOGUE_MAX_PAGES,
    dhash,
    extract_catalog_photos,
    hamming,
)
from app.services.attachment_bulk_download_service import suffix_copy_name
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

LOOKALIKE_MAX_DISTANCE = 10
CATALOGUE_MAX_PHOTOS = 2000
MAX_ALSO_ATTACH = 50
MAX_CODE_LENGTH = 120
JOB_TYPE = "catalogue_photo_read"
FAILED_MESSAGE = "The catalogue could not be read. Check the PDF and upload it again."
QUEUE_FAILED_MESSAGE = "The catalogue could not be queued. Try uploading it again."

ROOT_FOLDER = "Catalogue photos"
PHOTO_TYPE_NAME = "Product Photos"
QUEUE = "flyer_read"
JOB_TIMEOUT = flyer_svc.FLYER_READ_JOB_TIMEOUT

TABS = ("ready", "duplicate", "needs_product", "skipped")
DECISIONS = ("attach", "skip", "keep_both", "replace")


class CatalogueReadError(Exception):
    """A failure whose message is safe to show the user (it never carries system detail)."""
_RANK = {"high": 3, "medium": 2, "low": 1, "none": 0}


# --------------------------------------------------------------------------- #
# Upload (in the request)
# --------------------------------------------------------------------------- #
def _not_a_pdf(reason: str) -> AppException:
    return AppException(
        status_code=400,
        message=f"That file could not be read as a PDF ({reason}). Upload the catalogue as a PDF.",
        code="CATALOGUE_NOT_A_PDF",
    )


def check_upload(data: bytes, content_type: Optional[str]) -> None:
    """The refusals that need no extraction: size, declared type, not a PDF, locked."""
    import fitz

    flyer_svc.assert_within_limit(len(data))
    flyer_svc.assert_pdf_mime(content_type)
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise _not_a_pdf("it is not a PDF") from exc
    try:
        if document.needs_pass:
            raise AppException(
                status_code=400,
                message="That PDF is password protected. Remove the password and upload it again.",
                code="CATALOGUE_ENCRYPTED",
            )
        if document.page_count == 0:
            raise _not_a_pdf("it has no pages")
        if document.page_count > CATALOGUE_MAX_PAGES:
            raise AppException(
                status_code=400,
                message=f"That catalogue has more than {CATALOGUE_MAX_PAGES} pages.",
                code="CATALOGUE_TOO_MANY_PAGES",
            )
    finally:
        document.close()


def _folder_name(file_name: str) -> str:
    stem = file_name.rsplit(".", 1)[0] if file_name.lower().endswith(".pdf") else file_name
    stem = stem.replace("/", "-").replace("-->", "-").strip() or "catalogue"
    return stem[:200]


def _root_folder(db: Session, company_id: Optional[str]) -> AttachmentDirectory:
    root = (
        db.query(AttachmentDirectory)
        .filter(
            AttachmentDirectory.name == ROOT_FOLDER,
            AttachmentDirectory.parent_id.is_(None),
            AttachmentDirectory.is_deleted.is_(False),
            AttachmentDirectory.company_id == company_id,
        )
        .first()
    )
    if root is None:
        root = AttachmentDirectory(id=str(uuid.uuid4()), name=ROOT_FOLDER, company_id=company_id)
        db.add(root)
        db.flush()
    return root


def _make_folder(
    db: Session, root: AttachmentDirectory, file_name: str, company_id: Optional[str]
) -> AttachmentDirectory:
    name = _folder_name(file_name)
    taken = {
        row[0]
        for row in db.query(AttachmentDirectory.name).filter(
            AttachmentDirectory.parent_id == root.id, AttachmentDirectory.is_deleted.is_(False)
        )
    }
    # The drive's own collision naming ("x" -> "x - copy" -> "x - copy (2)").
    while name in taken:
        name = suffix_copy_name(name)
    folder = AttachmentDirectory(
        id=str(uuid.uuid4()), parent_id=root.id, name=name, company_id=company_id
    )
    db.add(folder)
    db.flush()
    return folder


def _store_file(
    db: Session,
    *,
    display_name: str,
    content: bytes,
    mime: str,
    directory: AttachmentDirectory,
    folder_path: str,
    attachment_type: Optional[AttachmentType],
    user_id: Optional[str],
    sha256: Optional[str],
    thumbnail: bool,
    company_id: Optional[str],
    bare_key: bool = False,
    uploaded: Optional[list] = None,
) -> Attachment:
    """One file into storage and a row in the folder. Never fires the n8n upload webhook."""
    from app.services import storage_router
    from app.services.image_thumbnailer import store_thumbnail

    attachment_id = str(uuid.uuid4())
    safe_name = storage_router.sanitize_storage_filename(display_name)
    if len(safe_name) > 200:  # the column holds 255 and the storage key adds a prefix
        stem, dot, ext = safe_name.rpartition(".")
        safe_name = (stem[: 200 - len(ext) - 1] + dot + ext) if dot and len(ext) <= 10 else safe_name[:200]
    entity = attachment_type.type_name.lower().replace(" ", "_") if attachment_type else "general"
    provider = storage_router.default_provider()
    backend = storage_router.get_backend(provider)
    key, _url = backend.upload_file(
        file_content=content, file_path=f"{entity}/{attachment_id}/{safe_name}", content_type=mime
    )
    if uploaded is not None:
        uploaded.append((provider, key))
    thumb_path = store_thumbnail(backend, provider, key, content, mime) if thumbnail else None
    if thumb_path and uploaded is not None:
        from app.services.image_thumbnailer import thumbnail_key_for

        uploaded.append((provider, thumbnail_key_for(key)))
    row = Attachment(
        id=attachment_id,
        attachment_type_id=attachment_type.id if attachment_type else None,
        original_filename=safe_name,
        stored_filename=display_name[:255],
        # The PDF is only ever read back by key; every reader goes through extract_key.
        file_path=key if bare_key else storage_router.cdn_base_url(provider, key),
        thumbnail_path=thumb_path,
        file_size_bytes=len(content),
        mime_type=mime,
        file_hash=sha256,
        uploaded_by=user_id,
        uploader_kind="user",
        directory_id=directory.id,
        full_directory_path=folder_path,
        storage_provider=provider,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def _free_pdf_name(db: Session, root: AttachmentDirectory, file_name: str) -> str:
    """The PDF's name in the root folder, bumped the drive's way while another file holds it.

    The drive keeps one active file name per folder (a unique index on the lower-cased stored
    name), so a catalogue uploaded twice would otherwise be refused with a 500.
    """
    from app.services import storage_router

    taken = {
        (row[0] or "").lower()
        for row in db.query(Attachment.original_filename).filter(
            Attachment.directory_id == root.id, Attachment.is_deleted.is_(False)
        )
    }
    name = file_name
    while storage_router.sanitize_storage_filename(name).lower() in taken:
        name = suffix_copy_name(name)
    return name


def create_from_upload(
    db: Session, *, file_name: str, data: bytes, user_id: Optional[str]
) -> CataloguePhotoReading:
    from app.services.company_scope import get_company_scope, resolve_write_company_id
    from app.services.job_service import JobService

    company_id = resolve_write_company_id(get_company_scope(db))
    root = _root_folder(db, company_id)
    folder = _make_folder(db, root, file_name, company_id)
    file_name = _free_pdf_name(db, root, file_name)
    # The source PDF sits in the root folder, so a ZIP of the catalogue folder holds photos only.
    pdf = _store_file(
        db,
        display_name=file_name,
        content=data,
        mime="application/pdf",
        directory=root,
        folder_path=ROOT_FOLDER,
        attachment_type=None,
        user_id=user_id,
        sha256=None,
        thumbnail=False,
        company_id=company_id,
        bare_key=True,
    )
    reading = CataloguePhotoReading(
        id=str(uuid.uuid4()),
        company_id=company_id,
        file_name=file_name[:255],
        file_size=len(data),
        status="queued",
        pdf_attachment_id=pdf.id,
        directory_id=folder.id,
        created_by=user_id,
    )
    db.add(reading)
    # The upload-activity drawer lists this job, one entry per catalogue.
    job = JobService(db).create_job(
        job_type=JOB_TYPE,
        user_id=user_id,
        filename=file_name[:255],
        metadata={"reading_id": reading.id},
        company_id=company_id,
    )
    reading.job_id = str(job.job_id)
    db.commit()
    db.refresh(reading)
    enqueue(db, reading)
    return reading


def _finish_job(
    db: Session,
    reading: CataloguePhotoReading,
    *,
    error: Optional[str] = None,
    result: Optional[dict] = None,
) -> None:
    """Best effort: the drawer entry follows the reading; a failure here never changes the reading."""
    if not reading.job_id:
        return
    from app.services.job_service import JobService

    try:
        service = JobService(db)
        if error is None:
            count = reading.photo_count or 0
            service.complete_job(
                reading.job_id,
                result=result,
                successful_rows=count,
                processed_rows=count,
                total_rows=count,
            )
        else:
            service.fail_job(reading.job_id, error)
    except Exception:  # noqa: BLE001
        logger.exception("Catalogue job %s could not be updated", reading.job_id)


def enqueue(db: Session, reading: CataloguePhotoReading) -> None:
    """Looked up at call time, so a test (or Redis being down) reaches the real seam."""
    from app.services import queue_service
    from app.tasks.catalogue_photo_tasks import process_catalogue_photo_reading

    try:
        job = queue_service.enqueue_job(
            process_catalogue_photo_reading,
            str(reading.id),
            queue_name=QUEUE,
            job_timeout=JOB_TIMEOUT,
            job_id=reading.job_id,
        )
    except Exception:  # noqa: BLE001 - the queue's problem; the detail goes to the log only
        logger.exception("Catalogue reading %s could not be queued", reading.id)
        reading.status = "failed"
        reading.error = QUEUE_FAILED_MESSAGE
        db.commit()
        _finish_job(db, reading, error=QUEUE_FAILED_MESSAGE)
        return
    db.commit()


# --------------------------------------------------------------------------- #
# The read (on the worker)
# --------------------------------------------------------------------------- #
def _bytes_of(attachment: Optional[Attachment]) -> Optional[bytes]:
    if attachment is None:
        return None
    from app.services import storage_router

    try:
        return storage_router.get_backend(attachment.storage_provider).download_file(
            storage_router.extract_key(attachment.file_path) or ""
        )
    except Exception:  # noqa: BLE001
        return None


def _image_hash_of(attachment: Attachment) -> Optional[str]:
    """dHash of an image already on file: its thumbnail when it has one, else the file itself."""
    from app.services import storage_router

    if not (attachment.mime_type or "").lower().startswith("image/"):
        return None
    provider = attachment.storage_provider
    for path in (attachment.thumbnail_path, attachment.file_path):
        key = storage_router.extract_key(path)
        if not key:
            continue
        try:
            return dhash(storage_router.get_backend(provider).download_file(key))
        except Exception:  # noqa: BLE001 - try the next source
            continue
    return None


def _lookalike(
    db: Session,
    product_id: str,
    photo_hash: str,
    cache: Optional[dict] = None,
    stats: Optional[dict] = None,
) -> Optional[tuple[str, int]]:
    """The closest image already linked to the product, within the threshold.

    ``cache`` maps attachment id to its dHash for the length of one run, so a file shared by
    many photos' products is downloaded once.
    """
    cache = cache if cache is not None else {}
    rows = (
        db.query(Attachment)
        .join(ProductAttachment, ProductAttachment.attachment_id == Attachment.id)
        .filter(ProductAttachment.product_id == product_id, Attachment.is_deleted.is_(False))
        .all()
    )
    best: Optional[tuple[str, int]] = None
    for attachment in rows:
        key = str(attachment.id)
        if key not in cache:
            cache[key] = _image_hash_of(attachment)
            if stats is not None and (attachment.mime_type or "").lower().startswith("image/"):
                stats["lookalike_compared" if cache[key] else "lookalike_unreadable"] += 1
        existing = cache[key]
        if existing is None:
            continue
        distance = hamming(photo_hash, existing)
        if distance <= LOOKALIKE_MAX_DISTANCE and (best is None or distance < best[1]):
            best = (key, distance)
    return best


def _photo_name(code: Optional[str], page: int, index_on_page: int, ext: str, used: dict[str, int]) -> str:
    if not code:
        return f"p{page:02d}-photo-{index_on_page:02d}.{ext}"
    used[code] = used.get(code, 0) + 1
    suffix = "" if used[code] == 1 else f" ({used[code]})"
    return f"{code}{suffix}.{ext}"


def process_reading(db: Session, reading: CataloguePhotoReading) -> dict:
    """Cut every kept photo out of the stored PDF, store it, propose a product.

    Raises on failure. Files already uploaded are deleted (best effort) before it does, and the
    caller rolls the rows back, so a failed read leaves nothing behind.
    """
    import fitz

    from app.services import storage_router

    if not reading.company_id:
        raise CatalogueReadError(FAILED_MESSAGE)
    pdf = (
        db.query(Attachment).filter(Attachment.id == reading.pdf_attachment_id).first()
        if reading.pdf_attachment_id
        else None
    )
    data = _bytes_of(pdf)
    if data is None:
        raise CatalogueReadError("The stored catalogue could not be fetched from storage.")
    document = fitz.open(stream=data, filetype="pdf")
    try:
        pages = document.page_count
    finally:
        document.close()
    if pages > CATALOGUE_MAX_PAGES:
        raise CatalogueReadError(f"That catalogue has more than {CATALOGUE_MAX_PAGES} pages.")
    try:
        photos = extract_catalog_photos(data, limit=CATALOGUE_MAX_PHOTOS)
    except ValueError as exc:  # the extractor's refusals carry fixed, plain messages
        raise CatalogueReadError(str(exc)) from exc
    if len(photos) > CATALOGUE_MAX_PHOTOS:
        raise CatalogueReadError(f"That catalogue holds more than {CATALOGUE_MAX_PHOTOS} photos.")

    folder = db.query(AttachmentDirectory).filter(AttachmentDirectory.id == reading.directory_id).first()
    if folder is None:
        raise CatalogueReadError(FAILED_MESSAGE)
    folder_path = f"{ROOT_FOLDER} --> {folder.name}"
    photo_type = db.query(AttachmentType).filter(AttachmentType.type_name == PHOTO_TYPE_NAME).first()

    codes = list(
        dict.fromkeys(code[:MAX_CODE_LENGTH] for photo in photos for code in photo.block_codes)
    )
    matches = match_codes(db, codes) if codes else {}

    uploaded: list = []
    hashes: dict = {}
    stats = {"lookalike_compared": 0, "lookalike_unreadable": 0, "lookalike_flagged": 0}
    used: dict[str, int] = {}
    per_page: dict[int, int] = {}
    try:
        for position, photo in enumerate(photos, start=1):
            block_codes = [code[:MAX_CODE_LENGTH] for code in photo.block_codes]
            primary_code = block_codes[0] if block_codes else None
            per_page[photo.page] = per_page.get(photo.page, 0) + 1
            ext = "png" if photo.mime == "image/png" else "jpg"
            name = _photo_name(primary_code, photo.page, per_page[photo.page], ext, used)
            attachment = _store_file(
                db,
                display_name=name,
                content=photo.image_bytes,
                mime=photo.mime,
                directory=folder,
                folder_path=folder_path,
                attachment_type=photo_type,
                user_id=reading.created_by,
                sha256=photo.sha256,
                thumbnail=True,
                company_id=reading.company_id,
                uploaded=uploaded,
            )
            photo_hash = dhash(photo.image_bytes)
            primary = matches.get(primary_code) if primary_code else None
            product_id = primary.product_id if primary else None
            others: list[dict] = []
            for code in block_codes[1:]:
                other = matches.get(code)
                if other and other.product_id and other.product_id != product_id:
                    entry = {"id": other.product_id, "product_code": other.product_code}
                    if entry not in others:
                        others.append(entry)
            duplicate = (
                _lookalike(db, product_id, photo_hash, hashes, stats) if product_id else None
            )
            if duplicate:
                stats["lookalike_flagged"] += 1
            db.add(
                CataloguePhoto(
                    id=str(uuid.uuid4()),
                    reading_id=reading.id,
                    page=photo.page,
                    position=position,
                    attachment_id=attachment.id,
                    sha256=photo.sha256,
                    dhash=photo_hash,
                    printed_code=primary_code,
                    block_codes=block_codes,
                    placeholders=list(photo.placeholders),
                    product_id=product_id,
                    rung=primary.rung if primary else None,
                    confidence=primary.confidence if primary else "none",
                    suggestion=primary.suggestion if primary else None,
                    other_block_products=others,
                    also_attach_product_ids=[],
                    duplicate_of_attachment_id=duplicate[0] if duplicate else None,
                    duplicate_distance=duplicate[1] if duplicate else None,
                    decision="skip" if duplicate else "attach",
                )
            )
        reading.page_count = pages
        reading.photo_count = len(photos)
        reading.status = "ready"
        reading.error = None
        db.commit()
    except BaseException:
        for provider, key in uploaded:
            storage_router.delete_object_best_effort(provider, key)
        raise
    return stats


# --------------------------------------------------------------------------- #
# Review
# --------------------------------------------------------------------------- #
def get_reading(db: Session, reading_id: str) -> CataloguePhotoReading:
    try:
        uuid.UUID(str(reading_id))
    except ValueError:
        raise AppException(status_code=404, message="Catalogue reading not found")
    reading = db.query(CataloguePhotoReading).filter(CataloguePhotoReading.id == reading_id).first()
    if reading is None:
        raise AppException(status_code=404, message="Catalogue reading not found")
    return reading


def _base(db: Session, reading_id: str):
    return db.query(CataloguePhoto).filter(CataloguePhoto.reading_id == reading_id)


def _tab_filter(query, tab: str):
    P = CataloguePhoto
    if tab == "duplicate":
        return query.filter(P.duplicate_of_attachment_id.isnot(None))
    query = query.filter(P.duplicate_of_attachment_id.is_(None))
    if tab == "ready":
        return query.filter(P.product_id.isnot(None), P.decision == "attach")
    if tab == "needs_product":
        return query.filter(P.product_id.is_(None), P.decision != "skip")
    if tab == "skipped":
        return query.filter(P.decision == "skip")
    raise AppException(status_code=422, message=f"Unknown tab {tab}")


def _to_attach(query):
    P = CataloguePhoto
    return query.filter(
        P.product_id.isnot(None), P.decision.in_(("attach", "keep_both", "replace")), P.attached_at.is_(None)
    )


def detail(db: Session, reading: CataloguePhotoReading) -> dict:
    from app.models.user import User

    base = _base(db, reading.id)
    counts = {tab: _tab_filter(base, tab).count() for tab in TABS}
    counts["to_attach"] = _to_attach(base).count()
    author = db.query(User.name).filter(User.id == reading.created_by).scalar() if reading.created_by else None
    return {
        "id": str(reading.id),
        "file_name": reading.file_name,
        "status": reading.status,
        "page_count": reading.page_count,
        "photo_count": reading.photo_count,
        "error": reading.error,
        "directory_id": str(reading.directory_id) if reading.directory_id else None,
        "created_at": reading.created_at.isoformat() if reading.created_at else None,
        "created_by_name": author,
        "counts": counts,
        "attached_count": base.filter(CataloguePhoto.attached_at.isnot(None)).count(),
    }


def _url(attachment: Optional[Attachment], *, thumb: bool) -> Optional[str]:
    if attachment is None:
        return None
    from app.services import storage_router

    path = (attachment.thumbnail_path if thumb else None) or attachment.file_path
    # Signed or nothing: an unsigned CDN path would be a broken image, or a leaked address.
    return storage_router.resolve_signed_url(path, provider=attachment.storage_provider, strict=True)


def _item(row: CataloguePhoto, products: dict, attachments: dict) -> dict:
    product = products.get(str(row.product_id)) if row.product_id else None
    duplicate = None
    if row.duplicate_of_attachment_id:
        dup = attachments.get(str(row.duplicate_of_attachment_id))
        duplicate = {
            "attachment_id": str(row.duplicate_of_attachment_id),
            "thumbnail_url": _url(dup, thumb=True),
            "distance": row.duplicate_distance,
        }
    own = attachments.get(str(row.attachment_id)) if row.attachment_id else None
    return {
        "id": str(row.id),
        "page": row.page,
        "position": row.position,
        "thumbnail_url": _url(own, thumb=True),
        "image_url": _url(own, thumb=False),
        "printed_code": row.printed_code,
        "block_codes": list(row.block_codes or []),
        "placeholders": list(row.placeholders or []),
        "product": {"id": str(product.id), "product_code": product.product_code} if product else None,
        "rung": row.rung,
        "confidence": row.confidence,
        "suggestion": row.suggestion,
        "other_block_products": list(row.other_block_products or []),
        "also_attach_product_ids": list(row.also_attach_product_ids or []),
        "duplicate": duplicate,
        "decision": row.decision,
        "attached_at": row.attached_at.isoformat() if row.attached_at else None,
    }


def _items(db: Session, rows: list[CataloguePhoto]) -> list[dict]:
    product_ids = {str(r.product_id) for r in rows if r.product_id}
    attachment_ids = {str(r.attachment_id) for r in rows if r.attachment_id} | {
        str(r.duplicate_of_attachment_id) for r in rows if r.duplicate_of_attachment_id
    }
    products = (
        {str(p.id): p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}
        if product_ids
        else {}
    )
    attachments = (
        {str(a.id): a for a in db.query(Attachment).filter(Attachment.id.in_(attachment_ids)).all()}
        if attachment_ids
        else {}
    )
    return [_item(r, products, attachments) for r in rows]


def list_photos(
    db: Session,
    reading: CataloguePhotoReading,
    *,
    tab: str,
    page: int,
    limit: int,
    sort: Optional[str],
    direction: str,
) -> dict:
    P = CataloguePhoto
    query = _tab_filter(_base(db, reading.id), tab)
    total = query.count()
    desc = direction == "desc"
    flip = (lambda c: c.desc()) if desc else (lambda c: c.asc())
    order_page = [flip(P.page), flip(P.position)]
    if sort == "printed_code":
        order = [flip(P.printed_code).nulls_last(), *order_page]
    elif sort == "product_code":
        code = (
            db.query(Product.product_code).filter(Product.id == P.product_id).correlate(P).scalar_subquery()
        )
        order = [flip(code).nulls_last(), *order_page]
    elif sort == "confidence":
        rank = case(
            (P.confidence == "high", 3), (P.confidence == "medium", 2), (P.confidence == "low", 1), else_=0
        )
        order = [flip(rank), *order_page]
    elif sort in (None, "", "page"):
        order = order_page
    else:
        raise AppException(status_code=422, message=f"Cannot sort by {sort}")
    rows = query.order_by(*order).offset((page - 1) * limit).limit(limit).all()
    return {
        "data": _items(db, rows),
        "empty": total == 0,
        "pagination": {"total": total, "page": page},
    }


def _photo(db: Session, reading: CataloguePhotoReading, photo_id: str) -> CataloguePhoto:
    try:
        uuid.UUID(str(photo_id))
    except ValueError:
        raise AppException(status_code=404, message="Photo not found")
    row = _base(db, reading.id).filter(CataloguePhoto.id == photo_id).first()
    if row is None:
        raise AppException(status_code=404, message="Photo not found")
    return row


def _product_in_scope(db: Session, product_id: str) -> Product:
    try:
        uuid.UUID(str(product_id))
    except ValueError:
        raise AppException(status_code=404, message="Product not found")
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise AppException(status_code=404, message="Product not found")
    return product


def patch_photo(db: Session, reading: CataloguePhotoReading, photo_id: str, changes: dict) -> dict:
    row = _photo(db, reading, photo_id)
    if row.attached_at is not None:
        raise AppException(status_code=409, message="That photo is already attached", code="PHOTO_ATTACHED")

    if "product_id" in changes:
        pid = changes["product_id"]
        if pid:
            product = _product_in_scope(db, pid)
            row.product_id = product.id
            row.rung = "manual"
            row.confidence = "high"
        else:
            row.product_id = None
            row.rung = "none"
            row.confidence = "none"
        row.also_attach_product_ids = []
        # The look-alike belongs to the product the row proposes: recompute it for the new one.
        duplicate = None
        if row.product_id and row.dhash:
            try:
                duplicate = _lookalike(db, str(row.product_id), row.dhash)
            except Exception:  # noqa: BLE001 - a failed check clears the flag rather than blocking the pick
                logger.exception("Look-alike check failed for photo %s", row.id)
        row.duplicate_of_attachment_id = duplicate[0] if duplicate else None
        row.duplicate_distance = duplicate[1] if duplicate else None
        row.decision = "skip" if duplicate else "attach"
    if "also_attach_product_ids" in changes:
        ids = list(dict.fromkeys(str(i) for i in (changes["also_attach_product_ids"] or [])))
        if len(ids) > MAX_ALSO_ATTACH:
            raise AppException(status_code=422, message=f"Choose at most {MAX_ALSO_ATTACH} products.")
        for pid in ids:
            _product_in_scope(db, pid)
        row.also_attach_product_ids = ids
    if "decision" in changes and changes["decision"] is not None:
        decision = changes["decision"]
        if decision not in DECISIONS:
            raise AppException(status_code=422, message=f"Unknown decision {decision}")
        if decision in ("keep_both", "replace") and row.duplicate_of_attachment_id is None:
            raise AppException(
                status_code=422,
                message="Keep both and Replace need a photo that looks like an existing one.",
                code="NO_LOOKALIKE",
            )
        row.decision = decision
    db.commit()
    db.refresh(row)
    return _items(db, [row])[0]


# --------------------------------------------------------------------------- #
# Attach
# --------------------------------------------------------------------------- #
def _pin_lone_photo(db: Session, product_id: str) -> None:
    """A product whose single photo shows automatically keeps showing it once a second arrives."""
    from app.services import brochure_image_service, product_image_service

    found = product_image_service.for_product(db, product_id)
    if found.candidate_count == 1 and found.state == product_image_service.CHOSEN:
        only = found.candidates[0]
        if not only.is_primary:
            brochure_image_service.set_brochure_image(db, product_id, only.attachment_id)


def attach(db: Session, reading: CataloguePhotoReading, user_id: Optional[str]) -> dict:
    from app.schemas.product import ProductAttachmentCreate
    from app.services import brochure_image_service
    from app.services.contact_access_type_service import ContactAccessTypeService
    from app.services.product_service import ProductAttachmentService

    links = ProductAttachmentService(db)
    levels = ContactAccessTypeService(db).get_default_access_levels()
    rows = (
        _to_attach(_base(db, reading.id))
        .order_by(CataloguePhoto.page, CataloguePhoto.position)
        .all()
    )
    attached = replaced = skipped = 0
    touched: set[str] = set()
    now = datetime.now(timezone.utc)

    for row in rows:
        targets = [str(row.product_id)] + [
            str(i) for i in (row.also_attach_product_ids or []) if str(i) != str(row.product_id)
        ]
        for index, product_id in enumerate(targets):
            if already_on_file(db, product_id, row.sha256 or ""):
                skipped += 1
                continue
            removed_link = None
            if index == 0 and row.decision == "replace" and row.duplicate_of_attachment_id:
                removed_link = (
                    db.query(ProductAttachment)
                    .filter(
                        ProductAttachment.product_id == product_id,
                        ProductAttachment.attachment_id == row.duplicate_of_attachment_id,
                    )
                    .first()
                )
            was_primary = bool(removed_link and removed_link.is_primary)
            if removed_link is not None:
                links.delete_product_attachment(str(removed_link.id))
            _pin_lone_photo(db, product_id)
            links.create_product_attachment(
                ProductAttachmentCreate(
                    product_id=product_id,
                    attachment_id=str(row.attachment_id),
                    is_primary=False,
                    access_levels=levels,
                ),
                created_by=user_id,
            )
            if was_primary:
                # The replaced photo was the product's chosen one: the new photo takes over.
                brochure_image_service.set_brochure_image(db, product_id, str(row.attachment_id))
            # A replaced photo is counted as replaced, not twice.
            if removed_link is not None:
                replaced += 1
            else:
                attached += 1
            touched.add(product_id)
        row.attached_at = now
        db.commit()
    return {"attached": attached, "replaced": replaced, "skipped": skipped, "products": len(touched)}
