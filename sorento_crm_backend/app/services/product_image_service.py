"""Which photograph of a product the system shows. One decision, read by everybody.

`product_attachments.is_primary` is that decision. It is **product master data, not a feature of
whoever happens to be rendering it**: the Dealer Kit brochure is one consumer, 3D-model generation
is another, and the project quotation is the third. Each reads this module rather than asking the
question a second time, because two answers to "which picture is this product" is the same as no
answer - the tile, the mesh and the customer's quotation would silently disagree.

**Among several photographs nothing is chosen automatically.** Ordering by `sort_order` and
taking the first row looks like a reasonable default and is not: for `SRTWC286-SH` the
first-linked row is one of 31 files including a blank page and two other products' photographs. A
wrong photo is a wrong product in front of a customer, and the same wrong photo fed to a mesh
generator is that plus a bill. So a product with several photographs and nobody's answer reports
`NOT_CHOSEN` and shows nothing, which is a state a screen can act on; a guess is not.

**One photograph and nobody's answer IS the answer** (QUOTATION-UX, owner 14 Oct, AC-QLG06): in
dev 2,060 of 2,308 products with photographs carry exactly one, so "not chosen" there was a click
that could only ever pick that one. `is_primary` still wins whenever it is set.

Four things are excluded from being a photograph at all, in every query here, and they have to
stay in step or a screen will count a product as done and then fail to show its picture:

- a non-image mime type (the live data holds 532 PDFs linked to products - a spec sheet rendered
  as the product photo is worse than no photo),
- a deleted attachment (611 live links point at one; Resource Management already hides them, so
  signing a URL for one puts a broken picture on a customer's document),
- a technical drawing (an image typed "Technical Specifications"): it is the TECHNICAL SPEC
  column's picture, never the product's photograph. A typeless image still counts as a photo,
- for a *chosen* image, all of the above - a choice made before the file was deleted must stop
  being an answer, not linger as a broken one.

`render` exists because the artifacts embed bytes rather than link to them. The mean chosen image
in live data is 1.1 MB and the largest 4.3 MB, while the column it lands in is 60 CSS px wide, so
everything is downscaled into a bounded box first. Fifty-two originals inlined is a PDF nobody can
email.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment, AttachmentType
from app.services.storage_router import (
    extract_key,
    get_backend,
    normalize_provider,
    resolve_signed_url,
)

logger = logging.getLogger(__name__)

#: Somebody has said which picture is the product.
CHOSEN = "chosen"
#: There are photographs, but nobody has said which one. The overwhelming majority today: 30 of
#: the 535 products with candidates carry a choice.
NOT_CHOSEN = "not_chosen"
#: No photograph exists to choose between. The fix is a photo shoot, not a click, and a screen
#: that says "choose one" here is sending somebody to an empty room.
NO_PHOTOS = "no_photos"
#: There is no product at all, so there is nothing a flag could point at.
OFF_CATALOG = "off_catalog"

#: Longest edge, in pixels, of anything embedded in a document. The PDF's image column is 60 CSS
#: px wide, so 240 px still prints at ~380 dpi; the Excel picture is anchored at 110 px.
PRINT_BOX = 240
#: Re-encode quality. Product photographs are flat studio shots and hold up well here.
JPEG_QUALITY = 72
#: Shared with every other copy of a stored image (IMAGE-UNIFY): one decode policy.
from app.services.image_thumbnailer import (  # noqa: E402 - re-exported for existing callers
    EMBEDDABLE_FORMATS,
    MAX_IMAGE_PIXELS,  # noqa: F401 - re-exported
    RenderedImage,
    downscale,
    rendition_urls,
)


#: The attachment type of a technical drawing. Matched on the name, as the Dealer Kit image
#: ranking does (`dealer_kit/product_images.py`).
DRAWING_TYPE = "Technical Specifications"


@dataclass(frozen=True)
class ProductFile:
    """One image on file for a product: a photograph or a technical drawing."""

    attachment: Attachment
    is_primary: bool
    is_drawing: bool

    @property
    def attachment_id(self) -> str:
        return str(self.attachment.id)

    @property
    def filename(self) -> Optional[str]:
        return self.attachment.original_filename or self.attachment.stored_filename


@dataclass(frozen=True)
class ProductImage:
    """What a caller needs to draw a product's picture cell, including when there is none."""

    product_id: Optional[str]
    state: str
    attachment_id: Optional[str] = None
    filename: Optional[str] = None
    #: Photographs somebody could choose between. Zero means the answer is an upload rather than
    #: a click, and the two need different words on screen.
    candidate_count: int = 0
    #: Those photographs, oldest upload first, for a picker.
    candidates: Tuple[ProductFile, ...] = ()




