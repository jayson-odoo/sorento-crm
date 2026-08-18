"""Fulfilment Planning: the reconciliation worklist, the supply sheet, the confirmation.

Contract: `documentation/plans/scm/STAGE1B-scm-front-planning-reconciliation.md` section 3
and `STAGE1C-scm-front-planning-promising.md` section 6.

Five routes, mounted on the same `/project-sales` root as the sales-order ones because
they are addressed the same two ways: a cross-project worklist, and one order by id.

Rights follow the rest of the module: reads take `projects.projects.view`, and the re-run
takes `projects.projects.edit` on that project, checked in `project_service` like every
other project write. The re-run is a WRITE (it persists the links it can prove and clears
the ones that went stale), so it is `require_permission`, not the API-key variant.

Mounted BEFORE `sales_orders.router` for the same reason `divergences` is: these paths hang
off `/sales-orders/{pso_id}`, and keeping every declaration of that prefix ahead of the
plain `/sales-orders/{pso_id}` one removes any question of shadowing.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.project_so_reconciliation import (
    FulfilmentPlanningRow,
    ReconciliationSummary,
)
from app.schemas.project_supply import ConfirmResult, ConfirmSupplyBody, SupplyProposal
from app.services import project_service as projects
from app.services.error_handler import handle_internal_error
from app.services.project_so_draft_service import ProjectSODraftService
from app.services.project_so_reconciliation_service import (
    ProjectSOReconciliationService,
)
from app.services.project_supply_service import ProjectSupplyService
from app.services.uuid_path_param import validate_uuid_path

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"


@router.get("/fulfilment-planning", response_model=ListResponse[FulfilmentPlanningRow])
def list_fulfilment_planning(
    query: Optional[str] = Query(
        None,
        description=(
            "Matches provisional ref, AutoCount doc no, area group, project code, "
            "project title or customer name"
        ),
    ),
    # A closed set, so an unknown value is a 422 rather than a 200 with an empty list:
    # the state is derived, and a filter nothing can equal reads on screen as "no work
    # to do" when the truth is "that is not a state".
    review_state: Optional[
        Literal["awaiting_reconciliation", "needs_cs_review", "confirmed"]
    ] = Query(None),
    project_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """Every published or amended Project SO, with its one whole-SO review state (J03).

    Plain ``def``, so FastAPI runs the whole handler in a threadpool: the mapping is
    synchronous SQLAlchemy over a page of orders, and on the event loop it holds up every
    other request the worker is serving.
    """
    try:
        if project_id:
            validate_uuid_path(project_id, resource="Project")
        return ProjectSOReconciliationService(db).list_fulfilment_planning(
            query=query,
            review_state=review_state,
            project_id=project_id,
            page=page,
            limit=limit,
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/sales-orders/{pso_id}/reconciliation", response_model=ReconciliationSummary
)
def get_reconciliation(
    pso_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """What the mapping makes of this order right now. A pure read: it writes nothing."""
    try:
        validate_uuid_path(pso_id, resource="Sales order")
        order = ProjectSODraftService(db).get_order(pso_id)
        return ProjectSOReconciliationService(db).evaluate(order)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/sales-orders/{pso_id}/supply", response_model=SupplyProposal)
def get_supply_proposal(
    pso_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """The Supply composition section: what covers each line, and why (J04).

    It writes at most one thing, and only ever the same thing: an active revision whose
    frozen facts no longer match the live ones is flipped to `challenged` here, because a
    sheet that reads Confirmed against quantities that have moved is a promise nobody can
    keep. Committed on the way out for that reason.
    """
    try:
        validate_uuid_path(pso_id, resource="Sales order")
        service = ProjectSupplyService(db)
        order = service.get_order(pso_id)
        body = service.proposal_for(order)
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/sales-orders/{pso_id}/confirm", response_model=ConfirmResult)
def confirm_supply(
    pso_id: str,
    payload: ConfirmSupplyBody,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Confirm the whole Project SO in one action (AC-C01).

    Every line commits together or none of them does: the service rechecks each line
    against authoritative facts, and one stale, unbalanced or unmapped line refuses the
    lot with `failing_lines` naming each by line number and item code. The Order Inquiry
    handoff runs inside this same transaction, so purchasing can never be told to buy
    something that was not also promised.
    """
    try:
        validate_uuid_path(pso_id, resource="Sales order")
        service = ProjectSupplyService(db)
        order = service.get_order(pso_id)
        project = projects.get_project_or_404(db, order.project_id)
        projects.assert_can_edit_project(
            db, project, current_user["id"], permission_slugs(db, current_user["id"])
        )
        body = service.confirm(order, payload, actor_user_id=current_user["id"])
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/sales-orders/{pso_id}/reconcile", response_model=ReconciliationSummary)
def rerun_reconciliation(
    pso_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Re-run after CS has answered whatever was in the way.

    Idempotent, so the button is safe to press on an order that is already clean: the same
    links are kept, the same summary comes back.
    """
    try:
        validate_uuid_path(pso_id, resource="Sales order")
        order = ProjectSODraftService(db).get_order(pso_id)
        project = projects.get_project_or_404(db, order.project_id)
        projects.assert_can_edit_project(
            db, project, current_user["id"], permission_slugs(db, current_user["id"])
        )
        body = ProjectSOReconciliationService(db).reconcile(order)
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
