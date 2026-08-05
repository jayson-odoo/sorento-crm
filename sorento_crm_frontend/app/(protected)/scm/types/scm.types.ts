/**
 * SCM M1 — shared types (net-position dashboard + sales orders).
 *
 * M1 "real" fields carry live numbers. M1 "deferred" fields are typed `| null`
 * and MUST render as "—" in the UI (never a fabricated number) — they light up
 * in M2/M3 (avg-daily-demand, days-of-cover, ROP, low/overstock composition).
 */

/** Health-state vocabulary. Backend-real: stockout (rendered "Out of stock"), dead,
 *  low (rendered "Low stock" — stocked but net <= demand-aware reorder point, M8-B),
 *  healthy, incoming, overstock (days-of-cover over the ceiling, server-computed). */
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

/** One delivery order behind a SKU's avg-daily-demand, shown in the explain drill
 *  (M8-B9 / A2). Navigable to the order; `order_id` feeds the href, never displayed. */
export interface DemandExplainDO {
  order_id: string;
  do_number: string;
  order_date: string | null;
  qty_out: number;
}

/** `GET /analytics/explain/demand` — the demand working behind a SKU's avg daily
 *  demand: the delivery orders that drove outflow, the rate, and the variability
 *  (Coefficient of variation). Proves the number is fact-based, not fabricated. */
export interface DemandExplain {
  avg_daily_demand: number;
  demand_cv: number | null;
  demand_dos: DemandExplainDO[];
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
  /** UUIDs carried ONLY for the avg-daily-demand explain fetch (M8-B9); never
   *  displayed — the drill resolves them to human-readable DO numbers. */
  product_id?: string | null;
  warehouse_id?: string | null;
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
  // M8-B — engine reorder point (latest completed run); null when the SKU was never
  // planned. Surfaced as a column in the "Low stock" drill so net <= ROP is visible.
  reorder_point?: number | null;
  // M8-F10 — the ROP inputs from the SAME latest-run rec that sourced reorder_point
  // (rec.inputs JSONB): safety_stock + supplier lead-time days. Null when un-planned.
  // Shown with a one-line plain definition in the Low-stock reorder-point (i).
  safety_stock?: number | null;
  lead_time_days?: number | null;
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
  /** Where the order came from - it decides who may edit its figures. `inquiry` = the Order
   *  Inquiry sheet created it, `upload` = CS's outstanding extract, `manual` = keyed in. */
  source?: SalesOrderSource;
  /** The project the Order Inquiry sheet named when no customer of that name existed. */
  internal_note?: string | null;
  /** Every distinct location its lines ship from. Plural: one order can land in two. */
  stock_locations?: string[];
  /** The purchase orders its lines wait on. Present on the LIST, absent on a single read. */
  linked_purchase_orders?: LinkedPurchaseOrder[];
  awaiting_purchase_orders?: number;
  created_at: string;
}

export type SalesOrderSource = 'inquiry' | 'upload' | 'manual';

/** A pairing this order's lines claim, and whether both sides are present. */
export interface LinkedPurchaseOrder {
  po_number: string;
  item_code: string | null;
  resolved: boolean;
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
//
// `draft_recommendation` (M4-D4) is a PO drafted from an accepted reorder
// recommendation. It is deliberately OUTSIDE the on-order set — `scm.on_order_v`
// counts only status IN ('active','received','partial','closed'), so a draft is
// NOT counted as incoming supply until it is confirmed (M4-D5). Confirming a
// draft flips it to `active` and it then counts as on-order (M4-D6).
export type PurchaseOrderStatus =
  | 'draft'
  | 'draft_recommendation'
  | 'active'
  | 'confirmed'
  | 'partially_received'
  | 'received'
  // Imported purchase history is written closed and fully received (it is history, not
  // incoming supply). The union omitted it, so every historical order was typed as
  // something it is not and only rendered by the title-case fallback.
  | 'closed'
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
  /** What the ORDER says: every line of it. Not what is still coming - see `open_qty`. */
  total_qty: number;
  line_count: number;
  /** What the PO still contributes as incoming supply. Zero on a received or historical
   *  order, which is why it is a separate figure rather than a narrowing of `total_qty`. */
  open_qty?: number;
  open_line_count?: number;
  lines: PurchaseOrderLine[];
  created_at: string;
  /** True when this PO counts as incoming supply (on-order) — false for a draft
   *  or cancelled PO. Mirrors `scm.on_order_v`'s status filter (M4-D5/D6). */
  is_on_order?: boolean;
  /** How the PO originated — `recommendation` = drafted from an accepted reorder
   *  recommendation (Slice B); `import` = arrived through the purchase-history upload;
   *  `manual` = created directly. */
  source?: 'recommendation' | 'import' | 'manual';
  /** Goods-receipt reference once a GR has been created from this PO (M4-D6). */
  gr_reference?: string | null;
}
