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
from datetime import datetime
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.catalogue_photos import CataloguePhoto, CataloguePhotoReading
from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment, AttachmentDirectory, AttachmentType
from app.services.dealer_kit import flyer_reading_service as flyer_svc
from app.services.dealer_kit.catalog_photo_matching import already_on_file, match_codes
from app.services.dealer_kit.catalog_photos import dhash, extract_catalog_photos, hamming
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

LOOKALIKE_MAX_DISTANCE = 10
ROOT_FOLDER = "Catalogue photos"
PHOTO_TYPE_NAME = "Product Photos"
QUEUE = "flyer_read"
JOB_TIMEOUT = flyer_svc.FLYER_READ_JOB_TIMEOUT

TABS = ("ready", "duplicate", "needs_product", "skipped")
DECISIONS = ("attach", "skip", "keep_both", "replace")
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
    finally:
        document.close()


def _folder_name(file_name: str) -> str:
    stem = file_name.rsplit(".", 1)[0] if file_name.lower().endswith(".pdf") else file_name
    stem = stem.replace("/", "-").strip() or "catalogue"
    return stem[:200]


def _make_folder(db: Session, file_name: str) -> AttachmentDirectory:
    root = (
        db.query(AttachmentDirectory)
        .filter(
            AttachmentDirectory.name == ROOT_FOLDER,
            AttachmentDirectory.parent_id.is_(None),
            AttachmentDirectory.is_deleted.is_(False),
        )
        .first()
    )
    if root is None:
        root = AttachmentDirectory(id=str(uuid.uuid4()), name=ROOT_FOLDER)
        db.add(root)
        db.flush()
    base = _folder_name(file_name)
    name, n = base, 1
    taken = {
        row[0]
        for row in db.query(AttachmentDirectory.name).filter(
            AttachmentDirectory.parent_id == root.id, AttachmentDirectory.is_deleted.is_(False)
        )
    }
    while name in taken:
        n += 1
        name = f"{base} ({n})"
    folder = AttachmentDirectory(id=str(uuid.uuid4()), parent_id=root.id, name=name)
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
    bare_key: bool = False,
) -> Attachment:
    """One file into storage and a row in the folder. Never fires the n8n upload webhook."""
    from app.services import storage_router
    from app.services.image_thumbnailer import store_thumbnail

    attachment_id = str(uuid.uuid4())
    safe_name = storage_router.sanitize_storage_filename(display_name)
    entity = attachment_type.type_name.lower().replace(" ", "_") if attachment_type else "general"
    provider = storage_router.default_provider()
    backend = storage_router.get_backend(provider)
    key, _url = backend.upload_file(
        file_content=content, file_path=f"{entity}/{attachment_id}/{safe_name}", content_type=mime
    )
    thumb_path = store_thumbnail(backend, provider, key, content, mime) if thumbnail else None
    row = Attachment(
        id=attachment_id,
        attachment_type_id=attachment_type.id if attachment_type else None,
        original_filename=safe_name,
        stored_filename=display_name,
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
    )
    db.add(row)
    db.flush()
    return row


def create_from_upload(
    db: Session, *, file_name: str, data: bytes, user_id: Optional[str]
) -> CataloguePhotoReading:
    folder = _make_folder(db, file_name)
    pdf = _store_file(
        db,
        display_name=file_name,
        content=data,
        mime="application/pdf",
        directory=folder,
        folder_path=f"{ROOT_FOLDER} --> {folder.name}",
        attachment_type=None,
        user_id=user_id,
        sha256=None,
        thumbnail=False,
        bare_key=True,
    )
    reading = CataloguePhotoReading(
        id=str(uuid.uuid4()),
        file_name=file_name[:255],
        file_size=len(data),
        status="queued",
        pdf_attachment_id=pdf.id,
        directory_id=folder.id,
        created_by=user_id,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    enqueue(db, reading)
    return reading


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
        )
    except Exception as exc:  # noqa: BLE001 - the queue's problem, said on the row
        logger.exception("Catalogue reading %s could not be queued", reading.id)
        reading.status = "failed"
        reading.error = f"Could not queue the catalogue read: {exc}"
        db.commit()
        return
    reading.job_id = getattr(job, "id", None)
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


