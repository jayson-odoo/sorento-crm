"""Order inquiry rows, their state and the export (P10, AC-I1 to AC-I7).

Reading is the project's own view grant, because the inquiry is part of reading a
project. ACTING on a row is `projects.order_inquiry.action`, which is purchasing's grant
rather than the project owner's: the row is purchasing's work and they do not own the
project it came from, so gating it on project edit would mean granting purchasing the
right to edit every pursuit in the company.

Rows are never created here. They are DERIVED when a sales order or an amendment
publishes, which is the only moment the instruction is true.
"""
from __future__ import annotations

import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.project_order_inquiry import (
    MarkInquiryRowsRequest,
    OrderInquiryDetail,
    OrderInquiryPoCandidate,
    OrderInquiryRowOut,
    OrderInquirySummary,
    OrderInquiryWorklistRow,
    OrderInquiryWorklistSummary,
    PlaceOnPoRequest,
)
from app.services import project_service as projects
from app.services.error_handler import AppException, handle_internal_error
from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.uuid_path_param import validate_uuid_path

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW = "projects.projects.view"
ACTION = "projects.order_inquiry.action"

#: The sort set the list accepts, declared here as a `Literal` because FastAPI cannot
#: build one from a runtime set. It MUST equal `SORTABLE_FIELDS` in the service, and a
#: test asserts the two agree.
WorklistSort = Literal[
    "so_date",
    "so_number",
    "item_code",
    "product_name",
    "qty",
    "delivery_date",
    "project_customer",
    "supplier",
    "po_number",
    "state",
    "raised_at",
    "location",
    "agent",
]

WORKLIST_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _worklist_filters(
    query: Optional[str],
    delivery_month: Optional[str],
    raised_date: Optional[str],
    state: Optional[str],
    project_id: Optional[str],
    supplier_id: Optional[str],
) -> dict:
    if project_id:
        validate_uuid_path(project_id, resource="Project")
    if supplier_id:
        validate_uuid_path(supplier_id, resource="Supplier")
    return {
        "query": query,
        "delivery_month": delivery_month,
        "raised_date": raised_date,
        "state": state,
        "project_id": project_id,
        "supplier_id": supplier_id,
    }


