"""Which photo of a product a brochure shows.

`product_attachments.is_primary` has always been the flag that decides a
catalogue tile's photo - `app/services/dealer_kit/product_images.py` already
orders by it - and it is false on every one of the 1,087 photo rows behind the
2025-2026 flyer's products. So a tile shows whichever row happened to be linked
first, and for `SRTWC286-SH` that is one of 31 files including a blank page and
two other products' photographs.

There is nothing to fix in the renderer. Somebody has to say which picture is
the product, and this is where that decision is recorded.

**Nothing is ever chosen automatically.** A filename containing the product code
would identify the right image for 509 of 535 products. Inferring from it is
deliberately rejected: a wrong photo is a wrong product in front of a customer,
and the same wrong photo fed to a 3D model generator is that plus a bill. Even a
product with exactly one candidate takes a click.

**The invariant is exactly one chosen image per product.** Two flagged at once
and the tile's photo is back at the mercy of row order, which is the defect this
module exists to remove. Enforced here on every write, and in the database by a
partial unique index so a path that bypasses this module cannot break it either.

This is product master data, not a Dealer Kit concept. The Kit is one consumer;
3D model generation is another, and it reads the same flag rather than asking
the question a second time.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.marketing import PromotionProduct
from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment
from app.services.error_handler import AppException

#: Page size when the caller does not say. Rows are tall - a product with 31
#: candidates is a wall of thumbnails - so a big page is a long scroll.
DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def set_brochure_image(
    db: Session,
    product_id: str,
    attachment_id: str,
    user_id: Optional[str] = None,
) -> ProductAttachment:
    """Record which image of a product a brochure shows.

    Idempotent: choosing the one already chosen leaves it chosen. A toggle would
    mean a double click silently leaves a product with no brochure image.

    Raises 404 - never 403 - when the product is out of scope or the attachment
    is not linked to it. A caller must not learn that a row they cannot reach
    exists.
    """
    # The company-scoped query filter does the tenancy work: a product belonging
    # to another company is simply not found, which is the 404 we want.
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise AppException(404, "Product not found")

    link = (
        db.query(ProductAttachment)
        .filter(
            ProductAttachment.product_id == product_id,
            ProductAttachment.attachment_id == attachment_id,
        )
        .first()
    )
    if link is None:
        raise AppException(404, "That file is not attached to this product")

    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if attachment is None or not _is_image(attachment):
        # `product_attachments` links whatever is attached to a product, and the
        # live data holds 532 PDFs. A spec sheet rendered as the product photo
        # is worse than no photo at all.
        raise AppException(400, "A brochure image has to be an image")

    # Cleared FIRST and in the same transaction as the set. The database also
    # holds a partial unique index, so doing this in the other order would trip
    # it rather than passing quietly.
    (
        db.query(ProductAttachment)
        .filter(
            ProductAttachment.product_id == product_id,
            ProductAttachment.attachment_id != attachment_id,
            ProductAttachment.is_primary.is_(True),
        )
        .update({ProductAttachment.is_primary: False}, synchronize_session="fetch")
    )

    link.is_primary = True
    db.flush()
    return link


def clear_brochure_image(db: Session, product_id: str) -> None:
    """Leave a product with no chosen image.

    Its tile falls back to the same first-linked-row behaviour as before, which
    is a knowingly weak answer rather than a silently weak one.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise AppException(404, "Product not found")

    (
        db.query(ProductAttachment)
        .filter(
            ProductAttachment.product_id == product_id,
            ProductAttachment.is_primary.is_(True),
        )
        .update({ProductAttachment.is_primary: False}, synchronize_session="fetch")
    )
    db.flush()


