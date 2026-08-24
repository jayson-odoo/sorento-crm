"""CRM-side price tag request endpoints.

Mounted at ``/api/v1/dealer-kit`` behind
``require_module_enabled_with_api_key("dealer_kit")``.

Permission gates:
  * ``dealer_kit.price_tag_requests.view``    - list + detail
  * ``dealer_kit.price_tag_requests.process`` - claim, transition, line update
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.dealer_kit import Page, PageVersion
from app.models.price_tag import PriceTagRequest, PriceTagRequestLine
from app.schemas.price_tag import (
    PriceTagRequestLineResponse,
    PriceTagRequestLineUpdate,
    PriceTagRequestListItem,
    PriceTagRequestResponse,
    TagSheetDocPayload,
    TagSheetDocResponse,
    TagSheetExportIn,
    TagSheetExportOut,
    TransitionPayload,
)
from app.services.error_handler import AppException
from app.services.price_tag_request_service import (
    PriceTagRequestService,
    STATUS_DESIGNING,
    STATUS_NEW,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/price-tag-requests", tags=["price-tag-requests"])

_VIEW = require_permission_with_api_key("dealer_kit.price_tag_requests.view")
_PROCESS = require_permission("dealer_kit.price_tag_requests.process")


def _user_id(user: dict) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("", response_model=list[PriceTagRequestListItem])
def list_price_tag_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Paginated listing of price tag requests."""
    results = PriceTagRequestService.list_requests(
        db, status=status_filter, search=q,
    )
    return [PriceTagRequestListItem.model_validate(r) for r in results]


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get("/{request_id}", response_model=PriceTagRequestResponse)
def get_price_tag_request(
    request_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    req = PriceTagRequestService.get_request(db, request_id)
    if not req:
        raise AppException(
            status_code=404,
            message="Price tag request not found.",
            code="NOT_FOUND",
        )
    return PriceTagRequestResponse.model_validate(req)


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------


@router.post("/{request_id}/claim", response_model=PriceTagRequestResponse)
def claim_price_tag_request(
    request_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(_PROCESS),
):
    """Assign the request to the claiming user and transition new -> designing."""
    req = PriceTagRequestService.get_request(db, request_id)
    if not req:
        raise AppException(
            status_code=404,
            message="Price tag request not found.",
            code="NOT_FOUND",
        )
    if req.status != STATUS_NEW:
        raise AppException(
            status_code=409,
            message="Only requests in 'new' status can be claimed.",
            code="INVALID_STATE",
        )

    req.created_by = _user_id(user)
    result = PriceTagRequestService.transition_status(
        db, request_id, STATUS_DESIGNING, user_id=_user_id(user),
    )

    # Auto-create a tag_sheet page for this request if one does not exist.
    if not result.page_id:
        page = Page(
            name=f"Tags - {result.doc_number}",
            slug=f"tag-sheet-{result.doc_number.lower()}",
            kind="tag_sheet",
            request_id=result.id,
            company_id=result.company_id,
            created_by=_user_id(user),
        )
        db.add(page)
        db.flush()
        result.page_id = page.id

    db.commit()
    return PriceTagRequestResponse.model_validate(result)


# ---------------------------------------------------------------------------
# Transition
# ---------------------------------------------------------------------------


@router.post("/{request_id}/transition", response_model=PriceTagRequestResponse)
def transition_price_tag_request(
    request_id: str,
    payload: TransitionPayload,
    db: Session = Depends(get_db),
    user: dict = Depends(_PROCESS),
):
    """Apply a status transition with optional note."""
    result = PriceTagRequestService.transition_status(
        db, request_id, payload.status, user_id=_user_id(user),
    )
    db.commit()
    return PriceTagRequestResponse.model_validate(result)


# ---------------------------------------------------------------------------
# Line update
# ---------------------------------------------------------------------------


@router.put(
    "/{request_id}/lines/{line_id}",
    response_model=PriceTagRequestLineResponse,
)
def update_price_tag_request_line(
    request_id: str,
    line_id: str,
    payload: PriceTagRequestLineUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(_PROCESS),
):
    """Update a line (marketing_price_override, marketing_override_reason)."""
    line = (
        db.query(PriceTagRequestLine)
        .filter(
            PriceTagRequestLine.id == line_id,
            PriceTagRequestLine.request_id == request_id,
        )
        .first()
    )
    if not line:
        raise AppException(
            status_code=404,
            message="Request line not found.",
            code="NOT_FOUND",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(line, key, value)

    db.flush()
    db.commit()
    return PriceTagRequestLineResponse.model_validate(line)


# ---------------------------------------------------------------------------
# Tag sheet design doc
# ---------------------------------------------------------------------------


def _require_request_page(db: Session, request_id: str) -> tuple[PriceTagRequest, Page]:
    """Look up the request and its tag_sheet page, raising 404 on miss."""
    req = PriceTagRequestService.get_request(db, request_id)
    if not req:
        raise AppException(
            status_code=404, message="Price tag request not found.", code="NOT_FOUND",
        )
    if not req.page_id:
        raise AppException(
            status_code=404,
            message="No tag sheet page exists for this request. Claim the request first.",
            code="NO_PAGE",
        )
    page = db.query(Page).filter(Page.id == req.page_id).first()
    if not page:
        raise AppException(
            status_code=404, message="Tag sheet page not found.", code="NOT_FOUND",
        )
    return req, page


@router.get("/{request_id}/design", response_model=TagSheetDocResponse)
def get_tag_sheet_design(
    request_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Return the latest page_version doc for this request's tag_sheet page."""
    _req, page = _require_request_page(db, request_id)
    latest = (
        db.query(PageVersion)
        .filter(PageVersion.page_id == page.id)
        .order_by(PageVersion.version.desc())
        .first()
    )
    return TagSheetDocResponse(
        page_id=str(page.id),
        version=latest.version if latest else 0,
        doc=latest.doc if latest else None,
    )


@router.put("/{request_id}/design", response_model=TagSheetDocResponse)
def save_tag_sheet_design(
    request_id: str,
    payload: TagSheetDocPayload,
    db: Session = Depends(get_db),
    user: dict = Depends(_PROCESS),
):
    """Save a new page_version for the request's tag_sheet page."""
    _req, page = _require_request_page(db, request_id)

    current_max = (
        db.query(func.max(PageVersion.version))
        .filter(PageVersion.page_id == page.id)
        .scalar()
    ) or 0

    version = PageVersion(
        page_id=page.id,
        version=current_max + 1,
        doc=payload.doc,
        commit_message=payload.commit_message,
        created_by=_user_id(user),
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    return TagSheetDocResponse(
        page_id=str(page.id),
        version=version.version,
        doc=version.doc,
    )


@router.post("/{request_id}/resolve-prices")
def resolve_prices_for_lines(
    request_id: str,
    line_ids: list[str] = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
) -> list[dict[str, Any]]:
    """Return resolved price data for the given line IDs.

    Phase 1: returns mock-resolved data from the line's own fields. Phase 2
    will wire through ``resolve_prices`` from ``pricing.py``.
    """
    req = PriceTagRequestService.get_request(db, request_id)
    if not req:
        raise AppException(
            status_code=404, message="Price tag request not found.", code="NOT_FOUND",
        )

    lines_by_id = {str(line.id): line for line in req.lines}
    results: list[dict[str, Any]] = []

    for lid in line_ids:
        line = lines_by_id.get(lid)
        if not line:
            continue
        # Mock resolution: in Phase 2, this calls resolve_prices + product master.
        results.append({
            "line_id": str(line.id),
            "code": line.product_code if hasattr(line, "product_code") else "",
            "name": "",
            "list_price": None,
            "sell_price": None,
            "show_promo_price": line.show_promo_price,
            "dimensions": "",
            "spec_lines": "",
            "included_accessories": line.included_accessories or "",
        })

    return results


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@router.post(
    "/{request_id}/export",
    response_model=TagSheetExportOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def export_tag_sheet(
    request_id: str,
    payload: TagSheetExportIn = TagSheetExportIn(),
    db: Session = Depends(get_db),
    user: dict = Depends(_PROCESS),
):
    """Queue a tag sheet PDF export.

    202, not 201: the file does not exist yet. The response carries the download
    id so the caller can watch it in My Downloads.

    Checks:
    - Request must be in ``approved`` or ``ready`` status.
    - If the request has a promotion, it must not be expired (409).
    - On first export after ``approved``, transitions to ``ready``.
    """
    from app.services.dealer_kit.tag_sheet_export_service import (
        request_tag_sheet_export,
    )
    from app.services.download_service import DownloadService
    from app.services.queue_service import enqueue_job
    from app.tasks.dealer_kit_export_tasks import generate_tag_sheet_pdf

    download, sheet_ids = request_tag_sheet_export(
        db,
        request_id=request_id,
        user_id=_user_id(user) or "",
        sheet_ids=payload.sheet_ids,
    )

    try:
        enqueue_job(
            generate_tag_sheet_pdf,
            str(download.id),
            sheet_ids,
            queue_name="catalogue_render",
            job_timeout=900,
        )
    except Exception as exc:  # noqa: BLE001
        DownloadService(db).mark_failed(
            str(download.id), f"Could not queue PDF generation: {exc}"
        )

    db.refresh(download)
    return TagSheetExportOut(
        download_id=download.id,
        status=str(download.status),
        filename=download.filename,
    )
