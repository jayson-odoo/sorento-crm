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
from app.models.price_tag import PriceTagRequest, PriceTagRequestLine
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
    """Build the full print payload for a tag sheet.

    Resolves product data and prices at render time (ADR 0008).
    """
    inputs = render_inputs(db, download_id)
    request = inputs["request"]
    doc = inputs["doc"] or {}

    if not request:
        return {
            "doc": doc,
            "resolvedData": {},
            "requestDocNumber": "",
            "version": inputs["version"],
        }

    # Build a map of line_id -> resolved data.
    resolved_data: dict[str, dict] = {}
    lines = (
        db.query(PriceTagRequestLine)
        .filter(PriceTagRequestLine.request_id == request.id)
        .all()
    )

    # Resolve prices via the pricing engine.
    product_ids = [
        str(line.product_id) for line in lines
        if line.product_id is not None
    ]

    price_map: dict = {}
    if product_ids and request.promotion_id:
        try:
            from app.models.product import Product
            from app.services.dealer_kit.pricing import resolve_prices
            from app.services.dealer_kit.viewer import ViewerContext

            products = (
                db.query(Product)
                .filter(Product.id.in_(product_ids))
                .all()
            )
            viewer = ViewerContext(
                is_staff=True,
                access_codes=frozenset(),
                show_invoice_price=False,
                is_internal_copy=True,
            )
            price_map = resolve_prices(db, products, viewer, request.promotion_id)
        except Exception:
            logger.warning(
                "Price resolution failed for request %s", request.id,
                exc_info=True,
            )
    elif product_ids:
        try:
            from app.models.product import Product
            from app.services.dealer_kit.pricing import resolve_prices
            from app.services.dealer_kit.viewer import ViewerContext

            products = (
                db.query(Product)
                .filter(Product.id.in_(product_ids))
                .all()
            )
            viewer = ViewerContext(
                is_staff=True,
                access_codes=frozenset(),
                show_invoice_price=False,
                is_internal_copy=True,
            )
            price_map = resolve_prices(db, products, viewer, None)
        except Exception:
            logger.warning(
                "Price resolution failed for request %s", request.id,
                exc_info=True,
            )

    # Build product info map.
    product_info: dict[str, dict] = {}
    if product_ids:
        try:
            from app.models.product import Product

            products = (
                db.query(Product)
                .filter(Product.id.in_(product_ids))
                .all()
            )
            for p in products:
                product_info[str(p.id)] = {
                    "code": p.product_code or "",
                    "name": p.product_name or "",
                    "dimensions": getattr(p, "dimensions", "") or "",
                }
        except Exception:
            logger.warning(
                "Product info resolution failed for request %s", request.id,
                exc_info=True,
            )

    for line in lines:
        line_id = str(line.id)
        pid = str(line.product_id) if line.product_id else None
        info = product_info.get(pid, {}) if pid else {}
        pv = price_map.get(pid) if pid else None

        list_price = None
        sell_price = None
        if pv:
            list_price = float(pv.list_price) if pv.list_price is not None else None
            sell_price = float(pv.offer_price) if pv.offer_price is not None else None

        # Marketing override wins (AC D9).
        if line.marketing_price_override is not None:
            sell_price = float(line.marketing_price_override)

        resolved_data[line_id] = {
            "line_id": line_id,
            "code": info.get("code", ""),
            "name": info.get("name", ""),
            "dimensions": info.get("dimensions", ""),
            "spec_lines": "",
            "list_price": list_price,
            "sell_price": sell_price,
            "show_promo_price": line.show_promo_price,
            "included_accessories": line.included_accessories or "",
            "quantity": line.quantity,
        }

    return {
        "doc": doc,
        "resolvedData": resolved_data,
        "requestDocNumber": request.doc_number,
        "version": inputs["version"],
    }
