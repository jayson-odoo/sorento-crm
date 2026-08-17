/**
 * SCM Purchasing and Fulfilment - Summary Order Report types (UAC Group C2 + C3).
 *
 * The printed sheet Mr Loo fills in with a pen, made decidable: one row per
 * product network wide, with every aggregate openable and the order quantity his
 * to set. The wire contract Phase 2 implements is documented at the top of
 * `services/summaryOrderService.ts`; this file is the field-for-field shape.
 *
 * Three rules are baked into the shapes below, all of them hard:
 *
 *   - **No ids.** Everything is addressed by human code (`product_code`,
 *     `supplier_code`, SO numbers, pool codes). `run_id` is the single exception
 *     and it is opaque: it identifies which week's report is being read (AC-C2.9)
 *     and is never rendered.
 *   - **Ordered and incoming stay separate** (AC-C2.2, revised 6 Aug 2026). Only
 *     `qty_in_transit` - the SPO allocation - drives the net position. A purchase
 *     order is an order placed, which the supplier may have shipped nothing
 *     against, so `qty_on_order` is displayed and never counted.
 *   - **A missing input is named, never zeroed.** Months of cover and container
 *     volume are nullable because the data genuinely is not there for most
 *     products (cover derivable for 62% of them, volume for 16%). A volume of 0
 *     reads as "no space needed" and a cover of 0 reads as "already out of
 *     stock", and both would be decisions taken on a figure nobody measured.
 */

/** One product, network wide (AC-C2.1). */
export interface OrderSummaryRow {
  product_code: string;
  product_name: string | null;
  /** Unit of measure, for the quantity figures. */
  uom: string | null;

  on_hand: number;
  /** Committed project demand, the sum of the lines behind the project drill. */
  project_demand: number;
  /** Outstanding dealer and retail orders, the sum of the lines behind that drill. */
  dealer_outstanding: number;
  /** Open Supply PO lines. Still negotiable: can be re-dated or cancelled. */
  qty_on_order: number;
  /** Inbound shipment lines. Loaded, so no longer negotiable. */
  qty_in_transit: number;

  /**
   * The dated shortfall from the Coverage Timeline (AC-C1), NOT `on hand + on
   * order - demand`. A positive net position can still be short when the supply
   * that lifts it is dated after the demand it is read as covering.
   */
  shortfall: number;
  /** What the engine proposes, after MOQ and order-multiple rounding (AC-C3). */
  suggested_qty: number;

  /** What a person decided. Null until they decide (AC-C2.1). */
  chosen_qty: number | null;
  chosen_supplier_code: string | null;
  chosen_supplier_name: string | null;
  /** Human name of whoever decided, never a user id (AC-C2.8). */
  decided_by: string | null;
  /** Naive Malaysia wall-clock ISO timestamp of the decision (AC-C2.8). */
  decided_at: string | null;

  /**
   * Average daily demand from `scm.demand_stat`. Null where the product has no
   * demand statistic, which is 38% of the book, so months of cover cannot be
   * stated for it and must say so rather than print 0.
   */
  avg_daily_demand: number | null;
  /**
   * Cubic metres per unit, derived from the product's recorded dimensions. Null
   * where no dimensions are recorded, which is 84% of the book.
   */
  unit_volume_cbm: number | null;
  /** Pool code any spare above the shortfall lands in (AC-C2.7). */
  spare_lands_at: string | null;

  /** How many lines each aggregate opens to, so the icon can carry a count. */
  project_demand_line_count: number;
  dealer_outstanding_line_count: number;
  /** Worst ageing in the dealer drill, so the row can flag it without listing it. */
  max_days_outstanding: number | null;
}

/** The whole report for one run, as of one date (AC-C2.9). */
export interface OrderSummaryReport {
  /** Opaque run key. Identifies which week is being read; never rendered. */
  run_id: string;
  /**
   * ISO date (YYYY-MM-DD) the position was FROZEN for. Null when the run froze no
   * rows: inventing today's date would label a book that was never built.
   */
  as_of: string | null;
  /** Naive Malaysia wall-clock ISO timestamp of the computation. Null with `as_of`. */
  generated_at: string | null;
  rows: OrderSummaryRow[];
}

/** Which aggregate a drill decomposes. */
export type OrderSummaryDemandKind = 'project' | 'dealer';