OFF_CATALOG_IMAGE = ProductImage(product_id=None, state=OFF_CATALOG)


# ----------------------------------------------------------------------- reading


def _on_file(query):
    """The two conditions that make an attachment an image on file, applied in one place.

    Every query in this module goes through here, photographs and drawings alike. Two of them
    drifting apart is how a screen ends up counting a product as answered and then rendering
    nothing for it.
    """
    return query.filter(
        Attachment.mime_type.ilike("image/%"),
        Attachment.is_deleted.is_(False),
    )


def files_for(db: Session, product_ids: Sequence[Optional[str]]) -> Dict[str, List[ProductFile]]:
    """Every image on file per product, photographs and drawings, in ONE query.

    Oldest upload first, then id, so "the first drawing" and the order a picker shows are the
    same answer on every read.
    """
    unique = list(dict.fromkeys(str(pid) for pid in product_ids if pid))
    if not unique:
        return {}
    rows = (
        _on_file(
            db.query(
                ProductAttachment.product_id,
                ProductAttachment.is_primary,
                Attachment,
                AttachmentType.type_name,
            )
            .join(Attachment, Attachment.id == ProductAttachment.attachment_id)
            .outerjoin(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
        )
        .filter(ProductAttachment.product_id.in_(unique))
        .order_by(Attachment.created_at.asc(), Attachment.id.asc())
        .all()
    )
    found: Dict[str, List[ProductFile]] = {}
    for product_id, is_primary, attachment, type_name in rows:
        found.setdefault(str(product_id), []).append(
            ProductFile(
                attachment=attachment,
                is_primary=bool(is_primary),
                is_drawing=type_name == DRAWING_TYPE,
            )
        )
    return found


def is_product_file(
    db: Session,
    *,
    product_id: str,
    attachment_id: str,
    drawing: bool,
    company_id: Optional[str],
) -> bool:
    """Whether this attachment is one of the product's images of that kind, for a line pick.

    Linked through `product_attachments`, an image on file (``_on_file``), this company's or
    shared, and a drawing exactly when ``drawing`` - the same kinds ``files_for`` hands a picker.
    """
    kind = func.coalesce(AttachmentType.type_name, "") == DRAWING_TYPE
    found = (
        _on_file(
            db.query(ProductAttachment.id)
            .join(Attachment, Attachment.id == ProductAttachment.attachment_id)
            .outerjoin(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
        )
        .filter(
            ProductAttachment.product_id == str(product_id),
            ProductAttachment.attachment_id == str(attachment_id),
            or_(Attachment.company_id.is_(None), Attachment.company_id == company_id),
            kind if drawing else ~kind,
        )
        .first()
    )
    return found is not None


def _resolve(product_id: str, files: Sequence[ProductFile]) -> ProductImage:
    """The photograph decision for one visible product, from its files."""
    photos = tuple(f for f in files if not f.is_drawing)
    pick = next((f for f in photos if f.is_primary), None)
    if pick is None and len(photos) == 1:
        pick = photos[0]
    if pick is not None:
        return ProductImage(
            product_id=product_id,
            state=CHOSEN,
            attachment_id=pick.attachment_id,
            filename=pick.filename,
            candidate_count=len(photos),
            candidates=photos,
        )
    return ProductImage(
        product_id=product_id,
        state=NOT_CHOSEN if photos else NO_PHOTOS,
        candidate_count=len(photos),
        candidates=photos,
    )


def chosen_attachment_id(db: Session, product_id: Optional[str]) -> Optional[str]:
    """The photograph that IS this product, or nothing.

    Nothing is a real answer here: several photographs and none chosen is not guessed at - see
    the module docstring for why guessing is worse than not answering.
    """
    found = for_product(db, product_id)
    return found.attachment_id if found.state == CHOSEN else None


def for_product(db: Session, product_id: Optional[str]) -> ProductImage:
    """One product's picture state. ``None`` is off-catalog and costs no query."""
    if not product_id:
        return OFF_CATALOG_IMAGE
    return images_for(db, [product_id]).get(
        str(product_id), ProductImage(product_id=str(product_id), state=NO_PHOTOS)
    )


def images_for(
    db: Session,
    product_ids: Sequence[Optional[str]],
    files: Optional[Dict[str, List[ProductFile]]] = None,
) -> Dict[str, ProductImage]:
    """Every product's picture state, in a bounded number of queries.

    Bounded and not per-product on purpose: a quotation scope runs to 52 lines and the picture
    column is drawn on every render of it, so one round trip per row would be 52. ``files`` lets
    a caller that already read ``files_for`` (the quotation, for its drawings) skip that query.
    """
    wanted = [str(pid) for pid in product_ids if pid]
    if not wanted:
        return {}
    unique = list(dict.fromkeys(wanted))
    if files is None:
        files = files_for(db, unique)

    # Which of these products this company can actually SEE.
    #
    # Everything above answers from `product_attachments`, which is a link table and is NOT
    # company-scoped; `Product` is (`CompanyScopedMixin`). So a line naming another company's
    # product - 233 quotation lines in live data do exactly that, same codes, different company -
    # came back as NO_PHOTOS carrying a product_id, and the cell rendered "No photo on file" as a
    # LINK to a product page that 404s with "Product not found". Reported from the screen on
    # 2026-08-09 (a Sorento line pointing at Mocha's SRTWC8608-SC).
    #
    # A product this company cannot see is not a product as far as this screen is concerned,
    # which is precisely what OFF_CATALOG means. One extra query for the whole table, so the
    # one-pass rule above still holds.
    visible = {
        str(row[0]) for row in db.query(Product.id).filter(Product.id.in_(unique)).all()
    }

    resolved: Dict[str, ProductImage] = {}
    for product_id in unique:
        if product_id not in visible:
            resolved[product_id] = OFF_CATALOG_IMAGE
            continue
        resolved[product_id] = _resolve(product_id, files.get(product_id, []))
    return resolved


#: How long a handed-out picture URL is valid. ``storage_router`` (the one signing cache) hands
#: back the SAME string for a sixth of this, 40 minutes, so a table repainting its photos reuses
#: the browser's copy instead of re-downloading every one (the reason the old per-module cache
#: existed: a URL that changes on every render cannot be cached, and that took the system down
#: once). Four hours keeps that 40-minute window with most of the URL's life still ahead of it.
_URL_EXPIRES_IN = 4 * 60 * 60


def _sign(row: Attachment, *, full: bool) -> Optional[str]:
    """Sign this attachment's thumbnail (or ORIGINAL with ``full``) through ``storage_router``."""
    source = row.file_path if full else (row.thumbnail_path or row.file_path)
    try:
        return resolve_signed_url(source, provider=row.storage_provider, expires_in=_URL_EXPIRES_IN)
    except Exception:  # noqa: BLE001 - a cell with no picture beats a broken one
        logger.warning("product image: cannot sign %s", row.id, exc_info=True)
        return None


def signed_urls(row: Attachment) -> Tuple[Optional[str], Optional[str]]:
    """``(thumbnail, original)`` for a row already loaded."""
    thumb = _sign(row, full=False)
    full = _sign(row, full=True)
    return thumb, full or thumb



def preview_urls(
    db: Session, attachment_ids: Iterable[Optional[str]], full: bool = False
) -> Dict[str, Optional[str]]:
    """Signed URLs for a SCREEN, one query for the whole table.

    The thumbnail when there is one (~320 px): a line table showing 52 product photographs at
    full resolution is tens of megabytes down the wire for cells about 48 px across. Pass
    ``full`` for the ORIGINAL, which is what a preview that can be zoomed needs and what the
    thumbnail is far too small to serve.

    Signatures are reused through ``storage_router``'s cache - see ``_URL_EXPIRES_IN``.
    """
    wanted = list(dict.fromkeys(str(a) for a in attachment_ids if a))
    if not wanted:
        return {}
    return {
        str(row.id): _sign(row, full=full)
        for row in db.query(Attachment).filter(Attachment.id.in_(wanted)).all()
    }


# --------------------------------------------------------------------- embedding


def render(db: Session, attachment_id: Optional[str]) -> Optional[RenderedImage]:
    """Bytes for a document, downscaled into ``PRINT_BOX``.

    Best-effort throughout. Storage being down, a row that has gone, a format Pillow will not
    open: each degrades to no picture, never to a quotation that cannot be produced. The customer
    is waiting for a price, not a photograph.
    """
    if not attachment_id:
        return None
    try:
        row = db.query(Attachment).filter(Attachment.id == str(attachment_id)).first()
        if row is None:
            return None
        # The thumbnail is the source when one exists: it is already ~320 px, so downloading the
        # 4 MB original to throw 95% of it away is bandwidth spent for nothing.
        key = extract_key(row.thumbnail_path) or extract_key(row.file_path)
        if not key:
            return None
        provider = normalize_provider(row.storage_provider)
        raw = get_backend(provider).download_file(key)
    except Exception:  # noqa: BLE001 - cosmetic, never fatal to the document
        logger.warning("product image: cannot fetch %s", attachment_id, exc_info=True)
        return None

    return _downscale(raw, attachment_id)


def _downscale(
    raw: bytes,
    attachment_id: Any,
    box: int = PRINT_BOX,
    quality: int = JPEG_QUALITY,
    upright: bool = False,
    draft: bool = False,
    max_pixels: Optional[int] = None,
) -> Optional[RenderedImage]:
    """A document embed of ``raw`` inside ``box`` px: the shared ``image_thumbnailer.downscale``,
    limited to ``EMBEDDABLE_FORMATS``, with this module's print defaults."""
    return downscale(
        raw,
        box,
        quality,
        formats=EMBEDDABLE_FORMATS,
        upright=upright,
        draft=draft,
        max_pixels=max_pixels,
        label=attachment_id,
    )


#: Longest edge of the rendition the spec sheet tab draws its ONE open page with.
MEDIUM_BOX = 1024


def medium_urls(
    db: Session,
    attachment_ids: Iterable[Optional[str]],
    release: Optional[Any] = None,
) -> Dict[str, str]:
    """Signed URLs of each picture's medium rendition; never the original. A picture without one
    (not ready, cannot be made) is left out and the caller keeps showing its thumbnail."""
    return rendition_urls(db, attachment_ids, "medium", release=release)



def as_data_uri(rendered: Optional[RenderedImage]) -> Optional[str]:
    if rendered is None:
        return None
    return f"data:{rendered.mime_type};base64,{base64.b64encode(rendered.data).decode('ascii')}"


@dataclass(frozen=True)
class PictureSource:
    """Where one attachment's bytes live, read while the DB connection is held so the fetch
    itself needs none (QUOTE-PERF-HOTFIX)."""

    attachment_id: str
    thumbnail_key: Optional[str]
    original_key: Optional[str]
    provider: str
    mime_type: Optional[str]


def picture_sources(db: Session, attachment_ids: Iterable[Optional[str]]) -> Dict[str, PictureSource]:
    """One query for every picture a page will inline."""
    wanted = list(dict.fromkeys(str(a) for a in attachment_ids if a))
    if not wanted:
        return {}
    return {
        str(row.id): PictureSource(
            attachment_id=str(row.id),
            thumbnail_key=extract_key(row.thumbnail_path) if row.thumbnail_path else None,
            original_key=extract_key(row.file_path) if row.file_path else None,
            provider=normalize_provider(row.storage_provider),
            mime_type=row.mime_type,
        )
        for row in db.query(Attachment).filter(Attachment.id.in_(wanted)).all()
    }


def render_source(source: PictureSource) -> Tuple[Optional[RenderedImage], Optional[str]]:
    """``(picture, new thumbnail url)`` with no DB access.

    The stored thumbnail when there is one. Otherwise the original is read ONCE, a thumbnail is
    made from it and uploaded exactly as the upload path does (``store_thumbnail``), and its URL
    is handed back for the caller to save on the attachment, so the original is never read for
    this picture again.
    """
    from app.services.image_thumbnailer import store_thumbnail

    try:
        backend = get_backend(source.provider)
        if source.thumbnail_key:
            return _downscale(backend.download_file(source.thumbnail_key), source.attachment_id), None
        if not source.original_key:
            return None, None
        raw = backend.download_file(source.original_key)
    except Exception:  # noqa: BLE001 - cosmetic, never fatal to the page
        logger.warning("product image: cannot fetch %s", source.attachment_id, exc_info=True)
        return None, None
    made = store_thumbnail(backend, source.provider, source.original_key, raw, source.mime_type)
    return _downscale(raw, source.attachment_id, upright=True), made


def data_uri(
    db: Session,
    attachment_id: Optional[str],
    cache: Optional[Dict[str, Optional[str]]] = None,
) -> Optional[str]:
    """The picture inline, for a renderer that must not depend on the network.

    ``cache`` is per document: one product commonly repeats down a scope (a WC beside its valve
    and its hose), and without it the same object is downloaded once per line.
    """
    if not attachment_id:
        return None
    key_id = str(attachment_id)
    if cache is not None and key_id in cache:
        return cache[key_id]
    rendered = render(db, key_id)
    uri = (
        f"data:{rendered.mime_type};base64,{base64.b64encode(rendered.data).decode('ascii')}"
        if rendered is not None
        else None
    )
    if cache is not None:
        cache[key_id] = uri
    return uri


# ---------------------------------------------------------------------- writing


def choose(db: Session, link: ProductAttachment) -> ProductAttachment:
    """Record that THIS attachment is the product's photograph.

    Idempotent, never a toggle: choosing the one already chosen leaves it chosen, because a double
    click that silently left a product with no photo would be indistinguishable from never having
    chosen at all.

    The other primaries are cleared FIRST and in the same transaction. `product_attachments` also
    carries a partial unique index on `(company_id, product_id) WHERE is_primary IS TRUE`, so
    doing it in the other order trips the index rather than passing quietly - which is what would
    turn "choose a different photo" into a 500.
    """
    (
        db.query(ProductAttachment)
        .filter(
            ProductAttachment.product_id == link.product_id,
            ProductAttachment.id != link.id,
            ProductAttachment.is_primary.is_(True),
        )
        .update({ProductAttachment.is_primary: False}, synchronize_session="fetch")
    )
    link.is_primary = True
    db.flush()
    return link


def clear(db: Session, product_id: str) -> None:
    """Leave a product with no chosen photograph.

    Its consumers then show nothing and say so, which is a knowingly weak answer rather than a
    silently weak one.
    """
    (
        db.query(ProductAttachment)
        .filter(
            ProductAttachment.product_id == str(product_id),
            ProductAttachment.is_primary.is_(True),
        )
        .update({ProductAttachment.is_primary: False}, synchronize_session="fetch")
    )
    db.flush()


def serialize(
    image: ProductImage,
    url: Optional[str] = None,
    preview_url: Optional[str] = None,
) -> Dict[str, Any]:
    """The picture cell as the frontend reads it.

    `url` only ever accompanies `CHOSEN`: a signed link beside "nobody has chosen" would be a
    contradiction the screen has to resolve, and there is nothing to sign.

    `preview_url` is the ORIGINAL rather than the ~320 px thumbnail, for the viewer that opens
    when somebody clicks the cell, and `attachment_id` is what lets that viewer download the
    file through the authenticated route the rest of the system already uses. Both follow the
    same rule as `url`: present only on `CHOSEN`.
    """
    chosen = image.state == CHOSEN
    return {
        "state": image.state,
        "url": url if chosen else None,
        "preview_url": (preview_url or url) if chosen else None,
        "attachment_id": image.attachment_id if chosen else None,
        "filename": image.filename if chosen else None,
        "candidate_count": image.candidate_count,
    }


__all__: List[str] = [
    "CHOSEN",
    "DRAWING_TYPE",
    "MEDIUM_BOX",
    "NOT_CHOSEN",
    "PictureSource",
    "medium_urls",
    "as_data_uri",
    "picture_sources",
    "render_source",
    "NO_PHOTOS",
    "OFF_CATALOG",
    "PRINT_BOX",
    "EMBEDDABLE_FORMATS",
    "ProductFile",
    "ProductImage",
    "RenderedImage",
    "choose",
    "chosen_attachment_id",
    "clear",
    "data_uri",
    "files_for",
    "for_product",
    "images_for",
    "is_product_file",
    "preview_urls",
    "render",
    "serialize",
    "signed_urls",
]
