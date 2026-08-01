"""The render payload a print page loads, for the PDF worker.

Headless Chromium has no CRM session, so this route authenticates with the
short-lived HMAC token minted at enqueue rather than a principal. The token
proves the URL came from the enqueue path; it carries no audience of its own,
because the `export_request` row is the single source of truth for who the
render is for and a second answer would eventually disagree with the first.

Everything price-shaped is resolved HERE, through the snapshotted viewer, so
the page itself renders whatever it is handed and cannot accidentally ask for
more than the audience is entitled to.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.base import company_scope
from app.models.dealer_kit import Collection, Page
from app.services.dealer_kit import collection_service, export_service, render_token
from app.services.error_handler import AppException

router = APIRouter()


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



@router.get("/{download_id}")
def read_print_payload(
    download_id: str,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    if not render_token.verify(download_id, token):
        # Same answer for a forged token and an unknown download: whether a
        # download exists is not something an unauthenticated caller may probe.
        raise AppException(status_code=404, message="Not found")

    # `render_inputs` refuses outright when the snapshot is missing, rather than
    # falling back to a staff principal.
    inputs = export_service.render_inputs(db, download_id)
    viewer = inputs["viewer"]

    # The page is company-scoped and this request is unauthenticated, so the
    # session sits at the fail-closed UNSET scope and would find nothing. Read
    # it across all companies FIRST to learn which company it belongs to, then
    # pin the scope to that one company for everything else. Chicken-and-egg:
    # the scope has to come from the row it is about to gate.
    with company_scope(db, None):
        page = db.query(Page).filter(Page.id == inputs["page_id"]).first()
    if page is None:
        raise AppException(status_code=404, message="Page not found")

    # An unauthenticated request resolves to the fail-closed UNSET scope, under
    # which every owned read returns nothing. Pin it to the page's own company
    # so the render can see the catalogue it belongs to - and nothing else.
    scope = frozenset({page.company_id}) if page.company_id else None

    doc = inputs["doc"] or {}
    resolved: dict[str, list[dict]] = {}

    with company_scope(db, scope):
        # One candidate load for every collection on the page.
        candidates = collection_service.sellable_products(db)
        for section in doc.get("sections", []) or []:
            for block in section.get("blocks", []) or []:
                props = block.get("props") or {}
                if props.get("kind") != "collection":
                    continue
                collection_id = props.get("collectionId")
                if not collection_id or collection_id in resolved:
                    continue
                row = (
                    db.query(Collection).filter(Collection.id == collection_id).first()
                )
                resolved[collection_id] = (
                    collection_service.resolve_tiles(
                        db,
                        row,
                        viewer,
                        candidates,
                        # Read from the page NOW rather than snapshotted at
                        # enqueue, like every other price here: the document
                        # never stores a figure (AC-G1), so a promotion that
                        # ended while this sat in the queue must print as list
                        # prices. What IS pinned is the version, because that is
                        # the content somebody asked to export.
                        promotion_id=page.promotion_id,
                    )
                    if row is not None
                    else []
                )

        # Tile designs are company-scoped too, so they must be read inside the
        # pinned scope - outside it this silently returns {} and every tile
        # falls back to a default field list.
        templates = _tile_templates_for(db, doc)

    return {
        "pageName": page.name,
        "tileTemplates": templates,
        "version": inputs["version"],
        "audience": inputs["audience"],
        "doc": doc,
        # collectionId -> tiles, already priced for this audience.
        "collections": {
            collection_id: [
                {
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
                for tile in tiles
            ]
            for collection_id, tiles in resolved.items()
        },
    }
