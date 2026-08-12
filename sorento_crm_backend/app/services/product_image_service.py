"""Which photograph of a product the system shows. One decision, read by everybody.

`product_attachments.is_primary` is that decision. It is **product master data, not a feature of
whoever happens to be rendering it**: the Dealer Kit brochure is one consumer, 3D-model generation
is another, and the project quotation is the third. Each reads this module rather than asking the
question a second time, because two answers to "which picture is this product" is the same as no
answer - the tile, the mesh and the customer's quotation would silently disagree.

**Nothing is ever chosen automatically, and there is deliberately no fallback.** Ordering by
`sort_order` and taking the first row looks like a reasonable default and is not: for
`SRTWC286-SH` the first-linked row is one of 31 files including a blank page and two other
products' photographs. A wrong photo is a wrong product in front of a customer, and the same wrong
photo fed to a mesh generator is that plus a bill. So a product nobody has answered for reports
`NOT_CHOSEN` and shows nothing, which is a state a screen can act on; a guess is not.

Three things are excluded from being a photograph at all, in every query here, and they have to
stay in step or a screen will count a product as done and then fail to show its picture:

- a non-image mime type (the live data holds 532 PDFs linked to products - a spec sheet rendered
  as the product photo is worse than no photo),
- a deleted attachment (611 live links point at one; Resource Management already hides them, so
  signing a URL for one puts a broken picture on a customer's document),
- for a *chosen* image, both of the above - a choice made before the file was deleted must stop
  being an answer, not linger as a broken one.

`render` exists because the artifacts embed bytes rather than link to them. The mean chosen image
in live data is 1.1 MB and the largest 4.3 MB, while the column it lands in is 60 CSS px wide, so
everything is downscaled into a bounded box first. Fifty-two originals inlined is a PDF nobody can
email.
"""
from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass
from time import monotonic
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment
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
#: A file Pillow cannot decode is passed through untouched rather than dropped - WeasyPrint
#: handles formats Pillow does not - but only while it is small enough that doing so cannot blow
#: up a document. Above this, no picture beats an unusable file.
RAW_FALLBACK_LIMIT = 256 * 1024


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


@dataclass(frozen=True)
class RenderedImage:
    """Bytes ready to embed, already inside ``PRINT_BOX``."""

    data: bytes
    mime_type: str
    width: int
    height: int


OFF_CATALOG_IMAGE = ProductImage(product_id=None, state=OFF_CATALOG)


# ----------------------------------------------------------------------- reading


def _photograph(query):
    """The three conditions that make an attachment a photograph, applied in one place.

    Every query in this module goes through here. Two of them drifting apart is how a screen ends
    up counting a product as answered and then rendering nothing for it.
    """
    return query.filter(
        Attachment.mime_type.ilike("image/%"),
        Attachment.is_deleted.is_(False),
    )


def chosen_attachment_id(db: Session, product_id: Optional[str]) -> Optional[str]:
    """The attachment somebody chose for this product, or nothing.

    Nothing is a real answer here. There is no ordering, no first-row fallback and no filename
    heuristic - see the module docstring for why guessing is worse than not answering.
    """
    if not product_id:
        return None
    row = (
        _photograph(
            db.query(ProductAttachment.attachment_id).join(
                Attachment, Attachment.id == ProductAttachment.attachment_id
            )
        )
        .filter(
            ProductAttachment.product_id == str(product_id),
            ProductAttachment.is_primary.is_(True),
        )
        .first()
    )
    return row[0] if row else None


def for_product(db: Session, product_id: Optional[str]) -> ProductImage:
    """One product's picture state. ``None`` is off-catalog and costs no query."""
    if not product_id:
        return OFF_CATALOG_IMAGE
    return images_for(db, [product_id]).get(
        str(product_id), ProductImage(product_id=str(product_id), state=NO_PHOTOS)
    )


def images_for(db: Session, product_ids: Sequence[Optional[str]]) -> Dict[str, ProductImage]:
    """Every product's picture state, in a bounded number of queries.

    Bounded and not per-product on purpose: a quotation scope runs to 52 lines and the picture
    column is drawn on every render of it, so one round trip per row would be 52.
    """
    wanted = [str(pid) for pid in product_ids if pid]
    if not wanted:
        return {}
    unique = list(dict.fromkeys(wanted))

    chosen = {
        product_id: (attachment_id, filename)
        for product_id, attachment_id, filename in _photograph(
            db.query(
                ProductAttachment.product_id,
                ProductAttachment.attachment_id,
                func.coalesce(Attachment.original_filename, Attachment.stored_filename),
            ).join(Attachment, Attachment.id == ProductAttachment.attachment_id)
        )
        .filter(
            ProductAttachment.product_id.in_(unique),
            ProductAttachment.is_primary.is_(True),
        )
        .all()
    }

    counts = dict(
        _photograph(
            db.query(ProductAttachment.product_id, func.count(ProductAttachment.id)).join(
                Attachment, Attachment.id == ProductAttachment.attachment_id
            )
        )
        .filter(ProductAttachment.product_id.in_(unique))
        .group_by(ProductAttachment.product_id)
        .all()
    )

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
        candidates = int(counts.get(product_id, 0))
        pick = chosen.get(product_id)
        if pick is not None:
            resolved[product_id] = ProductImage(
                product_id=product_id,
                state=CHOSEN,
                attachment_id=pick[0],
                filename=pick[1],
                candidate_count=candidates,
            )
        else:
            resolved[product_id] = ProductImage(
                product_id=product_id,
                state=NOT_CHOSEN if candidates else NO_PHOTOS,
                candidate_count=candidates,
            )
    return resolved


