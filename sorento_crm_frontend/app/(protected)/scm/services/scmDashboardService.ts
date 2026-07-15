/**
 * ============================================================================
 * SCM DASHBOARD — real API bindings (Phase 2 / M1 CP2b)
 * ============================================================================
 * All endpoints are mounted under `require_module_enabled_with_api_key("scm")`
 * at `/api/v1/scm/dashboard/*` and gated on `scm.dashboard.view`. Reads M0 views
 * only. No UUIDs reach the UI — SKU / warehouse / supplier by human-readable
 * code, product category resolved to a name server-side.
 *
 * Shared filter query params (apply to every endpoint below):
 *   warehouse    — comma-separated warehouse_code list (the BE also accepts a
 *                  repeatable `warehouse` and a `warehouses` alias; we send the
 *                  comma-separated `warehouse` form).
 *   category_id  — product_categories.id (UI shows the name, never the UUID).
 *   supplier     — supplier_code.
 *   health       — stockout|dead|healthy|incoming (legend chips + drill-downs).
 *   q            — free-text product search (SKU code / name). On net-position
 *                  the BE collapses `query` → `q`, so we send it via `query`.
 * ============================================================================
 *
 * ── M2 ANALYTICS (live, server-fed by the demand/classification/supplier job) ─
 * net-position rows (`/net-position`) + drill-down rows (`/products`):
 *   avg_daily_demand : number | null   // demand_stat.avg_daily_demand (units/day).
 *                                       //   null = no demand history for the SKU.
 *   days_of_cover    : number | null   // net_position ÷ avg_daily_demand, whole days.
 *                                       //   null when demand is 0 (∞ cover) or a
 *                                       //   deficit (net_position < 0).
 *   abc_class        : 'A'|'B'|'C'|null // item_classification.abc_class (dominant
 *                                       //   value location on net-position rows).
 *                                       //   null = unknown (e.g. null cost_price SKU).
 *   xyz_class        : 'X'|'Y'|'Z'|null // item_classification.xyz_class. null = unknown.
 *   reorder_point    : number | null    // M3 — stays null until the ROP engine lands.
 *
 * demand trend series (`/demand-series?sku=&warehouse=`) — the expandable Product
 * row's "Demand — last 12 months" sparkline. ~12 MONTHLY buckets of DO outflow
 * (oldest → newest), distinct from the 90-day weekly analytics rate window:
 *   { sku, product_name, warehouse_code, xyz_class, points: { month, qty }[],
 *     total_qty, peak_qty }
 *
 * roll-ups (`/rollups`):
 *   overstock_valuation : number | null // Σ stock_valuation WHERE days_of_cover
 *                                        //   > reorder_policy.overstock_days.
 *   overstock_count     : number | null // count of the same SKU×warehouse rows.
 *   below_rop_count     : number | null // M3, NOT M2 — needs a real reorder point;
 *                                        //   stays null, tile DEFERRED.
 *
 * suppliers (`/suppliers`) — a `performance` object per supplier group, or null:
 *   performance: {
 *     on_time_rate      : number | null // 0–1, receipts on/before expected+grace.
 *     avg_lead_time_days: number | null // completing-receipt clock.
 *     reject_rate       : number | null // 0–1, Σ rejected ÷ Σ received.
 *     fill_rate         : number | null // 0–1, Σ received ÷ Σ ordered.
 *     composite_score   : number | null // 0–100.
 *     sample_size       : number        // PO→GR completed lines behind the score.
 *     confidence        : 'high'|'medium'|'low'  // thin sample ⇒ 'low'.
 *   } | null                            // null when the supplier was never scored.
 *
 * Filters `abcClass` / `xyzClass` are sent as `abc` / `xyz` query params
 * ('A'|'B'|'C'|'unknown' / 'X'|'Y'|'Z'|'unknown') on the product grid + drill-down;
 * the backend filters + paginates authoritatively. The FE relabels the classes to
 * plain language for DISPLAY ONLY (abc_class → "Value": High/Med/Low; xyz_class →
 * "Demand": Steady/Variable/Erratic — see `lib/health` display maps); the wire
 * contract keeps the industry-standard ABC/XYZ names.
 *
 * The `health` param accepts `stockout|dead|healthy|incoming|overstock`. Overstock
 * is demand-derived (days-of-cover over the ceiling) and computed + filtered
 * server-side. `low` (below reorder point) is DEFERRED to M3 — its tile + legend
 * chip render greyed/inert and `health=low` is never sent.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  AbcFilterValue,
  ActiveStatusFilter,
  DemandSeries,
  HealthState,
  LifecycleFilter,
  NetPositionRow,
  ProductSummaryPage,
  ScmRollups,
  SupplierGroup,
  WarehouseHealth,
  XyzFilterValue,
} from '../types/scm.types';

const BASE = '/api/v1/scm/dashboard';

export interface ScmFilters {
  warehouses: string[];
  /** Product category — bound to `product_categories.id`. */
  categoryId: string | null;
  supplier: string | null;
  /** Health-status filter set by the interactive legend chips + drill-downs. */
  healthStatus: HealthState | null;
  /** M2 ABC class filter (client-side in Phase 1). `unknown` = unclassified. */
  abcClass: AbcFilterValue | null;
  /** M2 XYZ class filter (client-side in Phase 1). `unknown` = unclassified. */
  xyzClass: XyzFilterValue | null;
  /** Free-text product search (SKU / name). */
  productSearch: string;
  /**
   * Product-lifecycle scope → products.is_active / products.is_discontinued.
   * The DEFAULT is the FOCUSED view (`active` + `ongoing`), NOT `all`: inactive
   * and discontinued SKUs are excluded from every dashboard read (counts,
   * valuations, grids) unless the user widens the scope. The backend applies the
   * same focused default when these params are absent — sending them explicitly
   * keeps FE↔BE in lock-step and makes the active scope visible in the URL.
   */
  activeStatus: ActiveStatusFilter;
  lifecycle: LifecycleFilter;
}

