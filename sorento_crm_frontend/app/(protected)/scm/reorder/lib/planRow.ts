/**
 * ============================================================================
 * SCM M8 - presentational plan-row types + adapters (Phase-2, real backend)
 * ============================================================================
 * The M8 planning grid renders a light `PlanRow` shape rather than the full
 * `ReorderRecommendation` so the div-grid, drag, and inline popovers stay lean.
 * These adapters map the REAL run payload (recommendations + disposition rows)
 * onto that shape. The two heavy drills (net breakdown, days-cover demand) are
 * NOT baked onto the row - they're fetched lazily from their own endpoints when
 * a popover opens (see `services/drillService.ts` + `hooks/useDrills.ts`), so
 * the plan loads fast and the frozen numbers are always live.
 *
 * Replaces the Phase-1 `__mocks__/m8Plan.ts` fixtures.
 * ============================================================================
 */
import type { ReorderRecommendation, SupplierChoice } from '../types/reorder.types';

/** The chosen supplier on a plan row. `unit_cost` null = needs-cost. */
export interface PlanRowSupplier {
  code: string;
  name: string;
  unit_cost: number | null;
  lead_time_days: number;
}

/** Order-qty derivation inputs shown in the order-qty drill (M8-A4) - read off the
 *  recommendation's already-frozen fields, never recomputed on the client. */
export interface PlanRowOrderQtyInputs {
  safety_stock: number | null;
  reorder_point: number | null;
  order_up_to: number | null;
  rounded_qty: number;
  moq: number | null;
  order_multiple: number | null;
}

/** Supplier swap option for the inline edit popover (from the rec's alternatives). */
export interface PlanRowSupplierOption {
  value: string; // supplier CODE (what /adjust's override_supplier_id wants)
  label: string;
  unit_cost: number;
  /** The money `unit_cost` is in. Null on a row that predates the book holding more than
   *  one currency, which means it already meant ringgit. Carried because the shortlist is
   *  a price COMPARISON: bare, a USD 8.00 option reads cheaper than an RM 10.00 one. */
  currency: string | null;
  /** The same price restated in the base currency, which is what the ranking compared.
   *  Null when the candidate's currency has no rate on file. */
  unit_cost_base: number | null;
  lead_time_days: number;
}

/**
 * One buy recommendation the user reviews + steers in the M8 plan grid.
 * `order_qty` / `supplier` / `unit_cost` are the only fields an inline edit or a
 * market bump changes; `original_order_qty` keeps the engine's frozen value for
 * the struck-through "was" display. `rec` is the source recommendation, forwarded
 * to the detail dialog + the decision endpoints so nothing is re-derived.
 */
export interface M8PlanRow {
  id: string; // recommendation id - powers explain-net + detail + decisions
  rank: number;
  sku: string;
  product_name: string;
  type: 'buy';
  order_qty: number;
  original_order_qty: number;
  /** What the SUPPLIER charges, in `currency`. Shown on the row; never summed. */
  unit_cost: number | null;
  currency: string | null;
  /**
   * The same price in the BUDGET's currency. This is the only figure cash is computed
   * from: the budget is one pot of ringgit and the book prices mostly in dollars, so
   * multiplying the supplier's own figure understates a buy roughly fourfold.
   * Null when the price could not be converted, which means no cash figure at all.
   */
  unit_cost_base: number | null;
  net: number | null;
  days_cover: number | null;
  /** Frozen average daily demand the engine used to compute `days_cover`
   *  (`net / forecast_daily_demand = days_cover`). Drives the days-cover drill's
   *  headline avg/day + arithmetic so the equation reconciles exactly - the live
   *  `explain/demand` recompute (a different window) is evidence-only. */
  forecast_daily_demand: number | null;
  warehouse: string;
  supplier: PlanRowSupplier;
  order_qty_inputs: PlanRowOrderQtyInputs;
  /** Supplier swap options for the inline edit popover (rec's ranked alternatives). */
  alternatives: PlanRowSupplierOption[];
  /** Data-only ids for the days-cover demand drill (never rendered). */
  product_id: string | null;
  warehouse_id: string | null;
  /** The source recommendation - passed straight to the detail dialog + decisions. */
  rec: ReorderRecommendation;
}

/**
 * Cash impact for a row = live qty x the price IN THE BUDGET'S CURRENCY.
 *
 * Null when there is no convertible price, whether because nobody has priced the item or
 * because we hold no rate for the money it is priced in. Both park the row in front of a
 * human, which is right; a face-value number would quietly fund it at a quarter of cost.
 */
export function m8CashImpact(
  row: Pick<M8PlanRow, 'order_qty' | 'unit_cost' | 'unit_cost_base'>,
): number | null {
  if (row.unit_cost_base === null || row.unit_cost_base === undefined) return null;
  return row.order_qty * row.unit_cost_base;
}

/** Human warehouse label for a rec (never a UUID); a network rec reads "Network". */
function warehouseLabel(rec: ReorderRecommendation): string {
  if (rec.is_network) return 'Network';
  return rec.warehouse_name ?? rec.warehouse_code ?? 'Network';
}

/** Supplier swap options from a rec's chosen supplier + ranked alternatives. Only
 *  costed suppliers are offered (an uncosted swap can't be budgeted). */
export function supplierOptionsFor(rec: ReorderRecommendation): PlanRowSupplierOption[] {
  const all: SupplierChoice[] = [
    ...(rec.supplier ? [rec.supplier] : []),
    ...rec.alternatives,
  ];
  const seen = new Set<string>();
  const out: PlanRowSupplierOption[] = [];
  for (const s of all) {
    if (!s.supplier_code || seen.has(s.supplier_code) || s.unit_cost === null) continue;
    seen.add(s.supplier_code);
    out.push({
      value: s.supplier_code,
      label: s.supplier_name ?? s.supplier_code,
      unit_cost: s.unit_cost,
      currency: s.currency ?? null,
      unit_cost_base: s.unit_cost_base ?? null,
      lead_time_days: s.lead_time_days ?? 0,
    });
  }
  return out;
}

