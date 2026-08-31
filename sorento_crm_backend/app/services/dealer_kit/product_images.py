"""The photo on a catalogue tile, chosen for whoever is looking.

A product photo is not neutral content. ``product_attachments.access_levels``
records who a given image is for, and the trade imagery - cutaways, fitting
diagrams, installation notes - is tagged ``dealer``. Sending those to a consumer
browsing the public catalogue would leak exactly the material the tagging exists
to control.

So the image goes through the same gate as the price, and for the same reason:
one published page serves staff, dealers and consumers, and each must see only
their own. It fails CLOSED - if the viewer's entitlement cannot be established,
the tile has no image rather than the wrong one.

Resolved in ONE query for the whole page. A per-tile lookup turns a forty
product catalogue into forty round trips, which is the difference between a page
that opens and a page a dealer gives up on.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.product import Product, ProductAttachment
from app.models.resources import Attachment
from app.services.dealer_kit.viewer import ViewerContext
from app.services.storage_router import resolve_signed_url

# What an anonymous reader of a public catalogue counts as. The public page is
# the consumer-facing surface, so consumer imagery is what it may show; dealer
# imagery still requires the dealer code.
PUBLIC_ACCESS_CODE = "end_user"


def _may_see(levels: Optional[Sequence[str]], viewer: ViewerContext) -> bool:
    """Whether this viewer is allowed this image.

    An image with NO levels recorded is treated as public. Those rows predate
    access tagging and were uploaded as catalogue imagery; hiding all of them
    would empty the catalogue to protect nothing.
    """
    if viewer.is_staff:
        return True
    if not levels:
        return True

    codes = set(viewer.access_codes) or {PUBLIC_ACCESS_CODE}
    return bool(codes & set(levels))


def primary_image_urls(
    db: Session,
    products: Iterable[Product],
    viewer: ViewerContext,
    expires_in: int = 3600,
) -> dict[str, str]:
    """``{product_id: url}`` for the products this viewer may see an image of.

    Absent rather than blank: a product with no permitted image is simply not in
    the map, so the tile renders its no-image state instead of a broken one.
    """
    product_ids = [product.id for product in products]
    if not product_ids:
        return {}

    rows = (
        db.query(ProductAttachment, Attachment)
        .join(Attachment, Attachment.id == ProductAttachment.attachment_id)
        .filter(ProductAttachment.product_id.in_(product_ids))
        # Images only. `product_attachments` links whatever is attached to a
        # product - the live data holds 532 PDFs and a couple of videos - and a
        # spec sheet rendered as the product photo is worse than no photo.
        .filter(Attachment.mime_type.ilike("image/%"))
        # Deleted in Resource Management is deleted on the tile too. 611 of the
        # 2,924 live product-to-image links point at a soft-deleted attachment,
        # and signing a URL for one is the catalogue disagreeing with the file
        # manager about what exists. The picker filters the same way, so the two
        # surfaces of this feature cannot drift.
        .filter(Attachment.is_deleted.is_(False))
        .order_by(
            ProductAttachment.product_id,
            # Someone deliberately marked one as primary; ordering must not
            # quietly override that. `is_primary` is nullable, so compare to
            # TRUE rather than relying on a bare DESC over NULLs.
            (ProductAttachment.is_primary.is_(True)).desc(),
            ProductAttachment.sort_order.nullslast(),
            ProductAttachment.created_at,
        )
        .all()
    )

    urls: dict[str, str] = {}
    for link, attachment in rows:
        if link.product_id in urls:
            continue  # the ordering above already picked the winner
        if not _may_see(link.access_levels, viewer):
            continue

        # A tile is around 300px wide. Sending the full-size photo turns a forty
        # product page into tens of megabytes over a showroom's wifi.
        source = attachment.thumbnail_path or attachment.file_path
        # strict: a photo that cannot be signed is an ABSENT image, not a broken
        # tile. The map already omits products with no permitted image and the
        # tile has a no-image state designed for exactly this, whereas an
        # unsigned URL reaches the browser and comes back 403.
        signed = resolve_signed_url(
            source,
            provider=attachment.storage_provider,
            expires_in=expires_in,
            strict=True,
        )
        if signed:
            urls[link.product_id] = signed

    return urls


def gallery_images(
    db: Session,
    product: Product,
    viewer: ViewerContext,
    expires_in: int = 3600,
) -> list[dict]:
    """EVERY photo of one product this viewer may see, primary first.

    ``primary_image_urls`` answers "the photo for this tile" for a whole page.
    A price tag is the other shape of the same question: the designer picks
    which of a product's photos goes on the tag - the accessory shot, the
    cutaway, the inside view - so they need the list, for one product.

    Same gate, same ordering, same strict signing, deliberately in this module
    rather than beside the tag code: ``_may_see`` decides who sees trade imagery
    and a second copy of that rule would drift the first time either was
    touched. An unsignable photo is ABSENT, exactly as it is for a tile.
    """
    rows = (
        db.query(ProductAttachment, Attachment)
        .join(Attachment, Attachment.id == ProductAttachment.attachment_id)
        .filter(ProductAttachment.product_id == product.id)
        .filter(Attachment.mime_type.ilike("image/%"))
        .filter(Attachment.is_deleted.is_(False))
        .order_by(
            (ProductAttachment.is_primary.is_(True)).desc(),
            ProductAttachment.sort_order.nullslast(),
            ProductAttachment.created_at,
        )
        .all()
    )

    images: list[dict] = []
    for link, attachment in rows:
        if not _may_see(link.access_levels, viewer):
            continue
        # The FULL image, not the thumbnail: this one is going on a printed tag
        # at 300dpi, where a 320px thumbnail is a smear.
        signed = resolve_signed_url(
            attachment.file_path,
            provider=attachment.storage_provider,
            expires_in=expires_in,
            strict=True,
        )
        if not signed:
            continue
        images.append(
            {
                "attachment_id": attachment.id,
                "url": signed,
                "is_primary": bool(link.is_primary),
            }
        )
    return images
