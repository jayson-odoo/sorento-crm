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
from app.schemas.project_board import PileQueue, PlanningBoard, StockDetail
from app.schemas.project_so_reconciliation import (
    AdoptSalesOrderBody,
    AdoptSalesOrderResult,
    FulfilmentPlanningRow,
    ReconciliationSummary,
)
from app.schemas.project_supply import (
    ClassificationEvidence,
    ConfirmManyBody,
    ConfirmManyResult,
    ConfirmResult,
    ConfirmSupplyBody,
    PlanRow,
    SupplyProposal,
)
from app.services import project_service as projects
from app.services.error_handler import AppException, handle_internal_error
from app.services.project_classification_evidence import classification_evidence
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
            "One box. Matches the sales-order number, the customer name, the project "
            "label, or a PRODUCT (item code or name) on any of the order's outstanding "
            "lines. Also the provisional ref, AutoCount doc no and area group of an "
            "authored record."
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


@router.get("/plans", response_model=ListResponse[PlanRow])
def list_plans(
    query: Optional[str] = Query(
        None,
        description="Matches the sales-order number, the customer name, or the agent code.",
    ),
    state: Optional[Literal["active", "superseded", "challenged"]] = Query(
        None, description="Defaults to active - what is stored NOW."
    ),
    agent_code: Optional[str] = Query(None, description="One agent's code, exact match."),
    sort: Optional[
        Literal["so_number", "customer_name", "agent_code", "revision_no", "state", "decided_at"]
    ] = Query(None, description="Defaults to decided_at, most recent first."),
    direction: Optional[Literal["asc", "desc"]] = Query("desc", alias="dir"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """The Plans page (PLAN-demo-followups-19aug-ladder-v2 D1): "is the plan stored, how do
    I review it" - every supply decision, one row per revision, cross-order.

    A pure read over `so_supply_decisions`. `state` defaults to `active`: the question is
    about what is committed NOW, not the whole history a line's decision has ever carried,
    though `superseded` and `challenged` stay a click away.

    Plain ``def``, so FastAPI runs it in a threadpool: it is synchronous SQLAlchemy over a
    page of decisions.
    """
    try:
        result = ProjectSupplyService(db).list_decisions(
            query=query,
            state=state,
            agent_code=agent_code,
            sort=sort,
            dir=direction or "desc",
            page=page,
            limit=limit,
        )
        return {"data": result["data"], "pagination": result["pagination"]}
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


@router.post("/fulfilment-planning/confirm-all", response_model=ConfirmManyResult)
def confirm_all(
    payload: ConfirmManyBody,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """"Confirm all approved" (D3): every order's Confirm, each its OWN transaction.

    The board's Approve all composes a verdict per line across up to fifty orders; this posts
    the SAME per-order write `POST .../sales-orders/{pso_id}/confirm` already does, once per
    order named in `orders`, rather than one call per order from the panel. One order's own
    refusal (a stale line, a line somebody else confirmed a moment earlier) never takes the
    orders around it down: each entry commits or rolls back on its own, and every order named
    in the body gets a result - there is no silent partial success. `orders: []` answers with
    an empty result rather than a refusal; a board with nothing approved yet is not an error.
    """
    try:
        if not payload.orders:
            return {"results": []}
        results = ProjectSupplyService(db).confirm_many(
            payload.orders,
            actor_user_id=current_user["id"],
            assert_can_act=lambda session, order: _assert_can_act_on(
                session, order, current_user
            ),
        )
        return {"results": results}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/fulfilment-planning/stock-detail", response_model=StockDetail)
def get_stock_detail(
    product_id: str = Query(..., description="Addressing only; the board's cell carries it."),
    warehouse_id: str = Query(...),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """One product at one location: On Hand, SO Qty, SPO Qty, Available, and the documents.

    AutoCount's Stock Status with Detail, which is the screen the planner checks stock on and
    the one they asked the board's cell strip to justify itself against. A pure read.

    Plain ``def``, so FastAPI runs it in a threadpool: it is synchronous SQLAlchemy over one
    product-location's outstanding book.
    """
    try:
        validate_uuid_path(product_id, resource="Product")
        validate_uuid_path(warehouse_id, resource="Warehouse")
        return FulfilmentBoardService(db).stock_detail(product_id, warehouse_id)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/fulfilment-planning/queue", response_model=PileQueue)
def get_pile_queue(
    product_id: str = Query(..., description="Addressing only; the board's cell carries it."),
    warehouse_id: str = Query(...),
    line_id: Optional[str] = Query(
        None,
        description=(
            "The CORE sales-order line asking. Its row is marked, its position is stated, and "
            "every line in front of it says which factor put it there. Omitted reads the queue "
            "on nobody's behalf."
        ),
    ),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """Who is standing in front of this line at its pile, in the order the stock is served.

    The same queue the trail counted (`_pile_book`), read out in full with each line's rank and
    the facts behind it. A pure read.

    Plain ``def``, so FastAPI runs it in a threadpool: it is synchronous SQLAlchemy over one
    product-location's outstanding book, the widest of which on the live data is 289 lines.
    """
    try:
        validate_uuid_path(product_id, resource="Product")
        validate_uuid_path(warehouse_id, resource="Warehouse")
        if line_id:
            validate_uuid_path(line_id, resource="Sales order line")
        return FulfilmentBoardService(db).pile_queue(product_id, warehouse_id, line_id)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/fulfilment-planning/classification", response_model=ClassificationEvidence
)
def get_classification_evidence(
    product_id: str = Query(..., description="Addressing only; the board's chip carries it."),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """The Proof button: the ranked evidence behind one product's hot/cold verdict.

    The captain, reading the trail: "don't give me jargon like abc classification, just tell
    me hot selling or cold selling, at project or retail, with some button for me to view
    detail as a proof". This is that detail - which location, delivered how much, ranked
    where out of how many, and what share of the class that is - read live over the same
    rows the board's own hot-selling predicate reads. A pure read.

    Plain ``def``, so FastAPI runs it in a threadpool: it is synchronous SQLAlchemy over one
    product's classification rows.
    """
    try:
        validate_uuid_path(product_id, resource="Product")
        return classification_evidence(db, product_id)
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
        if payload.batch_id:
            body = _confirm_a_planning_change(db, order, payload, current_user["id"])
        else:
            body = service.confirm(order, payload, actor_user_id=current_user["id"])
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


def _confirm_a_planning_change(db, order, payload, actor_user_id: str) -> dict:
    """The board's Confirm, pressed on a board opened at `?batch=<id>` (part 3, AC-P3-4).

    ONE press, ONE call, ONE revision: the lines the planner composed become the batch
    rows' own compositions, and the batch is applied - which is what writes the revision,
    cancels the closed lines' rows, shifts their links and updates the surviving row in
    place. Confirming the batch through some second endpoint would have meant two writes
    and two chances for one of them to be the only one that landed.

    A line the press decided that the batch does NOT carry still goes in, as an ordinary
    confirmation beside the batch's rows: the planner pressed one button and is entitled
    to have it mean what the screen said.

    **THIS ORDER, AND NO OTHER.** A book upload moves many orders at once and the board
    presses Confirm per order, so the apply is narrowed to this one (`only_pso_ids`).
    Applying the whole batch off one press wrote revisions for orders nobody had
    confirmed, skipped the per-order permission check `_assert_can_act_on` gives this one,
    and stamped `applied_at`, which locked every remaining order's rows.

    A second press is REFUSED (409), not answered with the first press's revision number.
    """
    from app.models.planning_change import PlanningChangeRow
    from app.services import planning_change_service
    from app.services.planning_change_service import PLANNING_CHANGE_STATE_APPLIED
    from app.services.project_supply_service import SupplyLinesRefused

    batch_id = payload.batch_id
    validate_uuid_path(batch_id, resource="Planning change batch")
    rows = (
        db.query(PlanningChangeRow)
        .filter(
            PlanningChangeRow.batch_id == batch_id,
            PlanningChangeRow.project_sales_order_id == str(order.id),
        )
        .all()
    )
    if rows and all(r.applied_state == PLANNING_CHANGE_STATE_APPLIED for r in rows):
        # This ORDER is done even though the batch as a whole may not be: another order of
        # the same upload can still be waiting, so `applied_at` is not the thing to read.
        raise AppException(
            status_code=409,
            message="This planning change was already applied to this sales order.",
            code="planning_change_batch_applied",
        )
    by_line = {str(row.project_line_id): row for row in rows if row.project_line_id}

    extra: list[dict] = []
    for line in payload.lines:
        composition = line.model_dump()
        row = by_line.get(str(line.project_line_id))
        if row is None:
            extra.append(composition)
            continue
        if row.suggested in ("release", "retire"):
            # Approving one of these on the board means "yes, do what the book did" - it
            # is not an amendment of the line's supply. Posting it as an `amend` sent it
            # down the confirm branch instead, so the RELEASE rule (AC-P3-10) and the
            # retire-and-shift never fired from the board at all. The row already carries
            # `accept` from `build_batch`, and the board offers no way to change it.
            continue
        planning_change_service.set_row_decision(
            db, batch_id, str(row.id), "amend", composition
        )

    result = planning_change_service.apply(
        db,
        batch_id,
        actor_user_id,
        extra_confirm_lines={str(order.id): extra},
        refuse_if_applied=True,
        only_pso_ids={str(order.id)},
    )
    failed = [
        entry for entry in result["failed_orders"]
        if entry.get("so_number")
    ]
    outcome = (result.get("outcomes") or {}).get(str(order.id))
    confirmed = (outcome or {}).get("confirm_result")
    if confirmed is None:
        message = (
            failed[0]["reason"]
            if failed
            else "Nothing on this planning change could be confirmed."
        )
        # WHICH line, and why. An ordinary Confirm answers with `failing_lines` beside the
        # sentence and the sheet marks the row; the batch path dropped them, so the same
        # refusal read as "1 line cannot be confirmed" with nothing to act on.
        failing_lines = failed[0].get("failing_lines") if failed else None
        if failing_lines:
            raise SupplyLinesRefused(
                status_code=422,
                message=message,
                failing_lines=failing_lines,
                code="planning_change_not_confirmed",
            )
        raise AppException(
            status_code=422,
            message=message,
            code="planning_change_not_confirmed",
        )
    return confirmed


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