/** One contributing project line (AC-C2.3). */
export interface ProjectDemandLine {
  project_name: string;
  so_number: string;
  qty: number;
  /** ISO date the line is required on site. Null when the SO carries no date. */
  required_date: string | null;
}

/** One contributing dealer or retail line (AC-C2.4). */
export interface DealerDemandLine {
  dealer_name: string;
  so_number: string;
  qty: number;
  /**
   * Whole days since the order was raised. The column the printed sheet has no
   * room for, and the reason two units can outrank two hundred.
   */
  days_outstanding: number;
  /** ISO date the order was raised, so the ageing can be checked. */
  ordered_date: string | null;
}

/**
 * What one aggregate opens to. Server-sorted: project lines by required date,
 * dealer lines WORST-FIRST by days outstanding (AC-C2.4), so the client never
 * re-sorts and the two can never disagree.
 */
export interface OrderSummaryDemandDrill {
  product_code: string;
  kind: OrderSummaryDemandKind;
  /** Must equal the row's aggregate. The row figure is derived from these lines. */
  total_qty: number;
  /** Populated when `kind` is `project`, empty otherwise. */
  project_lines: ProjectDemandLine[];
  /** Populated when `kind` is `dealer`, empty otherwise. */
  dealer_lines: DealerDemandLine[];
}

/**
 * One supplier the item could be bought from (AC-C2.5).
 *
 * Every cost here is **ex-works in `currency`** (AC-C3.4). Neither figure is a
 * landed cost: freight and duty are not in the purchase order.
 */
export interface SupplierCandidate {
  supplier_code: string;
  supplier_name: string;
  /** ISO 4217 code the two costs are quoted in. */
  currency: string;
  /** Ordered cost, from `purchase_order_lines.unit_cost` (AC-C3.1). */
  last_po_cost: number | null;
  /** ISO date of that PO. What tells a buyer whether the item moves at all. */
  last_po_date: string | null;
  last_po_number: string | null;
  /** Incoming cost, stamped from the packing list at allocation (AC-C3.2). */
  last_incoming_cost: number | null;
  /**
   * ISO 4217 code `last_incoming_cost` is quoted in, from the shipment line itself. NOT
   * `currency`, which is the PO's: a supplier's pre-loading list prices in their own money
   * (often CNY) while the order sits in another, so labelling the incoming figure with the
   * PO's code states a price that was never quoted. Null when the shipment line states
   * none, and then the figure is shown without a currency rather than under a guess.
   */
  last_incoming_currency: string | null;
  last_incoming_date: string | null;
  /**
   * Incoming minus ordered, in `currency`. A first-class output: a supplier whose
   * incoming cost drifts above its ordered cost repriced after we committed
   * (AC-C3.3). Null when either side is missing.
   */
  cost_variance: number | null;
  /** Fraction of deliveries that landed on or before the promised date, 0 to 1. */
  on_time_rate: number | null;
  lead_time_days: number | null;
  /**
   * How many lines of THIS item this supplier has actually delivered. Zero means
   * they have never delivered it, which must be said rather than letting a low
   * `last_po_cost` make them look merely cheap (AC-C2.5).
   */
  delivered_line_count: number;
  /** Server verdict on `last_po_date` against `stale_after_days` (AC-C2.6). */
  is_stale: boolean;
  /** Whole days since `last_po_date`. Null when there is no last PO. */
  stale_days: number | null;
  moq: number | null;
  order_multiple: number | null;
}

/** The candidate set for one product. */
export interface OrderSummarySuppliers {
  product_code: string;
  /** The threshold behind `is_stale`, so the screen can say what stale means. */
  stale_after_days: number;
  candidates: SupplierCandidate[];
}

/** What a decision writes (AC-C2.8). */
export interface OrderSummaryDecisionInput {
  /** Which report the decision belongs to. Opaque, never rendered. */
  run_id: string;
  chosen_qty: number;
  supplier_code: string;
}

/** What the server echoes back, so the row can be updated without a refetch. */
export interface OrderSummaryDecisionResult {
  product_code: string;
  chosen_qty: number;
  /** Kept beside the chosen figure, never replaced by it (AC-C2.8). */
  suggested_qty: number;
  chosen_supplier_code: string;
  chosen_supplier_name: string;
  decided_by: string;
  decided_at: string;
}