@router.get("/order-inquiries", response_model=ListResponse[OrderInquiryWorklistRow])
def list_order_inquiry_worklist(
    query: Optional[str] = Query(
        None,
        description=(
            "One box. Matches the sales-order number, the item code, the product name or "
            "code, the customer and the project."
        ),
    ),
    delivery_month: Optional[str] = Query(
        None, description="`YYYY-MM`. The sheet tab purchasing works a month at a time."
    ),
    raised_date: Optional[str] = Query(
        None, description="`YYYY-MM-DD`. What was raised on one day, their per-day tab."
    ),
    # A closed set for the same reason `sort` is: a filter nothing can equal reads on
    # screen as "no work to do" when the truth is "that is not a state".
    state: Optional[Literal["raised", "actioned", "cancelled", "placed"]] = Query(None),
    project_id: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
    sort: Optional[WorklistSort] = Query(
        None, description="Defaults to delivery_date. Nulls always last."
    ),
    direction: Optional[Literal["asc", "desc"]] = Query(
        "asc",
        alias="dir",
        description="Nulls sort last in BOTH directions, never first on desc.",
    ),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """Everything purchasing has been told to buy, whoever it belongs to.

    Cross-project because purchasing is: an order ADOPTED from the AutoCount book has no
    project registration at all, so its rows appear on no per-project list and were
    reachable only from the one sales order that raised them.

    Plain ``def``, so FastAPI runs the whole handler in a threadpool: it is synchronous
    SQLAlchemy over a page of rows, and on the event loop it holds up every other request
    the worker is serving.
    """
    try:
        return OrderInquiryWorklistService(db).list_rows(
            page=page,
            limit=limit,
            sort=sort,
            direction=direction,
            **_worklist_filters(
                query, delivery_month, raised_date, state, project_id, supplier_id
            ),
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/order-inquiries/summary", response_model=OrderInquiryWorklistSummary)
def order_inquiry_worklist_summary(
    query: Optional[str] = Query(None),
    delivery_month: Optional[str] = Query(None),
    raised_date: Optional[str] = Query(None),
    state: Optional[Literal["raised", "actioned", "cancelled", "placed"]] = Query(None),
    project_id: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """The strip above the list, and the month / supplier / project controls beside it."""
    try:
        return OrderInquiryWorklistService(db).summary(
            **_worklist_filters(
                query, delivery_month, raised_date, state, project_id, supplier_id
            ),
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/order-inquiries/export")
def export_order_inquiry_worklist(
    query: Optional[str] = Query(None),
    delivery_month: Optional[str] = Query(None),
    raised_date: Optional[str] = Query(None),
    state: Optional[Literal["raised", "actioned", "cancelled", "placed"]] = Query(None),
    project_id: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """The filtered set as the workbook purchasing already reads: a sheet per month.

    Generated per request rather than stored, exactly as the per-project export is: a
    stored file goes stale the moment supply is reconfirmed, and a stale instruction is
    the thing this replaces.
    """
    try:
        filename, body = OrderInquiryWorklistService(db).export_xlsx(
            **_worklist_filters(
                query, delivery_month, raised_date, state, project_id, supplier_id
            )
        )
        return Response(
            content=body,
            media_type=WORKLIST_XLSX,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/projects/{project_id}/order-inquiry-rows",
    response_model=ListResponse[OrderInquiryRowOut],
)
async def list_order_inquiry_rows(
    project_id: str,
    query: Optional[str] = Query(None, description="Item code, SPO ref, location or SO number"),
    verb: Optional[List[str]] = Query(None),
    state: Optional[List[str]] = Query(None),
    sales_order_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    sort: str = Query("delivery_date"),
    dir: str = Query("asc"),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """Every instruction raised on one project, in delivery-date order by default."""
    try:
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        service = ProjectOrderInquiryService(db)
        rows, total = service.list_rows(
            project_id,
            query=query,
            verb=verb,
            state=state,
            pso_id=sales_order_id,
            page=page,
            limit=limit,
            sort=sort,
            direction=dir,
        )
        return {
            "data": rows,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/projects/{project_id}/order-inquiry-summary", response_model=OrderInquirySummary
)
async def order_inquiry_summary(
    project_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        return ProjectOrderInquiryService(db).summary(project_id)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/projects/{project_id}/order-inquiry-export")
async def export_order_inquiry(
    project_id: str,
    query: Optional[str] = Query(None),
    verb: Optional[List[str]] = Query(None),
    state: Optional[List[str]] = Query(None),
    sales_order_id: Optional[str] = Query(None),
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """The same rows, as the spreadsheet purchasing already reads (AC-I5).

    Generated per request, exactly as the AutoCount import file is: a stored copy goes
    stale the moment an amendment publishes, and a stale instruction is the thing being
    emailed around today.
    """
    try:
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        filename, body = ProjectOrderInquiryService(db).export_xlsx(
            project_id, query=query, verb=verb, state=state, pso_id=sales_order_id
        )
        return Response(
            content=body,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/sales-orders/{pso_id}/order-inquiry", response_model=OrderInquiryDetail)
async def get_sales_order_inquiry(
    pso_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """What purchasing was told when this sales order published."""
    try:
        validate_uuid_path(pso_id, resource="Sales order")
        body = ProjectOrderInquiryService(db).get_for_sales_order(pso_id)
        if body is None:
            raise AppException(
                status_code=404,
                message=(
                    "No order inquiry has been raised for this sales order. One is "
                    "derived the moment it publishes."
                ),
                code="order_inquiry_not_raised",
            )
        return body
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/order-inquiry-rows/mark", response_model=List[OrderInquiryRowOut])
async def mark_order_inquiry_rows(
    payload: MarkInquiryRowsRequest,
    current_user: dict = Depends(require_permission(ACTION)),
    db: Session = Depends(get_db),
):
    """Purchasing records what happened to one row or to a selection of them (AC-I7)."""
    try:
        for row_id in payload.row_ids:
            validate_uuid_path(row_id, resource="Order inquiry row")
        body = ProjectOrderInquiryService(db).mark_rows(
            payload.row_ids, state=payload.state, actor_user_id=current_user["id"]
        )
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/order-inquiry-rows/{row_id}/po-candidates",
    response_model=List[OrderInquiryPoCandidate],
)
async def order_inquiry_po_candidates(
    row_id: str,
    _user: dict = Depends(require_permission_with_api_key(ACTION)),
    db: Session = Depends(get_db),
):
    """Open PO lines this row could be tagged to (section G), soonest first."""
    try:
        validate_uuid_path(row_id, resource="Order inquiry row")
        return ProjectOrderInquiryService(db).po_candidates_for_row(row_id)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/order-inquiry-rows/{row_id}/place-on-po", response_model=OrderInquiryRowOut
)
async def place_order_inquiry_row_on_po(
    row_id: str,
    payload: PlaceOnPoRequest,
    current_user: dict = Depends(require_permission(ACTION)),
    db: Session = Depends(get_db),
):
    """Tag a raised row to one outstanding PO line - "the quantity to be ordered is
    deducted" (the captain, section G)."""
    try:
        validate_uuid_path(row_id, resource="Order inquiry row")
        validate_uuid_path(payload.po_line_id, resource="Purchase order line")
        body = ProjectOrderInquiryService(db).place_on_po(
            row_id, payload.po_line_id, actor_user_id=current_user["id"]
        )
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/order-inquiry-rows/{row_id}/unplace", response_model=OrderInquiryRowOut
)
async def unplace_order_inquiry_row(
    row_id: str,
    current_user: dict = Depends(require_permission(ACTION)),
    db: Session = Depends(get_db),
):
    """Untag: the row goes back to raised and the reorder engine sees it again."""
    try:
        validate_uuid_path(row_id, resource="Order inquiry row")
        body = ProjectOrderInquiryService(db).unplace(
            row_id, actor_user_id=current_user["id"]
        )
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