#: How long a handed-out URL is reused before it is signed again.
#:
#: This is a BUCKET-TRAFFIC control, not a CPU one. Signing is a local HMAC and costs nothing,
#: but it produces a DIFFERENT string every time (the signature covers a timestamp), and a URL
#: that changes on every render is a URL the browser can never serve from its own cache. So a
#: 52-line table re-downloaded all 52 photographs from the bucket on every paint, and opening
#: a full-size preview re-downloaded the original every time. Returning the SAME string inside
#: a window turns all of that into cache hits, which is the difference between one GET per
#: photo per user per window and one per render. Getting this wrong has taken the system down
#: before.
_URL_TTL = 45 * 60
#: Deliberately longer than the TTL, so a URL served at the last moment of its cache window
#: still has a quarter of an hour of validity left in the browser.
_URL_EXPIRES_IN = 60 * 60
#: A plain bound so a long-lived process cannot grow this without limit. Evicting the whole
#: thing is fine: the cost of a miss is one local HMAC.
_URL_CACHE_MAX = 4096

#: (attachment_id, "thumb" | "full") -> (url, monotonic deadline)
_url_cache: Dict[tuple, tuple] = {}


def _cached_sign(row: Attachment, *, full: bool) -> Optional[str]:
    """Sign this attachment, reusing the last signature while it is still fresh."""
    key = (str(row.id), "full" if full else "thumb")
    now = monotonic()
    hit = _url_cache.get(key)
    if hit is not None and hit[1] > now:
        return hit[0]

    source = row.file_path if full else (row.thumbnail_path or row.file_path)
    try:
        url = resolve_signed_url(
            source, provider=row.storage_provider, expires_in=_URL_EXPIRES_IN
        )
    except Exception:  # noqa: BLE001 - a cell with no picture beats a broken one
        logger.warning("product image: cannot sign %s", row.id, exc_info=True)
        return None

    if len(_url_cache) >= _URL_CACHE_MAX:
        _url_cache.clear()
    _url_cache[key] = (url, now + _URL_TTL)
    return url


def preview_urls(
    db: Session, attachment_ids: Iterable[Optional[str]], full: bool = False
) -> Dict[str, Optional[str]]:
    """Signed URLs for a SCREEN, one query for the whole table.

    The thumbnail when there is one (~320 px): a line table showing 52 product photographs at
    full resolution is tens of megabytes down the wire for cells about 48 px across. Pass
    ``full`` for the ORIGINAL, which is what a preview that can be zoomed needs and what the
    thumbnail is far too small to serve.

    Both are cached per attachment - see ``_URL_TTL``.
    """
    wanted = list(dict.fromkeys(str(a) for a in attachment_ids if a))
    if not wanted:
        return {}
    return {
        str(row.id): _cached_sign(row, full=full)
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

    mime = (row.mime_type or "").lower()
    if not mime.startswith("image/"):
        mime = "image/jpeg"
    return _downscale(raw, mime, attachment_id)


def _downscale(raw: bytes, mime: str, attachment_id: Any) -> Optional[RenderedImage]:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw)) as opened:
            opened.load()
            # Flattened onto white rather than converted straight to RGB: a PNG with alpha comes
            # out of a naive convert with black behind it, and a product cut out on transparency
            # is exactly the kind of file that gets uploaded.
            if opened.mode in ("RGBA", "LA", "P"):
                rgba = opened.convert("RGBA")
                canvas = Image.new("RGB", rgba.size, (255, 255, 255))
                canvas.paste(rgba, mask=rgba.split()[-1])
                image = canvas
            else:
                # CMYK is the other one that bites: a CMYK JPEG re-saved as-is renders inverted.
                image = opened.convert("RGB")
            image.thumbnail((PRINT_BOX, PRINT_BOX), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            return RenderedImage(
                data=buffer.getvalue(),
                mime_type="image/jpeg",
                width=image.width,
                height=image.height,
            )
    except Exception:  # noqa: BLE001
        # Pillow handles fewer formats than WeasyPrint does, so a decode failure is not proof the
        # file is unusable - it is passed through while it is small enough that doing so cannot
        # blow the document up.
        if len(raw) <= RAW_FALLBACK_LIMIT:
            logger.info(
                "product image: %s not decodable, embedding %d raw bytes",
                attachment_id,
                len(raw),
            )
            return RenderedImage(data=raw, mime_type=mime, width=0, height=0)
        logger.warning(
            "product image: %s not decodable and too large (%d bytes) to embed raw",
            attachment_id,
            len(raw),
        )
        return None


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
    "NOT_CHOSEN",
    "NO_PHOTOS",
    "OFF_CATALOG",
    "PRINT_BOX",
    "RAW_FALLBACK_LIMIT",
    "ProductImage",
    "RenderedImage",
    "choose",
    "chosen_attachment_id",
    "clear",
    "data_uri",
    "for_product",
    "images_for",
    "preview_urls",
    "render",
    "serialize",
]