def list_brochure_images(
    db: Session,
    *,
    promotion_id: Optional[str] = None,
    product_ids: Optional[Sequence[str]] = None,
    only_unset: bool = True,
    query: Optional[str] = None,
    page: int = 1,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Products and the images somebody could choose between.

    `promotion_id` narrows to the products in one promotion, which is what makes
    "everything in the A3 flyer" one sitting rather than a hunt through 22,805
    products.

    Products with NO image are included on purpose. 465 of the flyer's codes are
    in that state and the answer there is a photo shoot, not a click; dropping
    them would hide the work instead of naming it.
    """
    limit = max(1, min(limit, MAX_LIMIT))
    page = max(1, page)

    products = db.query(Product)
    if product_ids:
        products = products.filter(Product.id.in_(list(product_ids)))
    if promotion_id:
        promoted = (
            db.query(PromotionProduct.product_id)
            .filter(PromotionProduct.promotion_id == promotion_id)
            .subquery()
        )
        products = products.filter(Product.id.in_(promoted))
    if query:
        needle = f"%{query.strip()}%"
        products = products.filter(
            or_(Product.product_code.ilike(needle), Product.product_name.ilike(needle))
        )

    # Which products have a chosen image, resolved for the WHOLE filtered set
    # rather than per row: `remaining` is the number the screen leads with, and
    # a per-row lookup would make it cost a query per product.
    candidate_rows = (
        db.query(ProductAttachment, Attachment)
        .join(Attachment, Attachment.id == ProductAttachment.attachment_id)
        .filter(ProductAttachment.product_id.in_(products.with_entities(Product.id).subquery()))
        .filter(Attachment.mime_type.ilike("image/%"))
        .order_by(
            ProductAttachment.product_id,
            (ProductAttachment.is_primary.is_(True)).desc(),
            ProductAttachment.sort_order.nullslast(),
            ProductAttachment.created_at,
        )
        .all()
    )

    by_product: dict[str, list[tuple[ProductAttachment, Attachment]]] = {}
    for link, attachment in candidate_rows:
        by_product.setdefault(link.product_id, []).append((link, attachment))

    chosen_of = {
        product_id: next(
            (link.attachment_id for link, _ in rows if link.is_primary), None
        )
        for product_id, rows in by_product.items()
    }

    all_products = products.order_by(Product.product_code).all()
    if only_unset:
        visible = [p for p in all_products if not chosen_of.get(p.id)]
    else:
        visible = all_products

    total = len(all_products)
    remaining = sum(1 for p in all_products if not chosen_of.get(p.id))
    window = visible[(page - 1) * limit : (page - 1) * limit + limit]

    return {
        "items": [
            {
                "productId": product.id,
                "productCode": product.product_code,
                "productName": product.product_name,
                "chosenAttachmentId": chosen_of.get(product.id),
                "candidates": [
                    {
                        "attachmentId": link.attachment_id,
                        "filename": attachment.original_filename,
                        # Resolved by the route, which owns URL signing. Keeping
                        # storage out of here leaves the service testable without
                        # reaching S3.
                        "url": None,
                        "accessLevels": link.access_levels,
                    }
                    for link, attachment in by_product.get(product.id, [])
                ],
            }
            for product in window
        ],
        "total": total,
        "remaining": remaining,
        "shown": len(visible),
    }


def _is_image(attachment: Attachment) -> bool:
    return bool(attachment.mime_type and attachment.mime_type.lower().startswith("image/"))


def signed_urls(
    rows: Iterable[dict[str, Any]],
    db: Session,
    expires_in: int = 3600,
) -> None:
    """Fill in each candidate's thumbnail URL, in place.

    Separate from the query so the service stays testable offline: a test of the
    listing rules should not need object storage to answer.
    """
    from app.services.storage_router import resolve_signed_url

    ids = [
        candidate["attachmentId"]
        for row in rows
        for candidate in row["candidates"]
    ]
    if not ids:
        return

    attachments = {
        attachment.id: attachment
        for attachment in db.query(Attachment).filter(Attachment.id.in_(ids)).all()
    }
    for row in rows:
        for candidate in row["candidates"]:
            attachment = attachments.get(candidate["attachmentId"])
            if not attachment:
                continue
            # A tile in the picker is about 112px. Sending full-size photos
            # would make a page of 31 candidates tens of megabytes.
            source = attachment.thumbnail_path or attachment.file_path
            candidate["url"] = resolve_signed_url(
                source, provider=attachment.storage_provider, expires_in=expires_in
            )
