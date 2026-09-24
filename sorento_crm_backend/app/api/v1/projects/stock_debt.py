"""Stock Debt: the month x product board, the cell drill and the workbook export
(S2, R22/R28; extended 24 Sep 2026, PLAN-stock-debt-filters-totals-export-24sep.md).

    GET  /project-sales/stock-debt
    GET  /project-sales/stock-debt/{product_id}/cell?month=
    POST /project-sales/stock-debt/export

All three behind `projects.stock_debt.view` (AC-S2-8; the permission and its grant
sweep from `projects.projects.view` ship in migration 443 with S1). Its own permission
rather than the module's general view right because this screen states the whole book's
exposure - every customer's shortfall on one page - which is not the same grant as reading
a project. The export route reuses it too (AC-12): exporting states nothing new, it only
prints what the board already answers.

Mounted before the projects router for the same reason its siblings are: `/project-sales/
stock-debt` is a literal segment that `/projects/{project_id}` must not capture.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.common import MAX_PAGE_LIMIT
from app.schemas.download import DownloadResponse
from app.schemas.stock_debt import Book, StockDebtCell, StockDebtExportIn, StockDebtList
from app.services.error_handler import AppException, handle_internal_error
from app.services.scm.stock_debt_service import StockDebtService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "projects.stock_debt.view"


@router.get("/stock-debt", response_model=StockDebtList)
def list_stock_debt(
    query: Optional[str] = Query(
        None, description="Product code or name."
    ),
    group: Optional[str] = Query(
        None,
        description=(
            "Ownership group suffix (`BB`, `IB`, ...). Narrows the STOCK and the DEMAND "
            "read, so the balances are the group's own rather than the book's filtered. "
            "Ignored under `book=retail` - a site pool is nobody's ownership group."
        ),
    ),
    only_debt: bool = Query(
        True, description="Drop products that owe nothing in any month."
    ),
    cutoff: Optional[date] = Query(
        None,
        description=(
            "Drop demand lines with `required_date` after this date; the axis (columns) "
            "ends at its month. Supply landing after a line's own due date, but on or "
            "before the cutoff, still covers it - only demand is dropped."
        ),
    ),
    supplier_id: Optional[str] = Query(
        None,
        description=(
            "Keep only products whose LAST supplier (newest purchase-order line, else the "
            "primary-flagged product supplier) is this one. `none` keeps products with "
            "neither."
        ),
    ),
    book: Book = Query(
        "all",
        description=(
            "`all` (default) spans flagged project bins AND the site pools in one read; "
            "`project` is flagged bins only (the pre-24-Sep view); `retail` is pools only "
            "and ignores `group`."
        ),
    ),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """One row per product, one column per month, the cell is the cumulative balance.

    Plain ``def``, so FastAPI runs it in a threadpool: it is synchronous SQLAlchemy over the
    whole flagged catalogue, and on the event loop it would hold up every other request.
    """
    try:
        return StockDebtService(db).list(
            query=query,
            group=group,
            only_debt=only_debt,
            cutoff=cutoff,
            supplier_id=supplier_id,
            book=book,
            page=page,
            limit=limit,
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/stock-debt/{product_id}/cell", response_model=StockDebtCell)
def stock_debt_cell(
    product_id: str,
    month: str = Query(
        ...,
        description=(
            "`YYYY-MM`, or `tba` / `undated` / `unlocated` for the three right-hand columns."
        ),
    ),
    group: Optional[str] = Query(
        None,
        description=(
            "The ownership group the BOARD was narrowed to. Same meaning as on the list: it "
            "narrows the span the balance is recomputed from, so the drill foots with the "
            "cell that opened it."
        ),
    ),
    cutoff: Optional[date] = Query(
        None,
        description="The BOARD's own cutoff, echoed so the drill foots with the cell that opened it.",
    ),
    book: Book = Query(
        "all",
        description="The BOARD's own book, echoed so the drill foots with the cell that opened it.",
    ),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """The two tables behind one cell: what is DUE in that month and what is HELD for it."""
    try:
        validate_uuid_path(product_id, resource="Product")
        return StockDebtService(db).cell(product_id, month, group, cutoff, book)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/stock-debt/export", response_model=DownloadResponse, status_code=201)
def export_stock_debt(
    payload: StockDebtExportIn = Body(default_factory=StockDebtExportIn),
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """Queue the workbook through My Downloads (R10/R12, AC-12), the same pipeline the low
    stock report uses (`generate_low_stock_report` / `export_order_summary`): a
    `user_downloads` row is created FIRST, `generate_stock_debt_xlsx` runs on the `imports`
    queue, and the workbook itself is fetched later from the drawer once the worker marks
    the row ready. On an enqueue failure the row is marked failed rather than left pending
    forever, and a 503 tells the caller to try again.

    Filters travel as the ROUTE's own body (`StockDebtExportIn`), not a `run_id`: this
    screen has no reorder run underneath it, only the board's own current filters.
    """
    from app.api.v1.projects._common import acting_company_id
    from app.services.download_service import DownloadService
    from app.services.queue_service import enqueue_job
    from app.tasks.export_tasks import generate_stock_debt_xlsx

    try:
        filters = payload.model_dump()
        # The worker has no request-scoped company (AC-12b): snapshot the enqueuing
        # request's own single-company scope so the task can adopt it - same shape
        # `export_order_inquiry_worklist_async` uses for the same reason (reuse, not
        # reimplement).
        company_id = acting_company_id(db)

        filename = f"stock-debt-{date.today().strftime('%d%m%Y')}.xlsx"
        download = DownloadService(db).create(
            user_id=str(current_user["id"]),
            kind="stock_debt_xlsx",
            filename=filename,
        )
        try:
            enqueue_job(
                generate_stock_debt_xlsx,
                str(download.id),
                str(current_user["id"]),
                filters,
                company_id=company_id,
                queue_name="imports",
                job_timeout=600,
            )
        except Exception as e:  # noqa: BLE001
            DownloadService(db).mark_failed(
                str(download.id), f"Could not queue stock debt export: {e}"
            )
            raise AppException(
                status_code=503,
                message="Could not queue stock debt export. Please try again.",
            )
        return DownloadResponse.model_validate(DownloadService(db).get(str(download.id)))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