def _lookalike(db: Session, product_id: str, photo_hash: str) -> Optional[tuple[str, int]]:
    rows = (
        db.query(Attachment)
        .join(ProductAttachment, ProductAttachment.attachment_id == Attachment.id)
        .filter(ProductAttachment.product_id == product_id, Attachment.is_deleted.is_(False))
        .all()
    )
    best: Optional[tuple[str, int]] = None
    for attachment in rows:
        existing = _image_hash_of(attachment)
        if existing is None:
            continue
        distance = hamming(photo_hash, existing)
        if distance <= LOOKALIKE_MAX_DISTANCE and (best is None or distance < best[1]):
            best = (str(attachment.id), distance)
    return best


def _photo_name(code: Optional[str], page: int, index_on_page: int, ext: str, used: dict[str, int]) -> str:
    if not code:
        return f"p{page:02d}-photo-{index_on_page:02d}.{ext}"
    used[code] = used.get(code, 0) + 1
    suffix = "" if used[code] == 1 else f" ({used[code]})"
    return f"{code}{suffix}.{ext}"


def process_reading(db: Session, reading: CataloguePhotoReading) -> None:
    """Cut every kept photo out of the stored PDF, store it, propose a product. Raises on failure."""
    import fitz

    pdf = (
        db.query(Attachment).filter(Attachment.id == reading.pdf_attachment_id).first()
        if reading.pdf_attachment_id
        else None
    )
    data = _bytes_of(pdf)
    if data is None:
        raise AppException(
            status_code=422,
            message="The stored catalogue could not be fetched from storage.",
            code="CATALOGUE_SOURCE_UNREADABLE",
        )
    photos = extract_catalog_photos(data)
    document = fitz.open(stream=data, filetype="pdf")
    try:
        pages = document.page_count
    finally:
        document.close()

    folder = db.query(AttachmentDirectory).filter(AttachmentDirectory.id == reading.directory_id).first()
    if folder is None:
        raise AppException(status_code=422, message="The catalogue folder is gone.", code="CATALOGUE_NO_FOLDER")
    folder_path = f"{ROOT_FOLDER} --> {folder.name}"
    photo_type = db.query(AttachmentType).filter(AttachmentType.type_name == PHOTO_TYPE_NAME).first()

    codes = list(dict.fromkeys(code for photo in photos for code in photo.block_codes))
    matches = match_codes(db, codes) if codes else {}

    used: dict[str, int] = {}
    per_page: dict[int, int] = {}
    for position, photo in enumerate(photos, start=1):
        per_page[photo.page] = per_page.get(photo.page, 0) + 1
        ext = "png" if photo.mime == "image/png" else "jpg"
        name = _photo_name(photo.primary_code, photo.page, per_page[photo.page], ext, used)
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
        )
        primary = matches.get(photo.primary_code) if photo.primary_code else None
        product_id = primary.product_id if primary else None
        others: list[dict] = []
        for code in photo.block_codes[1:]:
            other = matches.get(code)
            if other and other.product_id and other.product_id != product_id:
                entry = {"id": other.product_id, "product_code": other.product_code}
                if entry not in others:
                    others.append(entry)
        duplicate = None
        if product_id:
            duplicate = _lookalike(db, product_id, dhash(photo.image_bytes))
        db.add(
            CataloguePhoto(
                id=str(uuid.uuid4()),
                reading_id=reading.id,
                page=photo.page,
                position=position,
                attachment_id=attachment.id,
                sha256=photo.sha256,
                dhash=dhash(photo.image_bytes),
                printed_code=photo.primary_code,
                block_codes=list(photo.block_codes),
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
    return (
        storage_router.resolve_signed_url(path, provider=attachment.storage_provider, strict=True)
        or path
    )


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
    if "also_attach_product_ids" in changes:
        ids = list(dict.fromkeys(str(i) for i in (changes["also_attach_product_ids"] or [])))
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
    now = datetime.utcnow()

    for row in rows:
        targets = [str(row.product_id)] + [
            str(i) for i in (row.also_attach_product_ids or []) if str(i) != str(row.product_id)
        ]
        for index, product_id in enumerate(targets):
            if already_on_file(db, product_id, row.sha256 or ""):
                skipped += 1
                continue
            is_replace = index == 0 and row.decision == "replace" and bool(row.duplicate_of_attachment_id)
            if is_replace:
                db.query(ProductAttachment).filter(
                    ProductAttachment.product_id == product_id,
                    ProductAttachment.attachment_id == row.duplicate_of_attachment_id,
                ).delete(synchronize_session=False)
                db.flush()
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
            # A replaced photo is counted as replaced, not twice.
            if is_replace:
                replaced += 1
            else:
                attached += 1
            touched.add(product_id)
        row.attached_at = now
        db.commit()
    return {"attached": attached, "replaced": replaced, "skipped": skipped, "products": len(touched)}
