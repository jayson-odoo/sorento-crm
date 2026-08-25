"""Tag sheet PDF export: request, render payload, and promotion guard.

Follows the same snapshot pattern as ``export_service.py`` for catalogue pages:
the viewer context is decided at enqueue and never re-derived later. The print
page renders whatever it is handed and cannot accidentally resolve prices for
the wrong audience.

The key difference is the expired-promotion guard: a tag sheet's prices depend
on the request's ``promotion_id``, and printing stale prices is worse than
refusing to print. AC-H.2 says to return 409 with a reason.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.dealer_kit import ExportRequest, Page, PageVersion
from app.models.download import DownloadStatus, UserDownload
from app.models.price_tag import PriceTagRequest
from app.services.error_handler import AppException
from app.services.price_tag_request_service import STATUS_APPROVED, STATUS_READY

logger = logging.getLogger(__name__)

KIND = "dealer_kit_tag_sheet_pdf"


def _slugify(name: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in name.lower())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "tag-sheet"


def _check_promotion_expired(db: Session, request: PriceTagRequest) -> None:
    """Raise 409 if the request's promotion has expired.

    A tag sheet whose promotion has expired would print stale prices. Refusing
    with a clear reason is better than printing something wrong.
    """
    if not request.promotion_id:
        return

    from app.models.marketing import Promotion

    promo = (
        db.query(Promotion)
        .filter(Promotion.id == request.promotion_id)
        .first()
    )
    if promo is None:
        raise AppException(
            status_code=409,
            message=(
                "The promotion linked to this request no longer exists. "
                "Remove the promotion or link a new one before exporting."
            ),
            code="PROMOTION_MISSING",
        )

    today = date.today()
    if promo.end_date and promo.end_date < today:
        raise AppException(
            status_code=409,
            message=(
                f"The promotion '{promo.description or promo.id}' expired on "
                f"{promo.end_date.isoformat()}. Extend the promotion or remove "
                f"it from the request before exporting."
            ),
            code="PROMOTION_EXPIRED",
        )

    if not promo.is_active:
        raise AppException(
            status_code=409,
            message=(
                f"The promotion '{promo.description or promo.id}' is inactive. "
                f"Reactivate it or remove it from the request before exporting."
            ),
            code="PROMOTION_INACTIVE",
        )


def request_tag_sheet_export(
    db: Session,
    *,
    request_id: str,
    user_id: str,
    sheet_ids: Optional[list[str]] = None,
) -> tuple[UserDownload, Optional[list[str]]]:
    """Queue a tag sheet PDF and snapshot what it should contain.

    Returns (download, sheet_ids) so the caller can pass sheet_ids to the RQ task.

    Validates:
    - Request must be in ``approved`` or ``ready`` status.
    - Promotion must not be expired.
    - The request must have a tag_sheet page with at least one version.

    On first successful export after ``approved``, transitions to ``ready``.
    """
    if not user_id:
        raise AppException(
            status_code=422,
            message="An export needs a requesting user.",
        )

    request = (
        db.query(PriceTagRequest)
        .filter(PriceTagRequest.id == request_id)
        .first()
    )
    if request is None:
        raise AppException(
            status_code=404,
            message="Price tag request not found.",
            code="NOT_FOUND",
        )

    if request.status not in (STATUS_APPROVED, STATUS_READY):
        raise AppException(
            status_code=409,
            message=(
                f"Cannot export a request in '{request.status}' status. "
                f"The request must be approved before export."
            ),
            code="INVALID_STATE",
        )

    # Promotion guard (AC-H.2).
    _check_promotion_expired(db, request)

    if not request.page_id:
        raise AppException(
            status_code=409,
            message="No tag sheet page exists for this request.",
            code="NO_PAGE",
        )

    page = db.query(Page).filter(Page.id == request.page_id).first()
    if page is None:
        raise AppException(
            status_code=404,
            message="Tag sheet page not found.",
            code="NOT_FOUND",
        )

    # Use the latest version (tag sheets do not have published/staging labels).
    version = (
        db.query(PageVersion)
        .filter(PageVersion.page_id == page.id)
        .order_by(PageVersion.version.desc())
        .first()
    )
    if version is None:
        raise AppException(
            status_code=409,
            message="The tag sheet has no saved designs yet.",
            code="NO_VERSION",
        )

    filename = f"{_slugify(request.doc_number)}-tags-v{version.version}.pdf"

    download = UserDownload(
        user_id=user_id,
        kind=KIND,
        source_entity_type="price_tag_request",
        source_entity_id=request_id,
        status=DownloadStatus.PENDING.value,
        filename=filename,
    )
    db.add(download)
    db.flush()

    # Store sheet_ids filter in the export request metadata if provided.
    db.add(
        ExportRequest(
            download_id=download.id,
            page_id=page.id,
            page_version_id=version.id,
            # Staff audience for tag sheets (they go to the printer).
            audience="staff",
            show_invoice_price=False,
            requested_by=user_id,
        )
    )

    # Transition approved -> ready on first export (AC-H.3).
    if request.status == STATUS_APPROVED:
        from app.services.price_tag_request_service import PriceTagRequestService

        PriceTagRequestService.transition_status(
            db, request_id, STATUS_READY, user_id=user_id,
        )

    db.commit()
    db.refresh(download)

    # Store sheet_ids filter as metadata on the download row for the render
    # payload to read. We use the download's error field temporarily (it is
    # null for pending downloads) - but that is fragile. Instead, we store it
    # in the export_request row by extending the pattern slightly.
    # For now, sheet_ids are passed via the print URL query parameter.
    # The render payload endpoint reads them from there.

    return download, sheet_ids


def render_inputs(db: Session, download_id: str) -> dict:
    """Everything the tag sheet render needs."""
    from app.services.dealer_kit.export_service import get_request as _get_export_request

    export_req = _get_export_request(db, download_id)
    version = (
        db.query(PageVersion)
        .filter(PageVersion.id == export_req.page_version_id)
        .first()
    )
    if version is None:
        raise AppException(
            status_code=404,
            message="The exported version no longer exists.",
        )

    page = db.query(Page).filter(Page.id == export_req.page_id).first()
    if page is None:
        raise AppException(
            status_code=404,
            message="Tag sheet page not found.",
        )

    # Find the price tag request from the page.
    request = (
        db.query(PriceTagRequest)
        .filter(PriceTagRequest.page_id == page.id)
        .first()
    )

    return {
        "page_id": export_req.page_id,
        "version_id": version.id,
        "version": version.version,
        "doc": version.doc,
        "request": request,
        "page": page,
    }


def resolve_tag_sheet_print_payload(db: Session, download_id: str) -> dict:
    """Everything the print page renders, resolved at render time (ADR 0008).

    Prices and product data come from ``tag_data_service`` - the SAME call the
    designer's left panel makes - so the proof marketing approved on screen and
    the PDF that reaches the printer carry the same figures. Artwork is signed
    HERE and sent with the payload rather than fetched by the page: the worker
    waits on one ready flag, and a picture that starts loading after it prints
    as a blank box.
    """
    from app.services.dealer_kit import asset_service, tag_data_service

    inputs = render_inputs(db, download_id)
    request = inputs["request"]
    doc = inputs["doc"] or {}

    resolved_data: dict[str, dict] = {}
    images: dict[str, str] = {}

    if request is not None:
        for row in tag_data_service.resolve_request_line_data(db, request):
            for image in row["images"]:
                images[image["attachment_id"]] = image["url"]
            resolved_data[row["line_id"]] = {
                "line_id": row["line_id"],
                "code": row["code"],
                "name": row["name"],
                "dimensions": row["dimensions"],
                "spec_lines": row["spec_lines"],
                "set_members": row["set_members"],
                # Money leaves as a number the browser can format. The Decimal
                # arithmetic already happened, in the pricing engine.
                "list_price": _as_float(row["list_price"]),
                "sell_price": _as_float(row["sell_price"]),
                "show_promo_price": row["show_promo_price"],
                "included_accessories": row["included_accessories"],
                "quantity": row["quantity"],
            }

    return {
        "doc": doc,
        "resolvedData": resolved_data,
        # assetId -> signed URL, for every library asset the document names.
        "assets": asset_service.urls_for(
            db, asset_service.tag_sheet_asset_ids(doc)
        ),
        # attachmentId -> signed URL, for every product photo a bound layer may
        # be showing. Gated by `product_images` before it ever gets here.
        "images": images,
        # Brand fonts, loaded through @font-face before the page reports ready.
        "fonts": asset_service.font_assets(db),
        "requestDocNumber": request.doc_number if request is not None else "",
        "version": inputs["version"],
    }


def _as_float(value) -> Optional[float]:
    return None if value is None else float(value)
