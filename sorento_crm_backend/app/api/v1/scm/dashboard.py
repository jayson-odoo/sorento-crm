"""SCM M1 dashboard endpoints - net position / warehouses / suppliers / rollups /
products drill-down. All read the M0 views and resolve UUIDs to human codes/names.

Shared filter query params (per the FE contract header in scmDashboardService.ts):
  warehouse    repeatable OR comma-separated warehouse_code list (also accepts the
               ``warehouses`` alias so the FE can send either).
  category_id  product_categories.id
  supplier     supplier_code
  health       stockout|dead|healthy|incoming
  q            free-text SKU-code / product-name search
  active_status  active|inactive|all - products.is_active. DEFAULT active.
  lifecycle      ongoing|discontinued|all - products.is_discontinued (ongoing=false).
                 DEFAULT ongoing.

The two lifecycle params DEFAULT to the FOCUSED view (active + ongoing) when
absent/empty, so inactive/discontinued SKUs never inflate the headline
stockout/dead/valuation figures unless the caller explicitly widens the scope.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_dashboard import (
    DemandSeries,
    NetPositionResponse,
    ProductSummaryList,
    ScmRollups,
    SupplierGroupList,
    WarehouseHealthList,
)
from app.services.scm.dashboard_service import ScmFilters, ScmDashboardService

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")


def _split(values: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    for v in values or []:
        out.extend(part.strip() for part in v.split(",") if part.strip())
    return out


def _norm(value: Optional[str], allowed: set, default: str) -> str:
    """Coerce an absent/empty/unrecognised lifecycle param to the focused default."""
    v = (value or "").strip().lower()
    return v if v in allowed else default


_ACTIVE_STATUS_VALUES = {"active", "inactive", "all"}
_LIFECYCLE_VALUES = {"ongoing", "discontinued", "all"}


def _filters(
    warehouse: Optional[List[str]],
    warehouses: Optional[List[str]],
    category_id: Optional[str],
    supplier: Optional[str],
    health: Optional[str],
    q: Optional[str],
    active_status: Optional[str] = None,
    lifecycle: Optional[str] = None,
    abc: Optional[str] = None,
    xyz: Optional[str] = None,
) -> ScmFilters:
    return ScmFilters(
        warehouses=_split(warehouse) + _split(warehouses),
        category_id=category_id,
        supplier=supplier,
        health=health,
        q=q,
        abc=(abc or None),
        xyz=(xyz or None),
        active_status=_norm(active_status, _ACTIVE_STATUS_VALUES, "active"),
        lifecycle=_norm(lifecycle, _LIFECYCLE_VALUES, "ongoing"),
    )


@router.get("/dashboard/net-position", response_model=NetPositionResponse)
def net_position(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort: Optional[str] = Query(None),
    dir: str = Query("asc"),
    query: Optional[str] = Query(None),
    warehouse: Optional[List[str]] = Query(None),
    warehouses: Optional[List[str]] = Query(None),
    category_id: Optional[str] = Query(None),
    supplier: Optional[str] = Query(None),
    health: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    abc: Optional[str] = Query(None),
    xyz: Optional[str] = Query(None),
    active_status: Optional[str] = Query(None),
    lifecycle: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    filters = _filters(warehouse, warehouses, category_id, supplier, health, q,
                       active_status, lifecycle, abc, xyz)
    return ScmDashboardService(db).net_position(filters, page, limit, sort, dir, query)


@router.get("/dashboard/warehouses", response_model=WarehouseHealthList)
def warehouses_tiles(
    warehouse: Optional[List[str]] = Query(None),
    warehouses: Optional[List[str]] = Query(None),
    category_id: Optional[str] = Query(None),
    supplier: Optional[str] = Query(None),
    health: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    abc: Optional[str] = Query(None),
    xyz: Optional[str] = Query(None),
    active_status: Optional[str] = Query(None),
    lifecycle: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    filters = _filters(warehouse, warehouses, category_id, supplier, health, q,
                       active_status, lifecycle, abc, xyz)
    return {"data": ScmDashboardService(db).warehouses(filters)}


@router.get("/dashboard/suppliers", response_model=SupplierGroupList)
def suppliers_groups(
    warehouse: Optional[List[str]] = Query(None),
    warehouses: Optional[List[str]] = Query(None),
    category_id: Optional[str] = Query(None),
    supplier: Optional[str] = Query(None),
    health: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    abc: Optional[str] = Query(None),
    xyz: Optional[str] = Query(None),
    active_status: Optional[str] = Query(None),
    lifecycle: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    filters = _filters(warehouse, warehouses, category_id, supplier, health, q,
                       active_status, lifecycle, abc, xyz)
    return {"data": ScmDashboardService(db).suppliers(filters)}


@router.get("/dashboard/rollups", response_model=ScmRollups)
def rollups(
    warehouse: Optional[List[str]] = Query(None),
    warehouses: Optional[List[str]] = Query(None),
    category_id: Optional[str] = Query(None),
    supplier: Optional[str] = Query(None),
    health: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    abc: Optional[str] = Query(None),
    xyz: Optional[str] = Query(None),
    active_status: Optional[str] = Query(None),
    lifecycle: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    filters = _filters(warehouse, warehouses, category_id, supplier, health, q,
                       active_status, lifecycle, abc, xyz)
    return ScmDashboardService(db).rollups(filters)


@router.get("/dashboard/products", response_model=ProductSummaryList)
def products_drilldown(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort: Optional[str] = Query(None),
    dir: str = Query("asc"),
    warehouse: Optional[List[str]] = Query(None),
    warehouses: Optional[List[str]] = Query(None),
    category_id: Optional[str] = Query(None),
    supplier: Optional[str] = Query(None),
    health: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    abc: Optional[str] = Query(None),
    xyz: Optional[str] = Query(None),
    active_status: Optional[str] = Query(None),
    lifecycle: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    filters = _filters(warehouse, warehouses, category_id, supplier, health, q,
                       active_status, lifecycle, abc, xyz)
    # A single warehouse scope for the popup can arrive via ?warehouse=CODE.
    single_wh = filters.warehouses[0] if len(filters.warehouses) == 1 else None
    return ScmDashboardService(db).products(
        filters, status, single_wh, page, limit, sort, dir
    )


@router.get("/dashboard/demand-series", response_model=DemandSeries)
def demand_series(
    sku: str = Query(..., description="Product code (SKU) - human, never a UUID."),
    warehouse: Optional[str] = Query(None, description="Optional warehouse_code scope."),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """~12 MONTHLY buckets of DO outflow for one SKU - the expandable product row's
    "last 12 months" demand trend. Distinct from the 90-day weekly analytics rate
    window; reads the same DO consumption source (``scm.consumption_v``)."""
    return ScmDashboardService(db).demand_series(sku, warehouse)
