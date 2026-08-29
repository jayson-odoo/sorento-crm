"""Stock Debt: the month x product board and the cell drill (S2, R22/R28).

    GET /project-sales/stock-debt
    GET /project-sales/stock-debt/{product_id}/cell?month=

Two reads, both behind `projects.stock_debt.view` (AC-S2-8; the permission and its grant
sweep from `projects.projects.view` ship in migration 443 with S1). Its own permission rather
than the module's general view right because this screen states the whole book's exposure -
every customer's shortfall on one page - which is not the same grant as reading a project.

Mounted before the projects router for the same reason its siblings are: `/project-sales/
stock-debt` is a literal segment that `/projects/{project_id}` must not capture.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.common import MAX_PAGE_LIMIT
from app.schemas.stock_debt import StockDebtCell, StockDebtList
from app.services.error_handler import handle_internal_error
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
            "read, so the balances are the group's own rather than the book's filtered."
        ),
    ),
    only_debt: bool = Query(
        True, description="Drop products that owe nothing in any month."
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
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """The two tables behind one cell: what is DUE in that month and what is HELD for it."""
    try:
        validate_uuid_path(product_id, resource="Product")
        return StockDebtService(db).cell(product_id, month, group)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
