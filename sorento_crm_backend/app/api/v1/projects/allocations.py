"""Allocation routes: ranked sources, the confirmed decision, cross-project claims (P9).

Routes mount at the module root rather than under `/projects/{project_id}` for the same
reason sales orders do: a line and a claim are listed under their order but addressed
directly by id.

Rights sit on the PROJECT, exactly as sales orders do. Two different projects decide two
different things here, which is the whole point of AC-H4:

- ``projects.projects.edit`` plus edit rights on the line's OWN project confirms a source
  and raises a claim.
- Answering a claim needs edit rights on the project HOLDING the stock. The asker cannot
  accept her own request, and that is checked in the service so the rule holds for any
  future caller.

Every refusal comes from the service. The routes translate, they do not decide.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.project_allocation import (
    AllocationCandidateList,
    AllocationClaimRequest,
    AllocationClaimRow,
    AllocationConfirmRequest,
    AllocationRefuseRequest,
    SalesOrderLineAllocationRow,
)
from app.services import project_service as projects
from app.services.error_handler import AppException, handle_internal_error
from app.services.project_allocation_service import ProjectAllocationService
from app.services.uuid_path_param import validate_uuid_path

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"


def _line_for_edit(db: Session, line_id: str, current_user: dict):
    """The line, its project, and the check that this person may source it."""
    validate_uuid_path(line_id, resource="Sales order line")
    service = ProjectAllocationService(db)
    line = service.get_line(line_id)
    project = service.project_of_line(line)
    projects.assert_can_edit_project(
        db, project, current_user["id"], permission_slugs(db, current_user["id"])
    )
    return service, line, project


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


# -------------------------------------------------------------------- the decision


@router.put(
    "/sales-order-lines/{line_id}/allocation",
    response_model=SalesOrderLineAllocationRow,
)
async def confirm_allocation(
    line_id: str,
    payload: AllocationConfirmRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Confirm or override the source for one line (AC-H3, AC-H5).

    409 when a source names more than the location holds free, or when it names stock held
    for another project with no accepted claim behind it.
    """
    try:
        service, line, project = _line_for_edit(db, line_id, current_user)
        body = service.confirm(
            line,
            project,
            [source.model_dump() for source in payload.sources],
            actor_user_id=current_user["id"],
        )
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete(
    "/sales-order-lines/{line_id}/allocation",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def clear_allocation(
    line_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Drop the decision and any request still waiting on it. Hard delete."""
    try:
        service, line, _project = _line_for_edit(db, line_id, current_user)
        service.clear(line)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ------------------------------------------------------------------------ claims


@router.post(
    "/sales-order-lines/{line_id}/allocation-claims",
    response_model=AllocationClaimRow,
    status_code=status.HTTP_201_CREATED,
)
async def raise_allocation_claim(
    line_id: str,
    payload: AllocationClaimRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Ask the holding project's CS for stock (AC-H4). Grants nothing until they answer."""
    try:
        service, line, project = _line_for_edit(db, line_id, current_user)
        validate_uuid_path(payload.warehouse_id, resource="Location")
        validate_uuid_path(payload.to_project_id, resource="Project")
        claim = service.raise_claim(
            line,
            project,
            warehouse_id=payload.warehouse_id,
            to_project_id=payload.to_project_id,
            qty=payload.qty,
            actor_user_id=current_user["id"],
        )
        body = service.serialize_claim(claim)
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
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


@router.post("/allocation-claims/{claim_id}/accept", response_model=AllocationClaimRow)
async def accept_allocation_claim(
    claim_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Release the stock. Only the holding project's CS may do it."""
    try:
        validate_uuid_path(claim_id, resource="Stock claim")
        service = ProjectAllocationService(db)
        claim = service.get_claim(claim_id)
        service.assert_can_answer(
            claim, current_user["id"], permission_slugs(db, current_user["id"])
        )
        service.accept_claim(claim, actor_user_id=current_user["id"])
        body = service.serialize_claim(claim)
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/allocation-claims/{claim_id}/refuse", response_model=AllocationClaimRow)
async def refuse_allocation_claim(
    claim_id: str,
    payload: AllocationRefuseRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Refuse WITH a reason. A refusal with none is rejected before it is written."""
    try:
        validate_uuid_path(claim_id, resource="Stock claim")
        service = ProjectAllocationService(db)
        claim = service.get_claim(claim_id)
        service.assert_can_answer(
            claim, current_user["id"], permission_slugs(db, current_user["id"])
        )
        service.refuse_claim(
            claim, reason=payload.reason, actor_user_id=current_user["id"]
        )
        body = service.serialize_claim(claim)
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