/**
 * The default filter state = the FOCUSED view. `activeStatus`/`lifecycle` default
 * to `active`/`ongoing` (NOT `all`), so a fresh dashboard — and every "Clear" —
 * resets back to focused, matching the backend default. "Show all" widens both.
 */
export const EMPTY_SCM_FILTERS: ScmFilters = {
  warehouses: [],
  categoryId: null,
  supplier: null,
  healthStatus: null,
  abcClass: null,
  xyzClass: null,
  productSearch: '',
  activeStatus: 'active',
  lifecycle: 'ongoing',
};

export interface NetPositionQuery extends ScmFilters {
  pageIndex: number;
  pageSize: number;
  sortField?: string;
  sortDir?: 'asc' | 'desc';
  searchQuery?: string;
}

/** Build the shared SCM filter query params for the non-paginated endpoints. */
function filterParams(filters: ScmFilters): URLSearchParams {
  const sp = new URLSearchParams();
  if (filters.warehouses.length) sp.set('warehouse', filters.warehouses.join(','));
  if (filters.categoryId) sp.set('category_id', filters.categoryId);
  if (filters.supplier) sp.set('supplier', filters.supplier);
  if (filters.healthStatus) sp.set('health', filters.healthStatus);
  if (filters.abcClass) sp.set('abc', filters.abcClass);
  if (filters.xyzClass) sp.set('xyz', filters.xyzClass);
  if (filters.productSearch) sp.set('q', filters.productSearch);
  // Always send the lifecycle scope so the URL is explicit and FE↔BE agree even
  // on the focused default (the BE would default the same way if omitted).
  sp.set('active_status', filters.activeStatus);
  sp.set('lifecycle', filters.lifecycle);
  return sp;
}

