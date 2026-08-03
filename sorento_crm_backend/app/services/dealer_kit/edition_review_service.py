"""What changed in a catalogue since the last Edition (S2.5.5, AC-L9).

Starting a new Edition inherits the layout - it is the same page, and the page
IS the layout. So nothing here duplicates anything. What a Designer actually
needs before reworking last season's catalogue is what the inherited document
no longer says truthfully, and that is what this computes, with no manual
marking (AC-L9).

**The dropped products are the reason this exists.** ``resolve_members``
filters ``is_discontinued`` and ``is_active`` out of the candidate set, and
repeats the filter on the pinned path, so a product that has been discontinued
since the catalogue was built does not render as a struck-through tile - it
VANISHES. The collection quietly holds one fewer product and nothing on any
screen says so. 5,317 of the live catalogue's products are discontinued, so
this is the normal case and not an edge one.

Hence: a pin that no longer resolves is reported as DROPPED, against the pin
rather than against the rendering. That is the only place the information still
exists.

**"New since the last Edition" is only meaningful because collections resolve
at read time.** A rule-based collection in an inherited layout picks up
products created since the previous Edition on its own, and nobody chose them.
Those get badged so a Designer sees what walked into the catalogue while they
were not looking.

Stock is reported per member because "should this still be the hero tile" is a
question about stock, and the answer currently lives on another screen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.dealer_kit import Collection, Edition, PageVersion
from app.models.inventory import Stock
from app.models.product import Product
from app.services.dealer_kit import collection_service


@dataclass(frozen=True)
class ReviewedProduct:
    """One product the inherited catalogue still binds."""

    product_id: str
    product_code: str
    product_name: str
    stock_on_hand: int
    # Created after the previous Edition started. Nobody chose it: a rule
    # picked it up when the collection resolved.
    is_new_since_previous: bool


@dataclass(frozen=True)
class DroppedProduct:
    """A product this catalogue names and can no longer show.

    ``reason`` separates the two ways it happens, because they send somebody to
    different places: a discontinued product is a commercial decision to accept,
    a missing one is data somebody deleted.
    """

    product_id: str
    product_code: Optional[str]
    product_name: Optional[str]
    reason: str  # "discontinued" | "inactive" | "missing"


@dataclass(frozen=True)
class EditionReview:
    members: list[ReviewedProduct] = field(default_factory=list)
    dropped: list[DroppedProduct] = field(default_factory=list)
    # The Edition this was compared against. None on a first Edition, which is
    # why "new since" is empty rather than "everything".
    previous_edition_name: Optional[str] = None


DISCONTINUED = "discontinued"
INACTIVE = "inactive"
MISSING = "missing"


def _collection_ids(doc: Optional[dict]) -> list[str]:
    """Every collection the document binds, in reading order, de-duplicated.

    Read off the doc rather than off the page's collection rows: a collection
    can exist against a page and no longer be placed in the current version,
    and reporting on one nobody can see would send a Designer hunting for a
    tile that is not there.
    """
    seen: dict[str, None] = {}
    for section in (doc or {}).get("sections", []) or []:
        for block in section.get("blocks", []) or []:
            if block.get("type") != "collection":
                continue
            collection_id = (block.get("props") or {}).get("collectionId")
            if collection_id:
                seen.setdefault(str(collection_id), None)
    return list(seen)


def _latest_version(db: Session, page_id: str) -> Optional[PageVersion]:
    return (
        db.query(PageVersion)
        .filter(PageVersion.page_id == page_id)
        .order_by(PageVersion.version.desc())
        .first()
    )


def _cutoff(db: Session, edition: Edition) -> tuple[Optional[datetime], Optional[str]]:
    """When the previous Edition began, and what it was called.

    Its CREATED time, not its approval: "new since the last Edition" means new
    since that cycle started, which is the window a Designer was not watching.
    Approval can be weeks later, and products arriving in between are exactly
    the ones worth badging.
    """
    if not edition.previous_edition_id:
        return None, None
    previous = (
        db.query(Edition).filter(Edition.id == edition.previous_edition_id).first()
    )
    if previous is None:
        return None, None
    return previous.created_at, previous.name


def review(db: Session, edition: Edition) -> EditionReview:
    version = _latest_version(db, edition.page_id)
    if version is None:
        return EditionReview()

    collection_ids = _collection_ids(version.doc)
    if not collection_ids:
        return EditionReview(previous_edition_name=_cutoff(db, edition)[1])

    collections = (
        db.query(Collection).filter(Collection.id.in_(collection_ids)).all()
    )

    # One candidate load for every collection on the page. resolve_members
    # would otherwise scan the whole sellable catalogue per collection, and a
    # seeded flyer page carries hundreds of them.
    candidates = collection_service.sellable_products(db)

    members: dict[str, Product] = {}
    pinned: dict[str, None] = {}
    for collection in collections:
        for product in collection_service.resolve_members(db, collection, candidates):
            members.setdefault(product.id, product)
        for product_id in collection.pinned_product_ids or []:
            if product_id:
                pinned.setdefault(str(product_id), None)

    cutoff, previous_name = _cutoff(db, edition)

    return EditionReview(
        members=_members(db, list(members.values()), cutoff),
        dropped=_dropped(db, [pin for pin in pinned if pin not in members]),
        previous_edition_name=previous_name,
    )


def _members(
    db: Session, products: list[Product], cutoff: Optional[datetime]
) -> list[ReviewedProduct]:
    if not products:
        return []

    on_hand = _stock_on_hand(db, [product.id for product in products])

    return [
        ReviewedProduct(
            product_id=product.id,
            product_code=product.product_code,
            product_name=product.product_name,
            stock_on_hand=on_hand.get(product.id, 0),
            # No previous Edition means no window, so nothing is "new since" -
            # deliberately not "everything is new", which would badge the whole
            # catalogue on the first Edition and teach people to ignore it.
            is_new_since_previous=bool(
                cutoff and product.created_at and product.created_at > cutoff
            ),
        )
        for product in products
    ]


def _stock_on_hand(db: Session, product_ids: list[str]) -> dict[str, int]:
    """Summed across warehouses, in ONE statement.

    A catalogue tile is not warehouse-specific, so the question "is there any
    of this" is answered across all of them. A product with no stock row at all
    is absent here and reads as zero at the call site, which is what no row
    means.
    """
    rows = (
        db.query(Stock.product_id, func.coalesce(func.sum(Stock.quantity_on_hand), 0))
        .filter(Stock.product_id.in_(product_ids))
        .group_by(Stock.product_id)
        .all()
    )
    return {product_id: int(total or 0) for product_id, total in rows}


def _dropped(db: Session, product_ids: list[str]) -> list[DroppedProduct]:
    """Pins that resolve to nothing, and why.

    Loaded WITHOUT the sellable filter - the whole point is to see the rows the
    resolver refused. A pin with no row at all is reported as missing rather
    than skipped: "this catalogue names a product that no longer exists" is the
    thing somebody has to act on.
    """
    if not product_ids:
        return []

    rows = {
        product.id: product
        for product in db.query(Product).filter(Product.id.in_(product_ids)).all()
    }

    dropped: list[DroppedProduct] = []
    for product_id in product_ids:
        product: Any = rows.get(product_id)
        if product is None:
            dropped.append(
                DroppedProduct(
                    product_id=product_id,
                    product_code=None,
                    product_name=None,
                    reason=MISSING,
                )
            )
            continue
        # Discontinued wins when a row is both: it is the commercial fact, and
        # "inactive" would send somebody to reactivate a product that is
        # deliberately end-of-life.
        reason = DISCONTINUED if product.is_discontinued else INACTIVE
        dropped.append(
            DroppedProduct(
                product_id=product.id,
                product_code=product.product_code,
                product_name=product.product_name,
                reason=reason,
            )
        )
    return dropped
