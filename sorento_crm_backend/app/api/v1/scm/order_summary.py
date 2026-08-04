"""SCM S3b - the Summary Order Report endpoints (UAC Groups C2, C3).

Four routes, mounted flat alongside the other SCM routes (no nested ``reorder/`` segment,
because nothing else in the domain has one):

* ``GET  /order-summary``                                 the frozen report for a run
* ``GET  /order-summary/{product_code}/demand?kind=``     the lines behind one aggregate
* ``GET  /order-summary/{product_code}/suppliers``        the candidates for one product
* ``POST /order-summary/{product_code}/decision``         record the order quantity

The three reads are gated on ``scm.dashboard.view``, mirroring ``explainer.py`` and
``coverage.py``. The write is gated on ``scm.reorder.run``, mirroring ``decisions.py`` - the
same permission that lets somebody run a plan is the one that lets them decide on it.

**Addressed by human codes.** No UUID may reach the UI, so the path parameter is a product
code and every reference in the response is a code, a number or a name. ``run_id`` is the one
opaque value on the wire: it says which week's report is being read (AC-C2.9) and the screen
never renders it.

**``decided_by`` is a NAME, not a user id.** The sibling decision routes pass the caller's id
straight through as the actor, which is right for their internal audit fields but wrong here:
this value is rendered beside the quantity on a report a planner reads, so it is resolved to
the caller's name and the id never leaves the server.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_order_summary import (
    OrderSummaryDecisionIn,
    OrderSummaryDecisionOut,
    OrderSummaryDemandDrillOut,
    OrderSummaryReportOut,
    OrderSummarySuppliersOut,
)
from app.services.scm import summary_order_service as svc

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")
_RUN = require_permission_with_api_key("scm.reorder.run")


def _actor(user: Optional[dict]) -> Optional[str]:
    """The caller's human name, never their id.

    Falls back to the email and then to None. None is honest - the service stamps "unknown"
    rather than an id, because an id rendered beside a decision is a UUID on a planner's
    screen, which is the rule this module is not allowed to break even for provenance.
    """
    user = user or {}
    return user.get("name") or user.get("email") or None


@router.get("/order-summary", response_model=OrderSummaryReportOut)
def get_order_summary(
    run_id: Optional[str] = Query(
        None,
        description=(
            "Which plan's report to read. Omitted means the newest completed plan. Opaque: "
            "it identifies the week, and is never rendered."
        ),
    ),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The frozen report, whole.

    Returned whole and paginated by the client, because the sheet it replaces is read as one
    book. There is no ``as_of`` parameter: the report STATES the date it was frozen for, and
    letting a caller pass a different one would label a frozen position with a date it does
    not describe. To read another week, name its run.
    """
    return svc.report(db, run_id=run_id)


@router.get(
    "/order-summary/{product_code}/demand", response_model=OrderSummaryDemandDrillOut
)
def get_order_summary_demand(
    product_code: str,
    kind: str = Query(..., description="project or dealer"),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The lines behind one aggregate, fetched lazily when its icon is opened (AC-C2.2a).

    Lazy because the list carries only what is needed to decide: preventing information
    fatigue is a requirement, not a preference. The SERVER sorts (dealer worst-first by
    ageing, project by required date), so the ageing a person reads is the ageing the server
    computed.
    """
    return svc.demand_drill(db, product_code, kind=kind)


@router.get(
    "/order-summary/{product_code}/suppliers", response_model=OrderSummarySuppliersOut
)
def get_order_summary_suppliers(
    product_code: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Every supplier the item could be bought from, with cost beside on-time and lead time.

    Cost alone cannot answer whether to change supplier (AC-C3.5), so the performance figures
    travel with every candidate rather than living on another screen.
    """
    return svc.suppliers_for(db, product_code)


@router.post(
    "/order-summary/{product_code}/decision", response_model=OrderSummaryDecisionOut
)
def post_order_summary_decision(
    product_code: str,
    payload: OrderSummaryDecisionIn = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    """Record what a person decided to order.

    A quantity above the shortfall is valid and is not a warning state (AC-C2.7); the engine's
    figure stays beside it with the actor and the time, so a larger number is a decision on the
    record rather than an untraceable override (AC-C2.8).
    """
    return svc.record_decision(
        db,
        product_code,
        run_id=payload.run_id,
        chosen_qty=payload.chosen_qty,
        supplier_code=payload.supplier_code,
        actor=_actor(_user),
    )
