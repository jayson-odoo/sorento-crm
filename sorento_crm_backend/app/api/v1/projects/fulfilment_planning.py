"""Fulfilment Planning: the AutoCount reconciliation worklist and one order's mapping.

Contract: `documentation/plans/scm/STAGE1B-scm-front-planning-reconciliation.md` section 3.

Three routes, mounted on the same `/project-sales` root as the sales-order ones because
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
from app.services import project_service as projects
from app.services.error_handler import handle_internal_error
from app.services.project_so_draft_service import ProjectSODraftService
from app.services.project_so_reconciliation_service import (
    ProjectSOReconciliationService,
)
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
        Literal["awaiting_reconciliation", "needs_cs_review"]
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
