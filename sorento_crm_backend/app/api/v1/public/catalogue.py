"""Public (unauthenticated) catalogue page rendering.

This is what a dealer or a consumer opens when they follow a shared link. It
lives under ``/api/v1/public`` rather than the Dealer Kit router because that
router sits behind the module guard, which needs a principal - and a reader has
none.

**Why the URL carries a company code.** ``dealer_kit.page.slug`` is unique PER
COMPANY, on purpose: Sorento and Mocha may each publish a "bathroom-2026". A
bare ``/c/{slug}`` therefore cannot resolve deterministically the moment a
second company exists, and resolving it by "whichever one matches" would be a
cross-company leak - precisely what the isolation work exists to prevent. So
the address is ``/c/{company_code}/{slug}``: the code (``SRT``, ``MCH``) is
short, stable, already unique, human-readable, and not a UUID.

**How scope works here.** An unauthenticated request resolves to the fail-closed
UNSET scope, under which every owned read returns zero rows. This route resolves
the company from the code FIRST, then reads inside a scope pinned to exactly
that one company. The lookup can never span companies, and an unknown code is
indistinguishable from an unpublished page: both are 404.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.base import company_scope
from app.models.company import Company
from app.models.dealer_kit import Collection
from app.schemas.dealer_kit import PublicPage
from app.services.dealer_kit import collection_service
from app.services.dealer_kit import page_service as svc
from app.services.dealer_kit.viewer import ANONYMOUS
from app.services.error_handler import AppException

router = APIRouter()


def _tile_out(tile: dict) -> dict:
    """snake_case resolver output -> the camelCase the renderer speaks."""
    return {
        "productId": tile["product_id"],
        "productCode": tile["product_code"],
        "productName": tile["product_name"],
        "price": tile["price"],
        "offerPrice": tile["offer_price"],
        "invoicePrice": tile["invoice_price"],
        "imageUrl": tile["image_url"],
        "dimensions": tile["dimensions"],
        "badges": tile["badges"],
    }


def _tile_templates_for(db, doc) -> dict:
    """templateId -> field list, for every design the document binds.

    Sent alongside the tiles so the renderer never has to fetch a design of its
    own: a print page that made its own API calls would be one more thing that
    can be half-finished when Chromium decides the page is idle.
    """
    from app.models.dealer_kit import TileTemplate
    from app.services.dealer_kit import tile_template_service

    ids = {
        (block.get("props") or {}).get("tileTemplateId")
        for section in (doc or {}).get("sections", []) or []
        for block in (section.get("blocks") or [])
        if (block.get("props") or {}).get("kind") == "collection"
    }
    ids.discard(None)
    if not ids:
        return {}

    rows = db.query(TileTemplate).filter(TileTemplate.id.in_(ids)).all()
    return {row.id: tile_template_service.fields_of(row) for row in rows}



@router.get("/{company_code}/{slug}", response_model=PublicPage)
def read_published_page(company_code: str, slug: str, db: Session = Depends(get_db)):
    company = (
        db.query(Company)
        .filter(
            func.lower(Company.code) == company_code.strip().lower(),
            Company.is_active.is_(True),
        )
        .first()
    )
    if company is None:
        # Deliberately the same answer as "no such page": whether a company
        # exists is not something an anonymous reader gets to probe.
        raise AppException(status_code=404, message="Page not found")

    with company_scope(db, frozenset({company.id})):
        live = svc.published_doc(db, slug.strip().lower())
        doc = live["doc"] or {}

        # Resolved HERE, for an anonymous reader. Without this a collection
        # block renders as an unbound placeholder on the public page, which is
        # the one surface where that is never acceptable.
        candidates = collection_service.sellable_products(db)
        collections: dict[str, list[dict]] = {}
        for section in doc.get("sections", []) or []:
            for block in section.get("blocks") or []:
                props = block.get("props") or {}
                if props.get("kind") != "collection":
                    continue
                collection_id = props.get("collectionId")
                if not collection_id or collection_id in collections:
                    continue
                row = (
                    db.query(Collection).filter(Collection.id == collection_id).first()
                )
                collections[collection_id] = (
                    collection_service.resolve_tiles(
                        db,
                        row,
                        ANONYMOUS,
                        candidates,
                        # The page's own promotion prices every tile on it.
                        # Whether it applies to the reader in front of us is
                        # decided per viewer, and an anonymous reader is a
                        # consumer - so a trade offer never reaches them.
                        promotion_id=live["promotion_id"],
                    )
                    if row is not None
                    else []
                )

        templates = _tile_templates_for(db, doc)

    return PublicPage(
        name=live["name"],
        slug=live["slug"],
        doc=doc,
        collections={
            key: [_tile_out(tile) for tile in tiles] for key, tiles in collections.items()
        },
        tile_templates=templates,
    )
