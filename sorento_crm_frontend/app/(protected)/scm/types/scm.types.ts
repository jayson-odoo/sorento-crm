/**
 * SCM M1 — shared types (net-position dashboard + sales orders).
 *
 * M1 "real" fields carry live numbers. M1 "deferred" fields are typed `| null`
 * and MUST render as "—" in the UI (never a fabricated number) — they light up
 * in M2/M3 (avg-daily-demand, days-of-cover, ROP, low/overstock composition).
 */

/** Health-state vocabulary. Backend-real: stockout, dead, healthy, incoming,
 *  overstock (days-of-cover over the ceiling — computed + filtered server-side).
 *  low (below reorder point) stays DEFERRED to M3 (needs a real reorder point). */
export type HealthState =
  | 'stockout'
  | 'low'
  | 'healthy'
  | 'overstock'
  | 'dead'
  | 'incoming';

export type Perspective = 'product' | 'warehouse' | 'supplier';

/** ABC = consumption-value class; XYZ = demand-variability class (M2). Both are
 *  `| null` on a row when unknown (e.g. a null-cost SKU can't be ABC-classed). */
export type AbcClass = 'A' | 'B' | 'C';
export type XyzClass = 'X' | 'Y' | 'Z';

/** Filter-bar selections. `unknown` targets rows the analytics job couldn't
 *  classify (null class), so they stay reachable rather than silently hidden. */
export type AbcFilterValue = AbcClass | 'unknown';
export type XyzFilterValue = XyzClass | 'unknown';

/** Product-lifecycle scope. Defaults to the FOCUSED view (`active` + `ongoing`)
 *  so inactive/discontinued SKUs don't inflate the headline counts; `all` widens
 *  the scope back to every SKU. → products.is_active / products.is_discontinued. */
export type ActiveStatusFilter = 'active' | 'inactive' | 'all';
export type LifecycleFilter = 'ongoing' | 'discontinued' | 'all';

/** Supplier performance scorecard (M2 — supplier×product rolled to supplier for
 *  display). `confidence` gates how loudly the score is shown; `low` = thin
 *  sample, render visually distinct and never oversell it. */
export interface SupplierPerformance {
  /** Share of receipts on/before expected + grace, 0–1. null = not derivable. */
  on_time_rate: number | null;
  avg_lead_time_days: number | null;
  /** Σ rejected ÷ Σ received, 0–1. */
  reject_rate: number | null;
  /** Σ received ÷ Σ ordered, 0–1. */
  fill_rate: number | null;
  /** Composite 0–100. */
  composite_score: number | null;
  /** PO→GR completed lines behind the score. */
  sample_size: number;
  confidence: 'high' | 'medium' | 'low';
}

/** Roll-up stat tiles. */
export interface ScmRollups {
  total_stock_valuation: number;
  dead_stock_valuation: number;
  stockout_count: number;
  incoming_po_count: number;
  /** ISO date of the nearest incoming PO ETA, or null if none open. */
  incoming_po_next_eta: string | null;
  /** SKUs missing cost_price — valuation excludes them; surfaced as a coverage note. */
  valuation_missing_cost_count: number;
  // M2 — real: Σ stock_valuation / count where days_of_cover > overstock_days.
  overstock_valuation: number | null;
  overstock_count: number | null;
  // Deferred (M3) — render "—": needs a real reorder point.
  below_rop_count: number | null;
}

/** One monthly bucket of DO outflow for the expandable product row's trend viz. */
export interface DemandSeriesPoint {
  /** ``YYYY-MM`` calendar month. */
  month: string;
  /** Summed outflow qty for the month (≥ 0). */
  qty: number;
}

/** ~12 monthly buckets of DO outflow for one SKU (M2 demand trend). */
export interface DemandSeries {
  sku: string;
  product_name: string;
  warehouse_code: string | null;
  /** Demand-variability class → drives the plain-language caption. */
  xyz_class: XyzClass | null;
  /** Oldest → newest monthly buckets, zero-filled. */
  points: DemandSeriesPoint[];
  total_qty: number;
  peak_qty: number;
}

/** One warehouse tile in the Health Grid. */
export interface WarehouseHealth {
  warehouse_code: string;
  warehouse_name: string;
  /** The single worst health state in the warehouse — drives the accent bar. */
  worst_state: HealthState;
  /** on_hand × cost_price summed; null when no SKU in the warehouse has a cost. */
  stock_valuation: number | null;
  stockout_count: number;
  dead_count: number;
  incoming_po_count: number;
  sku_count: number;
  /** Composition mini-bar counts. low/overstock are deferred (null) at M1. */
  composition: {
    stockout: number;
    dead: number;
    healthy: number;
    incoming: number;
    low: number | null;
    overstock: number | null;
  };
}

/** Per-warehouse breakdown of an aggregated product row (expand target). */
export interface WarehouseBreakdown {
  warehouse_code: string;
  warehouse_name: string;
  on_hand: number;
  on_order: number;
  committed: number;
  net_position: number;
  stock_valuation: number | null;
  status: HealthState;
}