export async function getRollups(filters: ScmFilters): Promise<ScmRollups> {
  const res = await apiFetch(`${BASE}/rollups?${filterParams(filters).toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load roll-up figures'));
  return res.json();
}

export async function getWarehouseHealth(
  filters: ScmFilters,
): Promise<{ data: WarehouseHealth[] }> {
  const res = await apiFetch(`${BASE}/warehouses?${filterParams(filters).toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load warehouse health'));
  return res.json();
}

export async function getSuppliers(filters: ScmFilters): Promise<{ data: SupplierGroup[] }> {
  const res = await apiFetch(`${BASE}/suppliers?${filterParams(filters).toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load suppliers'));
  return res.json();
}

export async function getNetPosition(
  params: NetPositionQuery,
): Promise<DataGridApiResponse<NetPositionRow>> {
  const sorting = params.sortField
    ? [{ id: params.sortField, desc: params.sortDir === 'desc' }]
    : undefined;
  const search = params.searchQuery || params.productSearch;
  const sp = buildDataGridParams(
    {
      pageIndex: params.pageIndex,
      pageSize: params.pageSize,
      sorting,
      searchQuery: search,
    },
    {
      warehouse: params.warehouses.length ? params.warehouses.join(',') : undefined,
      category_id: params.categoryId ?? undefined,
      supplier: params.supplier ?? undefined,
      health: params.healthStatus ?? undefined,
      abc: params.abcClass ?? undefined,
      xyz: params.xyzClass ?? undefined,
      active_status: params.activeStatus,
      lifecycle: params.lifecycle,
    },
  );
  const res = await apiFetch(`${BASE}/net-position?${sp.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load net position'));
  return res.json();
}

/** Drill-down popup query: base target scope + server-side search/sort/page. */
export interface ProductsQuery {
  /** Narrow to one health state (stat-tile / warehouse-count drill-down). */
  status?: HealthState | null;
  /** Scope to one warehouse (overrides the current warehouse filter). */
  warehouse?: string | null;
  /** Free-text search over product code / name (overrides the dashboard search). */
  q?: string;
  /** Sortable metric column, or `sku` / `status`. */
  sort?: string;
  dir?: 'asc' | 'desc';
  page?: number;
  limit?: number;
}

/**
 * Drill-down product list backing every "what's behind this number?" popup
 * (roll-up stat tiles, warehouse tile counts, warehouse "view products"). These
 * sets can be thousands of rows, so search / sort / pagination are server-side.
 * Returns the paginated envelope (`data` + `total` + `page`).
 */
export async function getProducts(
  filters: ScmFilters,
  opts: ProductsQuery = {},
): Promise<ProductSummaryPage> {
  const sp = filterParams(filters);
  if (opts.warehouse) sp.set('warehouse', opts.warehouse); // popup scope overrides
  if (opts.status) sp.set('status', opts.status);
  if (opts.q) sp.set('q', opts.q); // popup search overrides the dashboard search
  if (opts.sort) {
    sp.set('sort', opts.sort);
    sp.set('dir', opts.dir ?? 'asc');
  }
  sp.set('page', String(opts.page ?? 1));
  sp.set('limit', String(opts.limit ?? 50));
  const res = await apiFetch(`${BASE}/products?${sp.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load products'));
  return res.json();
}

/**
 * ~12 MONTHLY buckets of DO outflow for one SKU — the expandable Product row's
 * "Demand — last 12 months" trend viz. Optionally scoped to one warehouse; the
 * Product perspective aggregates across warehouses (no `warehouse`). SKU is the
 * human product code (never a UUID).
 */
export async function getDemandSeries(
  sku: string,
  warehouse?: string | null,
): Promise<DemandSeries> {
  const sp = new URLSearchParams({ sku });
  if (warehouse) sp.set('warehouse', warehouse);
  const res = await apiFetch(`${BASE}/demand-series?${sp.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load demand trend'));
  return res.json();
}

// --- dead-stock-days quick setting (global reorder policy) ------------------

const CONFIG_BASE = '/api/v1/scm/config';

/** Read the global dead-stock threshold (days) that drives the "dead" status. */
export async function getDeadStockDays(): Promise<number> {
  const res = await apiFetch(`${CONFIG_BASE}/dead-stock-days`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load dead-stock setting'));
  const body = (await res.json()) as { dead_stock_days: number };
  return body.dead_stock_days;
}

/** Update the global dead-stock threshold (days). Requires scm.config.manage. */
export async function setDeadStockDays(days: number): Promise<number> {
  const res = await apiFetch(`${CONFIG_BASE}/dead-stock-days`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dead_stock_days: days }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save dead-stock setting'));
  const body = (await res.json()) as { dead_stock_days: number };
  return body.dead_stock_days;
}
