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
from app.models.dealer_kit import Page
from app.services.dealer_kit import (
    asset_service,
    document_bindings,
    export_service,
    render_token,
)
from app.services.error_handler import AppException

router = APIRouter()


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

    with company_scope(db, scope):
        resolved = document_bindings.resolve_bound_collections(
            db,
            doc,
            viewer,
            # Read from the page NOW rather than snapshotted at enqueue, like
            # every other price here: the document never stores a figure
            # (AC-G1), so a promotion that ended while this sat in the queue
            # must print as list prices. What IS pinned is the version, because
            # that is the content somebody asked to export.
            promotion_id=page.promotion_id,
        )

        # Tile designs are company-scoped too, so they must be read inside the
        # pinned scope - outside it this silently returns {} and every tile
        # falls back to a default field list. The PAGE's default is included:
        # printing a brochure whose blocks name no design must not print
        # something that looks nothing like the page on screen.
        templates = document_bindings.tile_templates_for(
            db, doc, page.tile_template_id
        )
        # Section backgrounds, signed for this render. Sent with the payload
        # so the print page never fetches an image of its own: the worker
        # waits on one ready flag, and a background loaded after it prints
        # as a blank band.
        assets = asset_service.background_urls(db, doc)

    return {
        "pageName": page.name,
        "tileTemplates": templates,
        "defaultTileTemplateId": page.tile_template_id,
        "version": inputs["version"],
        "audience": inputs["audience"],
        "doc": doc,
        # assetId -> signed URL for every section background on the page.
        "assets": assets,
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


@router.get("/tag-sheet/{download_id}")
def read_tag_sheet_print_payload(
    download_id: str,
    token: str = Query(...),
    sheet: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
):
    """Render payload for tag sheet PDF export.

    Resolves product data and prices at render time (ADR 0008). The print page
    renders DOM/CSS elements (not Konva) for Chromium's ``page.pdf()``.

    ``sheet`` query params filter to specific sheet ids. Empty = all sheets.
    """
    if not render_token.verify(download_id, token):
        raise AppException(status_code=404, message="Not found")

    from app.models.base import company_scope as _company_scope
    from app.services.dealer_kit.tag_sheet_export_service import (
        resolve_tag_sheet_print_payload,
    )

    # Tag sheet pages are company-scoped; read across all companies to learn
    # which one, then pin the scope for price resolution.
    with _company_scope(db, None):
        payload = resolve_tag_sheet_print_payload(db, download_id)

    # Filter sheets if specific ids were requested.
    if sheet and payload.get("doc"):
        doc = payload["doc"]
        if "sheets" in doc:
            doc["sheets"] = [
                s for s in doc["sheets"] if s.get("id") in sheet
            ]

    return payload
