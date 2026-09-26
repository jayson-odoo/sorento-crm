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
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.download import DownloadResponse
from app.schemas.export_split import ExportSplit
from app.services.download_service import DownloadService
from app.services.error_handler import AppException
from app.services.uuid_path_param import validate_uuid_path
from app.schemas.scm_order_summary import (
    KeyedStatusIn,
    KeyedStatusOut,
    LowStockViewOut,
    OrderSummaryDecisionIn,
    OrderSummaryDecisionOut,
    OrderSummaryDemandDrillOut,
    OrderSummaryExportIn,
    OrderSummaryLocationsOut,
    OrderSummaryReportOut,
    OrderSummarySuppliersOut,
    PoWorklistOut,
)
from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService
from app.services.scm import low_stock_report_service
from app.services.scm import reorder_run_service
from app.services.scm import summary_order_service as svc

log = logging.getLogger(__name__)

#: The third value `POST /order-summary/export` accepts, and the `user_downloads.kind` it
#: creates - one string, so the format on the wire and the kind in the drawer cannot drift
#: (PLAN-low-stock-report S3, AC-30).
LOW_STOCK_FORMAT = "low_stock_xlsx"

#: Lane C, PLAN-order-sheet-oi-reports-22sep.md (AC-C1/AC-C2): the fourth `format` value -
#: the OI worksheet, a run's OWN Start Plan scope of live OI Buy rows (`kind` on the wire
#: is this plus `_xlsx`, `oi_worksheet_xlsx`, matching the other two formats' own rule).
OI_WORKSHEET_FORMAT = "oi_worksheet"

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
    if fmt not in ("pdf", "xlsx", LOW_STOCK_FORMAT, OI_WORKSHEET_FORMAT):
        raise AppException(
            status_code=422,
            message="format must be pdf, xlsx, low_stock_xlsx or oi_worksheet.",
        )
    # R6 (PLAN-low-stock-export-split-25sep, AC-13): `split` names how the LOW STOCK
    # workbook re-files its sheets - it is meaningless on the other three formats, and
    # silently ignoring it there would let a caller believe a split it never got. Checked
    # before any guard below creates a row or touches the queue.
    if payload.split != "none" and fmt != LOW_STOCK_FORMAT:
        raise AppException(
            status_code=422,
            message="split applies to the low stock report only",
        )
    # PLAN-excel-preview-26sep AC-6: the page's supplier / category filters, the same rule
    # as `split` above - refused on the other formats rather than silently ignored.
    if (payload.suppliers or payload.categories) and fmt != LOW_STOCK_FORMAT:
        raise AppException(
            status_code=422,
            message="filters apply to the low stock report only",
        )
    if fmt == OI_WORKSHEET_FORMAT:
        # Fix round 1 (security review): the worksheet prints the OI worklist's own row
        # shape, so it needs the OI worklist's own view permission on top of
        # `scm.dashboard.view` (`_EXPORT`'s dependency) - a caller who can only see the
        # dashboard, and never the worklist itself, must not be able to print it. Checked
        # IN-BODY rather than as a second route dependency, so the order sheet and low
        # stock formats stay reachable on `scm.dashboard.view` alone.
        from app.services.user_service import UserPermissionService

        from app.api.v1.projects.order_inquiries import VIEW as OI_WORKLIST_VIEW

        if not UserPermissionService(db).check_user_has_permission(
            current_user["id"], OI_WORKLIST_VIEW
        ):
            raise AppException(
                403,
                "You do not have permission to export the OI worksheet.",
                code="oi_worksheet_permission_required",
            )
    run_id = payload.run_id
    if run_id:
        run_id = validate_uuid_path(run_id, resource="Reorder run")
        reorder_run_service.assert_run_visible(db, run_id)

    # A COUNT/MAX over `scm.order_summary_row`, not a full `report()` render on the
    # request thread (reviewer nit, review fix round A, A5) - the row-count guard (M1,
    # Phase 3 security review) and the sheet's own `as_of` - which names the file - come
    # off one lightweight query rather than serialising every row just to maybe refuse.
    #
    # The low stock workbook now shares this SAME guard (PLAN-low-stock-last-in-and-list-
    # scope S2, owner ruling 15 Sep - "I prefer All to match the list exported"):
    # `low_stock_guard_stats` (which counted every frozen row, unreduced) is gone, and the
    # low stock format's row count is checked against its OWN cap, `MAX_LOW_STOCK_ROWS`.
    #
    # AC-C6: the OI worksheet's row set is OI rows, not `scm.order_summary_row` rows, so
    # `stats["row_count"]` (still read here, for `run_id`/`as_of`) says nothing about it -
    # it is guarded separately, against `run_scope_oi_rows`'s own count and the writer's
    # own `MAX_WORKSHEET_ROWS`, the run's Start Plan scope (A3/C2: product ids and SO
    # numbers when the run named them, its own window) rather than the order sheet's cap.
    stats = svc.export_guard_stats(db, run_id=run_id)
    if fmt == OI_WORKSHEET_FORMAT:
        from app.models.scm import ReorderRun
        from app.services.scm import demand

        run = db.query(ReorderRun).filter(ReorderRun.id == stats["run_id"]).one_or_none()
        if run is None:
            raise AppException(404, "That plan does not exist.")
        # Fix round 1: `run.product_ids` passed straight through, NOT `run.product_ids or
        # None` - `run_scope_oi_rows` already reads `None` as "no product filter" and `[]`
        # as "this run's product scope resolved to nothing" (`or None` was silently
        # turning the second case into the first, widening a run scoped to nothing into
        # every product).
        scope_rows = demand.run_scope_oi_rows(
            db, run.product_ids, so_numbers=run.so_numbers,
            horizon_start=run.plan_horizon_start, horizon=run.plan_horizon_date,
        )
        if len(scope_rows) > OrderInquiryWorklistService.MAX_WORKSHEET_ROWS:
            raise AppException(422, "Narrow the plan first")
    else:
        cap = (
            low_stock_report_service.MAX_LOW_STOCK_ROWS if fmt == LOW_STOCK_FORMAT
            else svc.MAX_EXPORT_ROWS
        )
        # PLAN-excel-preview-26sep AC-7 (owner ruling 26 Sep, Q8): the low stock cap counts
        # the rows the filters KEEP, so narrowing makes a big run exportable. The cheap
        # count answers first; only a run over the cap WITH filters reads the run to count
        # what they keep, so an unfiltered request stays one COUNT query.
        over = stats["row_count"] > cap
        if over and fmt == LOW_STOCK_FORMAT and (payload.suppliers or payload.categories):
            over = low_stock_report_service.filtered_row_count(
                db, stats["run_id"],
                suppliers=payload.suppliers, categories=payload.categories,
            ) > cap
        if over:
            raise AppException(422, "Narrow the plan first")

    kind = (
        LOW_STOCK_FORMAT if fmt == LOW_STOCK_FORMAT
        else f"{OI_WORKSHEET_FORMAT}_xlsx" if fmt == OI_WORKSHEET_FORMAT
        else f"order_sheet_{fmt}"
    )
    # AC-16b (security S5, amended reviewer R1): one in-flight sheet per user per run PER
    # FORMAT - the EXACT kind, so a pending PDF never blocks an Excel request for the same
    # run (matches the AC-23 evidence: PDF then Excel back to back both succeed). No queue
    # machinery, just a guard on what `user_downloads` already states; `has_in_flight`
    # sweeps this user's stale rows first, so a dead worker's leftover never wedges a
    # caller out for the rest of the 20-minute window.
    if DownloadService(db).has_in_flight(
        user_id=str(current_user["id"]), kind=kind,
        source_entity_type="reorder_run", source_entity_id=stats["run_id"],
    ):
        if fmt == LOW_STOCK_FORMAT:
            raise AppException(
                status_code=409,
                message="A low stock report for this plan is already being prepared - "
                        "check My Downloads.",
            )
        if fmt == OI_WORKSHEET_FORMAT:
            raise AppException(
                status_code=409,
                message="An OI worksheet for this plan is already being prepared - "
                        "check My Downloads.",
            )
        fmt_label = "Excel" if fmt == "xlsx" else fmt.upper()
        raise AppException(
            status_code=409,
            message=f"An order sheet ({fmt_label}) for this plan is already being "
                    "prepared - check My Downloads.",
        )

    stamp = svc.compact_ddmmyyyy(stats["as_of"])
    filename = (
        f"low-stock-{stamp}.xlsx" if fmt == LOW_STOCK_FORMAT
        else f"oi-worksheet-{stamp}.xlsx" if fmt == OI_WORKSHEET_FORMAT
        else f"order-sheet-{stamp}.{fmt}"
    )
    download = DownloadService(db).create(
        user_id=str(current_user["id"]),
        kind=kind,
        source_entity_type="reorder_run",
        source_entity_id=stats["run_id"],
        filename=filename,
    )
    try:
        from app.services.queue_service import enqueue_job
        from app.tasks.export_tasks import (
            generate_low_stock_report,
            generate_oi_worksheet,
            generate_order_sheet,
        )

        if fmt == LOW_STOCK_FORMAT:
            enqueue_job(
                generate_low_stock_report,
                str(download.id),
                stats["run_id"],
                str(current_user["id"]),
                queue_name="imports",
                job_timeout=600,
                split=payload.split,
                suppliers=payload.suppliers or None,
                categories=payload.categories or None,
            )
        elif fmt == OI_WORKSHEET_FORMAT:
            enqueue_job(
                generate_oi_worksheet,
                str(download.id),
                stats["run_id"],
                str(current_user["id"]),
                queue_name="imports",
                job_timeout=600,
            )
        else:
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


