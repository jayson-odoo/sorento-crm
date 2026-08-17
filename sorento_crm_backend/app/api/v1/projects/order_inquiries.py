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
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.project_order_inquiry import (
    MarkInquiryRowsRequest,
    OrderInquiryDetail,
    OrderInquiryRowOut,
    OrderInquirySummary,
)
from app.services import project_service as projects
from app.services.error_handler import AppException, handle_internal_error
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.uuid_path_param import validate_uuid_path

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW = "projects.projects.view"
ACTION = "projects.order_inquiry.action"


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
