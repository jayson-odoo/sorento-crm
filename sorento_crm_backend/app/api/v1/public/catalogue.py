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

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.base import company_scope
from app.models.company import Company
from app.schemas.dealer_kit import PublicPage
from app.services.dealer_kit import asset_service, document_bindings, public_cache
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


def _catalogue_response(request: Request, body: bytes, etag: str) -> Response:
    """The payload, or a 304 when the reader already has this exact one.

    A brochure serializes to hundreds of kilobytes, and the common case on this
    route is somebody reopening a link they were sent. `Cache-Control` uses the
    same window as the server-side entry so there is one staleness number to
    reason about rather than two.
    """
    headers = {
        "ETag": etag,
        "Cache-Control": f"public, max-age={public_cache.TTL_SECONDS}",
    }
    # A conditional request may send several, and a proxy may weaken ours.
    offered = [tag.strip() for tag in (request.headers.get("if-none-match") or "").split(",")]
    if etag in offered or f"W/{etag}" in offered:
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


@router.get("/{company_code}/{slug}", response_model=PublicPage)
def read_published_page(
    company_code: str,
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
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

    normalized_slug = slug.strip().lower()

    cached = public_cache.get(company.id, normalized_slug)
    if cached is not None:
        return _catalogue_response(request, *cached)

    with company_scope(db, frozenset({company.id})):
        live = svc.published_doc(db, normalized_slug)
        doc = live["doc"] or {}

        # Resolved HERE, for an anonymous reader. Without this a collection
        # block renders as an unbound placeholder on the public page, which is
        # the one surface where that is never acceptable.
        collections = document_bindings.resolve_bound_collections(
            db,
            doc,
            ANONYMOUS,
            # The page's own promotion prices every tile on it. Whether it
            # applies to the reader in front of us is decided per viewer, and
            # an anonymous reader is a consumer - so a trade offer never
            # reaches them.
            promotion_id=live["promotion_id"],
        )

        templates = document_bindings.tile_templates_for(
            db, doc, live["tile_template_id"]
        )
        # Assets are company-scoped too, so they resolve INSIDE the pinned
        # scope - outside it this comes back empty and every seeded section
        # silently loses its banner.
        assets = asset_service.background_urls(db, doc)

    page = PublicPage(
        name=live["name"],
        slug=live["slug"],
        doc=doc,
        collections={
            key: [_tile_out(tile) for tile in tiles] for key, tiles in collections.items()
        },
        tile_templates=templates,
        default_tile_template_id=live["tile_template_id"],
        assets=assets,
    )
    return _catalogue_response(request, *public_cache.put(company.id, normalized_slug, page))
