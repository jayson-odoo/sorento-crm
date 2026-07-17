"""SCM M1 dashboard response schemas.

Mirror the FE contract in ``app/(protected)/scm/services/scmDashboardService.ts``
+ ``types/scm.types.ts``. No UUIDs reach the UI — product / warehouse / supplier /
category are resolved to human-readable codes/names server-side. M1-deferred
fields (avg_daily_demand, days_of_cover, reorder_point, below_rop_count,
overstock_valuation, composition.low / .overstock) are typed Optional and always
serialized as ``null`` until M2/M3.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


# --- rollups ----------------------------------------------------------------

class ScmRollups(BaseModel):
    total_stock_valuation: float
    dead_stock_valuation: float
    stockout_count: int
    incoming_po_count: int
    incoming_po_next_eta: Optional[str] = None
    valuation_missing_cost_count: int
    # M2 — real: Σ stock_valuation / count where days_of_cover > overstock_days.
    overstock_valuation: Optional[float] = None
    overstock_count: Optional[int] = None
    # Deferred (M3) — always null: needs a real reorder point.
    below_rop_count: Optional[int] = None


# --- warehouse tiles --------------------------------------------------------

class WarehouseComposition(BaseModel):
    stockout: int
    dead: int
    healthy: int
    incoming: int
    low: Optional[int] = None
    overstock: Optional[float] = None


class WarehouseHealth(BaseModel):
    warehouse_code: str
    warehouse_name: str
    worst_state: str
    stock_valuation: Optional[float] = None
    stockout_count: int
    dead_count: int
    incoming_po_count: int
    sku_count: int
    composition: WarehouseComposition


class WarehouseHealthList(BaseModel):
    data: List[WarehouseHealth]


# --- net position (product perspective) -------------------------------------

class WarehouseBreakdown(BaseModel):
    warehouse_code: str
    warehouse_name: str
    on_hand: float
    on_order: float
    committed: float
    net_position: float
    stock_valuation: Optional[float] = None
    status: str


class NetPositionRow(BaseModel):
    sku: str
    product_name: str
    product_class: Optional[str] = None
    variant: Optional[str] = None
    supplier_name: Optional[str] = None
    on_hand: float
    on_order: float
    committed: float
    net_position: float
    stock_valuation: Optional[float] = None
    last_movement_at: Optional[str] = None
    status: str
    imbalance: bool
    stockout_with_committed: bool
    attention_rank: int
    warehouses: List[WarehouseBreakdown]
    # M2 — real analytics (product-level: Σ per-warehouse demand; dominant ABC/XYZ).
    avg_daily_demand: Optional[float] = None
    days_of_cover: Optional[float] = None
    abc_class: Optional[str] = None
    xyz_class: Optional[str] = None
    # Deferred (M3) — always null: needs a real reorder point.
    reorder_point: Optional[float] = None


class NetPositionPagination(BaseModel):
    total: int
    page: int


class NetPositionResponse(BaseModel):
    data: List[NetPositionRow]
    empty: bool
    pagination: NetPositionPagination


# --- supplier perspective ---------------------------------------------------

class SupplierSkuRow(BaseModel):
    sku: str
    product_name: str
    on_hand: float
    on_order: float
    net_position: float
    status: str
    incoming_po_eta: Optional[str] = None


class SupplierPerformance(BaseModel):
    """M2 supplier-level scorecard. Rate fields (on_time/reject/fill) are 0–1;
    composite is scaled 0–100. Null fields where the metric couldn't be derived;
    a thin sample carries ``confidence='low'``. Absent entirely when never scored."""
    on_time_rate: Optional[float] = None
    avg_lead_time_days: Optional[float] = None
    reject_rate: Optional[float] = None
    fill_rate: Optional[float] = None
    composite_score: Optional[float] = None
    sample_size: int
    confidence: str


class SupplierGroup(BaseModel):
    supplier_code: str
    supplier_name: str
    declared_lead_time_days: Optional[int] = None
    incoming_po_count: int
    incoming_po_next_eta: Optional[str] = None
    skus: List[SupplierSkuRow]
    # M2 — real scorecard, or null when the supplier has no computed performance.
    performance: Optional[SupplierPerformance] = None


class SupplierGroupList(BaseModel):
    data: List[SupplierGroup]


# --- product drill-down (popups) --------------------------------------------

class ProductSummary(BaseModel):
    sku: str
    product_name: str
    # UUIDs carried for the avg-daily-demand explain fetch only (M8-B9); never
    # displayed — the FE resolves them to human-readable DO numbers via the drill.
    product_id: Optional[str] = None
    warehouse_id: Optional[str] = None
    warehouse_code: str
    warehouse_name: str
    on_hand: float
    on_order: float
    committed: float
    net_position: float
    stock_valuation: Optional[float] = None
    status: str
    # Stocked out WITH open committed demand — the reorder-signal attention badge.
    stockout_with_committed: bool
    # M2 — real analytics (per SKU×warehouse).
    avg_daily_demand: Optional[float] = None
    days_of_cover: Optional[float] = None
    abc_class: Optional[str] = None
    xyz_class: Optional[str] = None
    # M8-B — engine reorder point (latest completed run); null when the SKU was never
    # planned. A stocked SKU with ``net_position <= reorder_point`` reads as low-stock.
    reorder_point: Optional[float] = None
    # M8-F10 — the safety stock + supplier lead-time days that FEED the reorder point,
    # read from the SAME latest-run rec's frozen ``inputs`` JSONB that sourced
    # ``reorder_point`` above. Null when un-planned (no completed run / no rec inputs).
    # The Low-stock reorder-point (i) shows each value with a one-line plain definition
    # so ROP is not a black box.
    safety_stock: Optional[float] = None
    lead_time_days: Optional[float] = None


class ProductSummaryList(BaseModel):
    data: List[ProductSummary]
    total: int
    page: int


# --- demand trend series (expandable product row viz) -----------------------

class DemandSeriesPoint(BaseModel):
    """One monthly bucket of DO outflow (``YYYY-MM`` + summed qty)."""
    month: str
    qty: float


class DemandSeries(BaseModel):
    sku: str
    product_name: str
    warehouse_code: Optional[str] = None
    xyz_class: Optional[str] = None
    points: List[DemandSeriesPoint]
    total_qty: float
    peak_qty: float


# --- dead-stock-days quick setting (global reorder_policy) -------------------

class DeadStockDays(BaseModel):
    dead_stock_days: int


class DeadStockDaysUpdate(BaseModel):
    dead_stock_days: int