@router.get("/order-summary/low-stock-view", response_model=LowStockViewOut)
def get_low_stock_view(
    run_id: Optional[str] = Query(
        None,
        description=(
            "Which plan's low stock report to show. Omitted means the newest completed "
            "plan. Opaque, and never rendered."
        ),
    ),
    split: ExportSplit = Query(
        low_stock_report_service.VIEW_DEFAULT_SPLIT,
        description="How the workbook is split into sheets. Defaults to supplier and category.",
    ),
    supplier: Optional[List[str]] = Query(
        None, description="Keep only these suppliers (repeat the parameter). 'No supplier' "
                          "is the blank bucket.",
    ),
    category: Optional[List[str]] = Query(
        None, description="Keep only these categories (repeat the parameter). 'No category' "
                          "is the blank bucket.",
    ),
    db: Session = Depends(get_db),
    _user: dict = Depends(_EXPORT),
):
    """The low stock report as the in-app page shows it (PLAN-excel-preview-26sep AC-1): the
    workbook for one run, split and filtered, built by the SAME function that writes the
    file (AC-2), so what the user sees is what Download gives them.

    Same gate as the export itself (`scm.dashboard.view`, a real signed-in user, never an
    API key): the report carries supplier names, PO and SPO numbers. A named `run_id` is
    validated as a UUID and checked with the run visibility gate before anything is read,
    so a malformed, absent or another company's run is the same 404.
    """
    if run_id:
        run_id = validate_uuid_path(run_id, resource="Reorder run")
        reorder_run_service.assert_run_visible(db, run_id)
    return low_stock_report_service.build_low_stock_view(
        db, run_id=run_id, split=split, suppliers=supplier, categories=category,
    )


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