/** Product perspective: SKU aggregated across the selected warehouse set. */
export interface NetPositionRow {
  /** Human-readable SKU code — shown in the UI (never a UUID). */
  sku: string;
  product_name: string;
  product_class: string | null;
  variant: string | null;
  supplier_name: string | null;
  on_hand: number;
  on_order: number;
  committed: number;
  /** net_position = on_hand + on_order − committed. */
  net_position: number;
  stock_valuation: number | null;
  last_movement_at: string | null;
  status: HealthState;
  /** True when one warehouse is stocked out while another has surplus. */
  imbalance: boolean;
  /** Attention badge: stockout WITH open committed demand. */
  stockout_with_committed: boolean;
  /** Server-side attention sort key (lower = more urgent). */
  attention_rank: number;
  warehouses: WarehouseBreakdown[];
  // M2 — real analytics (demand_stat + item_classification), server-fed.
  avg_daily_demand: number | null;
  days_of_cover: number | null;
  abc_class: AbcClass | null;
  xyz_class: XyzClass | null;
  // Deferred (M3) — render "—".
  reorder_point: number | null;
}

/** Product line used by the drill-down popups (stat tiles, warehouse counts,
 *  "view products"). Read-only, human code + name + warehouse + the same metric
 *  columns as the Product-perspective grid. Never a UUID. */
export interface ProductSummary {
  sku: string;
  product_name: string;
  warehouse_code: string;
  warehouse_name: string;
  on_hand: number;
  on_order: number;
  committed: number;
  /** net_position = on_hand + on_order − committed. */
  net_position: number;
  /** on_hand × cost_price; null when the SKU has no cost on file. */
  stock_valuation: number | null;
  status: HealthState;
  /** Stocked out WITH open committed demand — the attention badge. */
  stockout_with_committed: boolean;
  // M2 — real analytics (demand_stat + item_classification), server-fed.
  avg_daily_demand: number | null;
  days_of_cover: number | null;
  abc_class: AbcClass | null;
  xyz_class: XyzClass | null;
}

/** Paginated drill-down response (server-side search/sort/pagination). */
export interface ProductSummaryPage {
  data: ProductSummary[];
  total: number;
  page: number;
}

/** Supplier perspective: one SKU line under a supplier group. */
export interface SupplierSkuRow {
  sku: string;
  product_name: string;
  on_hand: number;
  on_order: number;
  net_position: number;
  status: HealthState;
  incoming_po_eta: string | null;
}

export interface SupplierGroup {
  supplier_code: string;
  supplier_name: string;
  /** Declared (contractual) lead time in days; null if not on file. */
  declared_lead_time_days: number | null;
  incoming_po_count: number;
  incoming_po_next_eta: string | null;
  skus: SupplierSkuRow[];
  /** M2 scorecard (real supplier-level analytics). null = not yet scored. */
  performance: SupplierPerformance | null;
}

// ---------------------------------------------------------------------------
// Sales orders (M1-D14)
// ---------------------------------------------------------------------------

// `medium` is what the seed / back-end emits; `normal` is the FE-form default —
// both are supported. Any unknown value still renders via a neutral fallback.
export type SalesOrderPriority = 'low' | 'medium' | 'normal' | 'high' | 'urgent';
export type SalesOrderStatus =
  | 'open'
  | 'partially_delivered'
  | 'fulfilled'
  | 'cancelled';

export interface SalesOrderLine {
  id: string;
  sku: string;
  product_name: string;
  qty_ordered: number;
  /** Stamped by create-DO-from-SO (soft link, no hard FK). */
  qty_delivered: number;
  uom: string;
}

export interface SalesOrder {
  id: string;
  /** Human-readable SO number — shown in the UI (never a UUID). */
  so_number: string;
  order_type: string;
  order_type_label: string;
  customer_code: string;
  customer_name: string;
  /** Drives demand_nature in M2 channel-tagging. */
  market_segment: string | null;
  priority: SalesOrderPriority;
  status: SalesOrderStatus;
  order_date: string;
  requested_delivery_date: string | null;
  total_qty: number;
  /** Undelivered qty = committed demand contributed to the dashboard. */
  committed_qty: number;
  lines: SalesOrderLine[];
  created_at: string;
}

export interface SalesOrderFormData {
  order_type: string;
  customer_code: string;
  priority: SalesOrderPriority;
  requested_delivery_date?: string | null;
  lines: { sku: string; qty_ordered: number; uom: string }[];
}

// ---------------------------------------------------------------------------
// Purchase orders (read-only at M1 — create/confirm lands in M4)
// ---------------------------------------------------------------------------

// `active` is the seed / back-end value for a confirmed-but-not-fully-received
// PO. Any unknown value still renders via a neutral fallback.
export type PurchaseOrderStatus =
  | 'draft'
  | 'active'
  | 'confirmed'
  | 'partially_received'
  | 'received'
  | 'cancelled';

export interface PurchaseOrderLine {
  id: string;
  sku: string;
  product_name: string;
  qty_ordered: number;
  qty_received: number;
  uom: string;
}

export interface PurchaseOrder {
  id: string;
  /** Human-readable PO number — shown in the UI (never a UUID). */
  po_number: string;
  supplier_code: string;
  supplier_name: string;
  warehouse_code: string | null;
  warehouse_name: string | null;
  status: PurchaseOrderStatus;
  order_date: string;
  /** Expected delivery / ETA; null when not committed yet. */
  expected_date: string | null;
  total_qty: number;
  line_count: number;
  lines: PurchaseOrderLine[];
  created_at: string;
}