/** Adapt a real buy `ReorderRecommendation` into the M8 plan grid row. */
export function recToPlanRow(rec: ReorderRecommendation): M8PlanRow {
  const orderQty = rec.order_qty ?? 0;
  const supplier: PlanRowSupplier = {
    code: rec.supplier?.supplier_code ?? '',
    name: rec.supplier?.supplier_name ?? 'No supplier',
    unit_cost: rec.supplier?.unit_cost ?? rec.unit_cost ?? null,
    lead_time_days: rec.supplier?.lead_time_days ?? rec.lead_time_days ?? 0,
  };
  return {
    id: rec.id,
    rank: rec.rank ?? 0,
    sku: rec.sku,
    product_name: rec.product_name,
    type: 'buy',
    order_qty: orderQty,
    original_order_qty: orderQty,
    unit_cost: rec.unit_cost ?? null,
    currency: rec.currency ?? rec.supplier?.currency ?? null,
    // Prefer the run's own frozen cash figure over re-deriving it: it was computed with
    // the rate the run used, and re-deriving from today's would explain a decision
    // nobody made. Falls back to the chosen supplier's converted price.
    unit_cost_base:
      rec.supplier?.unit_cost_base ??
      (rec.cash_impact !== null && rec.order_qty ? rec.cash_impact / rec.order_qty : null),
    net: rec.net_position,
    days_cover: rec.days_of_cover,
    forecast_daily_demand: rec.forecast_daily_demand,
    warehouse: warehouseLabel(rec),
    supplier,
    order_qty_inputs: {
      safety_stock: rec.safety_stock,
      reorder_point: rec.reorder_point,
      order_up_to: rec.order_up_to,
      rounded_qty: orderQty,
      moq: rec.moq,
      order_multiple: rec.order_multiple,
    },
    alternatives: supplierOptionsFor(rec),
    product_id: rec.product_id ?? null,
    warehouse_id: rec.warehouse_id ?? null,
    rec,
  };
}

// ---------------------------------------------------------------------------
// Disposition (Stock allocation) rows - read-only list.
// ---------------------------------------------------------------------------

export type M8DispositionAction = 'discontinue' | 'promo' | 'hold';

export interface M8DispositionRow {
  id: string;
  sku: string;
  product_name: string;
  action: M8DispositionAction;
  qty: number;
  warehouse_code: string;
  warehouse_name: string;
  days_cover: number | null;
  reason: string;
}

/**
 * A disposition with a real call-to-action, vs an FYI "hold" (M8-F18). Today the
 * actionable actions are Discontinue (dead stock) and Promote/reallocate; "hold"
 * (overstock just above the cover ceiling) needs no action and is demoted to a
 * collapsed FYI section + excluded from the headline Stock-allocation count. The
 * M9 inter-warehouse transfer will add another actionable action here when built.
 */
export function isActionableDisposition(action: M8DispositionAction): boolean {
  return action === 'discontinue' || action === 'promo';
}

/** Actionable (Discontinue / Promote) vs FYI hold rows, order preserved (M8-F18). */
export interface M8DispositionSplit {
  actionable: M8DispositionRow[];
  hold: M8DispositionRow[];
}

/** Split allocation rows into actionable vs FYI hold - drives the grid's two
 *  sections and the tile's actionable-only count (M8-F18). */
export function splitDispositionRows(rows: M8DispositionRow[]): M8DispositionSplit {
  const actionable: M8DispositionRow[] = [];
  const hold: M8DispositionRow[] = [];
  for (const row of rows) {
    (isActionableDisposition(row.action) ? actionable : hold).push(row);
  }
  return { actionable, hold };
}

/** Adapt a disposition `ReorderRecommendation` into the read-only allocation row. */
export function recToDispositionRow(rec: ReorderRecommendation): M8DispositionRow {
  const action: M8DispositionAction =
    rec.disposition_action === 'discontinue'
      ? 'discontinue'
      : rec.disposition_action === 'promo'
        ? 'promo'
        : 'hold';
  return {
    id: rec.id,
    sku: rec.sku,
    product_name: rec.product_name,
    action,
    // Disposition rows carry excess units in net_position (no order qty).
    qty: rec.net_position ?? 0,
    warehouse_code: rec.warehouse_code ?? (rec.is_network ? 'Network' : ''),
    warehouse_name: rec.warehouse_name ?? (rec.is_network ? 'Network' : ''),
    days_cover: rec.days_of_cover,
    reason: rec.reason_label ?? '',
  };
}

// ---------------------------------------------------------------------------
// Market-bump proposal line (slice E) - one confirm-gated qty delta.
// ---------------------------------------------------------------------------

export interface M8ProposalLine {
  row_id: string; // recommendation id to /adjust
  sku: string;
  product_name: string;
  old_qty: number;
  new_qty: number;
  unit_cost: number;
  reason: string;
}

/**
 * A staged decision on a line, as the plan's own vocabulary.
 *
 * Lived in the results grid that S11 replaced. Kept here, beside the row model, because it is
 * a fact about a plan row rather than about any one component that draws it.
 */
export type M8RowDecision = 'accepted' | 'rejected' | null;

/** The draft purchase order a confirmed line landed in. */
export interface RowPoLink {
  po_number: string;
  po_id: string | null;
}
