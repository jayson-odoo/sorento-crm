"""GET /api/v1/inventory/stock-position - the supplier stock sheet, every supplier, one row per item.

Read-only, opened by the Stock Status page's own permissions (`stock_status.READ_PERMISSIONS`):
the figures are that panel's, for every item. Plan:
documentation/plans/inventory/PLAN-stock-position-report-27oct.md.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.v1.inventory.stock_status import READ_PERMISSIONS
from app.database import get_db
from app.dependencies import require_any_permission_with_api_key
from app.services import stock_position_service as svc

router = APIRouter()

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _result(db, query, supplier_id, brand_id, warehouse_id, sort, dir, sales_basis):
    return svc.stock_position(
        db,
        query=query,
        supplier_ids=supplier_id,
        brand_ids=brand_id,
        warehouse_ids=warehouse_id,
        sort=sort,
        direction=dir,
        sales_basis=sales_basis,
    )


@router.get("")
def get_stock_position(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    sort: Optional[str] = Query(None, description="A column key, or wh:<warehouse code>."),
    dir: str = Query("asc", pattern="^(asc|desc)$"),
    query: Optional[str] = Query(None, description="Item code or description contains."),
    supplier_id: Optional[List[str]] = Query(None),
    brand_id: Optional[List[str]] = Query(None),
    warehouse_id: Optional[List[str]] = Query(None),
    sales_basis: str = Query("so_ordered", description="so_ordered or invoiced."),
    _user: dict = Depends(require_any_permission_with_api_key(READ_PERMISSIONS)),
    db: Session = Depends(get_db),
):
    """One page of items, every figure computed and sorted on the server."""
    result = _result(db, query, supplier_id, brand_id, warehouse_id, sort, dir, sales_basis)
    return svc.page(result, page, limit)


@router.get("/export")
def export_stock_position(
    sort: Optional[str] = Query(None),
    dir: str = Query("asc", pattern="^(asc|desc)$"),
    query: Optional[str] = Query(None),
    supplier_id: Optional[List[str]] = Query(None),
    brand_id: Optional[List[str]] = Query(None),
    warehouse_id: Optional[List[str]] = Query(None),
    sales_basis: str = Query("so_ordered"),
    _user: dict = Depends(require_any_permission_with_api_key(READ_PERMISSIONS)),
    db: Session = Depends(get_db),
):
    """Every row of the same filtered, sorted set, as an Excel workbook."""
    result = _result(db, query, supplier_id, brand_id, warehouse_id, sort, dir, sales_basis)
    return Response(
        content=svc.workbook(result),
        media_type=_XLSX,
        headers={"Content-Disposition": 'attachment; filename="stock-position.xlsx"'},
    )
