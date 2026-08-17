"""Allocation READS: ranked sources, one order's components, the claims worklist (P9).

Everything here answers a question. Nothing here writes, because Stage 1C moved the
writing: a Project SO's supply is composed and committed in ONE atomic transaction
(`POST /project-sales/sales-orders/{pso_id}/confirm`, PLAN-scm-front-planning.md 3.1), so
per-line confirmation, clearing a line's decision, and the raise/accept/refuse claim
handshake are gone. A cross-project Borrow is written straight to `accepted` inside that
same transaction by the confirming CS actor (AC-B10), which is why nothing is left to
answer.

What is left is what the supply sheet and its audit read: the ranked candidates it offers
as Borrow sources, the components of an order's active decision, and the claims history.

Routes mount at the module root rather than under `/projects/{project_id}` for the same
reason sales orders do: a line and a claim are listed under their order but addressed
directly by id.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.project_allocation import (
    AllocationCandidateList,
    AllocationClaimRow,
    SalesOrderLineAllocationRow,
)
from app.services.error_handler import AppException, handle_internal_error
from app.services.project_allocation_service import ProjectAllocationService
from app.services.uuid_path_param import validate_uuid_path

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"


# --------------------------------------------------------------------- read side


@router.get(
    "/sales-orders/{pso_id}/allocations",
    response_model=ListResponse[SalesOrderLineAllocationRow],
)
async def list_sales_order_allocations(
    pso_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """Every line on the order and where it is coming from, sourced or not.

    Unsourced lines are included rather than filtered out: "which of the 99 still has no
    source" is the question this screen exists to answer.
    """
    try:
        validate_uuid_path(pso_id, resource="Sales order")
        service = ProjectAllocationService(db)
        service.get_order(pso_id)
        rows = service.list_for_order(pso_id)
        return {
            "data": rows,
            "pagination": {"total": len(rows), "page": 1, "limit": max(len(rows), 1)},
            "empty": not rows,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/sales-order-lines/{line_id}/allocation-candidates",
    response_model=AllocationCandidateList,
)
async def list_allocation_candidates(
    line_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """Ranked sources, computed live on every request and never stored (AC-H1, AC-H2)."""
    try:
        validate_uuid_path(line_id, resource="Sales order line")
        service = ProjectAllocationService(db)
        line = service.get_line(line_id)
        return service.serialize_candidates(line)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/allocation-claims", response_model=ListResponse[AllocationClaimRow])
async def list_allocation_claims(
    direction: str = Query(
        "incoming",
        description=(
            "incoming = waiting on projects this user works; outgoing = raised by them; "
            "all = both."
        ),
    ),
    state: Optional[List[str]] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """The worklist: who is waiting on an answer from this person, and what they asked."""
    try:
        if direction not in {"incoming", "outgoing", "all"}:
            raise AppException(
                status_code=422,
                message="Direction must be incoming, outgoing or all.",
                code="allocation_claims_direction",
            )
        service = ProjectAllocationService(db)
        rows, total = service.list_claims(
            user_id=current_user["id"],
            permissions=permission_slugs(db, current_user["id"]),
            direction=direction,
            state=state,
            page=page,
            limit=limit,
        )
        return {
            "data": rows,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
