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

import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.download import DownloadResponse
from app.services.download_service import DownloadService
from app.services.error_handler import AppException
from app.services.uuid_path_param import validate_uuid_path
from app.schemas.scm_order_summary import (
    KeyedStatusIn,
    KeyedStatusOut,
    OrderSummaryDecisionIn,
    OrderSummaryDecisionOut,
    OrderSummaryDemandDrillOut,
    OrderSummaryExportIn,
    OrderSummaryLocationsOut,
    OrderSummaryReportOut,
    OrderSummarySuppliersOut,
    PoWorklistOut,
)
from app.services.scm import reorder_run_service
from app.services.scm import summary_order_service as svc

log = logging.getLogger(__name__)

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")
_RUN = require_permission_with_api_key("scm.reorder.run")
# Security S4 (review fix round A, A4): a WRITE endpoint - it creates a `user_downloads`
# row and enqueues a background render - is never reachable by `X-API-Key` alone. Same
# permission slug as `_VIEW` (exporting states nothing new, it only prints what the
# report already answers), but the real-signed-in-user dependency: `app/dependencies.py`'s
# own rule for anything that writes.
_EXPORT = require_permission("scm.dashboard.view")


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


def _ddmmyyyy_compact(iso: Optional[str]) -> str:
    """`2026-09-10` -> `10092026`, for a FILENAME (no separators). Falls back to today
    when the run froze no rows (`report()`'s own `as_of` is then None) - the row itself
    still needs a name, and today is the only date anyone has to stamp on it."""
    from datetime import date as _date, datetime as _datetime

    if not iso:
        return _date.today().strftime("%d%m%Y")
    try:
        return _datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%d%m%Y")
    except ValueError:
        return _date.today().strftime("%d%m%Y")


@router.post("/order-summary/export", response_model=DownloadResponse)
def export_order_summary(
    payload: OrderSummaryExportIn = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(_EXPORT),
):
    """Queue the order sheet through My Downloads (S4, G6 ruling 9 Sep 2026 - "our export
    of the excel and pdf needs to use My Downloads process, similar to other downloading
    buttons"). Same permission as the grid it prints (``scm.dashboard.view``): exporting
    states nothing new, it only prints what the report already answers.

    AC-16: every guard - format, a malformed run id, an absent/invisible run, too many
    rows to order - runs SYNCHRONOUSLY here, before any ``user_downloads`` row exists, so
    a rejected request never leaves a row behind for the drawer to show. L1/L2 (Phase 3
    security review, carried over from the old GET): a named ``run_id`` is validated as a
    UUID (404 on a malformed one, the same non-committal answer a genuinely-absent run
    gets) and its visibility is checked with the SAME gate every other run-scoped route
    uses, before the report is ever read.
    """
    fmt = (payload.format or "").strip().lower()
    if fmt not in ("pdf", "xlsx"):
        raise AppException(status_code=422, message="format must be pdf or xlsx.")
    run_id = payload.run_id
    if run_id:
        run_id = validate_uuid_path(run_id, resource="Reorder run")
        reorder_run_service.assert_run_visible(db, run_id)

    # A COUNT/MAX over `scm.order_summary_row`, not a full `report()` render on the
    # request thread (reviewer nit, review fix round A, A5) - the row-count guard (M1,
    # Phase 3 security review) and the sheet's own `as_of` - which names the file - come
    # off one lightweight query rather than serialising every row just to maybe refuse.
    stats = svc.export_guard_stats(db, run_id=run_id)
    if stats["row_count"] > svc.MAX_EXPORT_ROWS:
        raise AppException(422, "Narrow the plan first")

    filename = f"order-sheet-{_ddmmyyyy_compact(stats['as_of'])}.{fmt}"
    download = DownloadService(db).create(
        user_id=str(current_user["id"]),
        kind=f"order_sheet_{fmt}",
        source_entity_type="reorder_run",
        source_entity_id=stats["run_id"],
        filename=filename,
    )
    try:
        from app.services.queue_service import enqueue_job
        from app.tasks.export_tasks import generate_order_sheet

        enqueue_job(
            generate_order_sheet,
            str(download.id),
            stats["run_id"],
            fmt,
            str(current_user["id"]),
            queue_name="imports",
            job_timeout=600,
        )
    except Exception as e:
        DownloadService(db).mark_failed(
            str(download.id), f"Could not queue order sheet generation: {e}"
        )
        raise AppException(
            status_code=503,
            message="Could not queue order sheet generation. Please try again.",
        )

    return DownloadResponse.model_validate(DownloadService(db).get(str(download.id)))


@router.get(
    "/order-summary/{product_code}/demand", response_model=OrderSummaryDemandDrillOut
)
def get_order_summary_demand(
    product_code: str,
    kind: str = Query(
        ...,
        description=(
            "project, retail or unclassified. `dealer` is accepted as the legacy name of "
            "retail."
        ),
    ),
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
    "/order-summary/{product_code}/locations", response_model=OrderSummaryLocationsOut
)
def get_order_summary_locations(
    product_code: str,
    run_id: Optional[str] = Query(
        None,
        description=(
            "Which plan's frozen locations to read. Omitted means the newest completed "
            "plan. Opaque, and never rendered."
        ),
    ),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The member locations behind one product row (AC-F08).

    Everything comes off the row's FROZEN basis, so the drill can only ever reconcile with
    the figure it opened. Demand is split by channel; stock, incoming SPO, the PO book and
    the reorder level are single shared facts of the product-location and appear once
    (AC-F07). The chosen quantity's split back to locations sums exactly to it (AC-F12).
    """
    return svc.locations(db, product_code, run_id=run_id)


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

    Two refusals, and they are different statuses because they are fixed in different
    places: 422 `chosen_qty_precision` when the quantity carries more fractional digits
    than the row's frozen `uom_decimal_places` allows (retype it coarser), and 409 when the
    run is decided at the other grain or predates the contract (decide where the run says,
    or create a new plan).
    """
    return svc.record_decision(
        db,
        product_code,
        run_id=payload.run_id,
        chosen_qty=payload.chosen_qty,
        supplier_code=payload.supplier_code,
        actor=_actor(_user),
    )


# =========================================================================== #
# S4 - the PO creation worklist (UAC Group E2)
# =========================================================================== #


@router.get("/po-worklist", response_model=PoWorklistOut)
def get_po_worklist(
    run_id: Optional[str] = Query(
        None,
        description=(
            "Which plan's decisions to work. Omitted means the newest completed plan. "
            "Opaque, and never rendered."
        ),
    ),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """What Mr Loo decided, ready to be keyed (AC-E2.1).

    Joey executes; she does not decide. There is no accept, reject or quantity route here -
    a second decision point would let the two screens disagree about what was ordered.

    The SERVER sorts, worst first: late rows, then by place-by date with nulls last. A
    client free to re-sort could disagree with the late flag beside the row.
    """
    return svc.po_worklist(db, run_id=run_id)


@router.post("/po-worklist/{product_code}/keyed-status", response_model=KeyedStatusOut)
def post_keyed_status(
    product_code: str,
    payload: KeyedStatusIn = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    """Record that a purchase order has been keyed into AutoCount, or un-record it.

    Manual because nothing can detect it: no integration exists (AC-E2.2). Gated on the
    same permission as the decision itself - somebody who may run and decide a plan is who
    keys its orders.
    """
    return svc.set_keyed_status(
        db,
        product_code,
        run_id=payload.run_id,
        keyed_status=payload.keyed_status,
        actor=_actor(_user),
        warehouse_code=payload.warehouse_code,
    )
