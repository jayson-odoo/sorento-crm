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
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.project_board import PlanningBoard
from app.schemas.project_so_reconciliation import (
    AdoptSalesOrderBody,
    AdoptSalesOrderResult,
    FulfilmentPlanningRow,
    ReconciliationSummary,
)
from app.schemas.project_supply import ConfirmResult, ConfirmSupplyBody, SupplyProposal
from app.services import project_service as projects
from app.services.error_handler import handle_internal_error
from app.services.project_fulfilment_board_service import FulfilmentBoardService
from app.services.project_so_adoption_service import ProjectSOAdoptionService
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


def _assert_can_act_on(db: Session, order, current_user: dict) -> None:
    """Write authorisation for one planning record, whether or not it has a project.

    `assert_can_edit_project` cannot run without a project, and an order adopted from the
    AutoCount book has none by design (`PLAN-fulfilment-planning-from-autocount-so.md`
    section 2, "Authorisation with no project"): the module permission on the route is then
    the whole gate, and the per-project check is kept for records that DO have a project.
    Passing `order.project_id` straight to `get_project_or_404` answered 404 "Project not
    found" for every adopted order, which took Confirm and Re-sync - the last steps of the
    journey - off the screen entirely. Company scope is enforced by the mixin either way.
    """
    if not order.project_id:
        return
    project = projects.get_project_or_404(db, order.project_id)
    projects.assert_can_edit_project(
        db, project, current_user["id"], permission_slugs(db, current_user["id"])
    )


@router.get("/fulfilment-planning", response_model=ListResponse[FulfilmentPlanningRow])
def list_fulfilment_planning(
    query: Optional[str] = Query(
        None,
        description=(
            "Matches the sales-order number, customer name, the Order Inquiry project "
            "string, provisional ref, AutoCount doc no, area group, project code or "
            "project title"
        ),
    ),
    # A closed set, so an unknown value is a 422 rather than a 200 with an empty list:
    # the state is derived, and a filter nothing can equal reads on screen as "no work
    # to do" when the truth is "that is not a state". `not_started` is the fourth value
    # (AC-FP05) and means "an outstanding core sales order nobody has planned".
    review_state: Optional[
        Literal[
            "not_started", "awaiting_reconciliation", "needs_cs_review", "confirmed"
        ]
    ] = Query(None),
    project_id: Optional[str] = Query(None),
    sales_order_id: Optional[str] = Query(
        None, description="Narrow to one core sales order. Addressing only."
    ),
    # `sort` + `dir` are the names `buildDataGridParams` sends, unchanged. The set is
    # CLOSED for the same reason `review_state` is: a grid drawing a sort arrow on a column
    # the server quietly ignored is a screen lying about what it is showing. It must equal
    # `SORTABLE_FIELDS` in the service - FastAPI cannot build a `Literal` from a runtime
    # set, so a test asserts the two agree.
    sort: Optional[
        Literal[
            "so_number",
            "customer_name",
            "project_label",
            "earliest_required_date",
            "outstanding_qty",
            "line_count",
            "review_state",
            "provisional_ref",
            "po_number",
            "area_group",
            "updated_at",
        ]
    ] = Query(None, description="Defaults to earliest_required_date. Nulls always last."),
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
    """Everything that needs planning, one row per subject (AC-FP01 to AC-FP06).

    A union of the outstanding project-class sales-order book and the planning records
    authored here that it does not already carry, ordered by the earliest still-owed
    required date because that is the order the work is due in.

    Plain ``def``, so FastAPI runs the whole handler in a threadpool: the mapping is
    synchronous SQLAlchemy over a page of orders, and on the event loop it holds up every
    other request the worker is serving.
    """
    try:
        if project_id:
            validate_uuid_path(project_id, resource="Project")
        if sales_order_id:
            validate_uuid_path(sales_order_id, resource="Sales order")
        return ProjectSOReconciliationService(db).list_fulfilment_planning(
            query=query,
            review_state=review_state,
            project_id=project_id,
            sales_order_id=sales_order_id,
            sort=sort,
            dir=direction,
            page=page,
            limit=limit,
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/fulfilment-planning/adopt", response_model=AdoptSalesOrderResult)
def adopt_sales_order(
    payload: AdoptSalesOrderBody,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Start planning: journey step 2, and the whole of it (AC-FP07).

    One decision - which order - and everything else is derived from the order itself: the
    lines, the products, the quantities, the required dates, the fulfilment locations and
    the customer. No project to choose, no reference to invent, no confirmation dialog,
    because it destroys nothing and it repeats safely (AC-FP08): a second press, a retry or
    a second CS answers with the record that already exists.

    Gated on the module permission alone, with no `assert_can_edit_project`: an adopted
    record has no project for that check to run against (plan section 2, an accepted
    narrowing rather than an oversight). No new permission is introduced (AC-FP26).
    """
    try:
        body = ProjectSOAdoptionService(db).adopt(
            payload.sales_order_id, actor_user_id=current_user["id"]
        )
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/fulfilment-planning/board", response_model=PlanningBoard)
def get_planning_board(
    orders: str = Query(
        ...,
        description=(
            "Comma-separated sales-order NUMBERS, never ids, so a board can be linked to "
            "and reloaded. At most 50 (PLAN 13.2)."
        ),
    ),
    granularity: Literal["day", "week", "month"] = Query("week"),
    day_window: Optional[date] = Query(
        None,
        description=(
            "First day of the day-granularity window. Defaults to the earliest still-future "
            "date owed. A DISPLAY bound only: nothing is filtered out of the plan by it."
        ),
    ),
    preview_policy: Optional[str] = Query(
        None,
        description=(
            "Rank by a NAMED alternative policy instead of the live one, without activating "
            "it. '1' or 'true' means the module's own board preview. Read-only: a previewed "
            "ranking is labelled and may never be committed against."
        ),
    ),
    as_of: Optional[date] = Query(
        None, description="Build the board against this date instead of today."
    ),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """Several sales orders at once: dates across, products down, one pile per location.

    A pure read (PLAN 13.4). The board writes no decision object of its own - the decision
    stays per sales order, atomic across the lines that order is committing - so opening it
    claims no stock and there is no board write endpoint to pair with this.

    Plain ``def`` so FastAPI runs it in a threadpool: it is synchronous SQLAlchemy over a
    selection of up to fifty orders, and on the event loop it would hold up every other
    request the worker is serving.
    """
    try:
        numbers = [part.strip() for part in (orders or "").split(",") if part.strip()]
        return FulfilmentBoardService(db).build(
            numbers,
            granularity=granularity,
            as_of=as_of,
            day_window_start=day_window,
            preview_policy=preview_policy,
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
    """Confirm the lines the planner has decided, in one action (AC-C01 as amended).

    Every line IN THIS CONFIRMATION commits together or none of them does: the service
    rechecks each against authoritative facts, and one stale, unbalanced or unmapped line
    refuses the lot with `failing_lines` naming each by line number and item code. A line
    the body does not name is left undecided on purpose (13.4) and keeps counting as
    demand; a body naming no line at all is refused. The Order Inquiry handoff runs inside
    this same transaction, so purchasing can never be told to buy something that was not
    also promised.
    """
    try:
        validate_uuid_path(pso_id, resource="Sales order")
        service = ProjectSupplyService(db)
        order = service.get_order(pso_id)
        _assert_can_act_on(db, order, current_user)
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
        _assert_can_act_on(db, order, current_user)
        body = ProjectSOReconciliationService(db).reconcile(order)
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
