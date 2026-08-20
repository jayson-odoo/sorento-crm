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
 *
 * Stage 2 (front planning) adds three things to the same shapes, and adds no row
 * identity: the product row is still exactly one row per product (AC-E03).
 *
 *   - **Channel is analysis inside the row, never row identity.** Project, Retail
 *     and Unclassified are separate DEMAND readings; stock, incoming SPO, PO supply
 *     and the reorder level stay single shared facts counted once (AC-F07).
 *   - **The run's stamped grain travels with the report.** `decision_grain` says
 *     which grain owns the decision, and it is a property of the run rather than a
 *     control offered to the buyer (AC-F01).
 *   - **Precision is frozen, not live.** `uom_decimal_places` is the product's base
 *     UOM divisibility as it was when the run was calculated, and it is what both
 *     the quantity field and the location split obey (AC-F12).
 */

import type { PlanGrain } from '../lib/planGrain';

/** One product, network wide (AC-C2.1). */
export interface OrderSummaryRow {
  product_code: string;
  product_name: string | null;
  /** Unit of measure, for the quantity figures. */
  uom: string | null;

  on_hand: number;
  /**
   * Open PROJECT-class SO quantity, classified by the SO's persisted `demand_class`
   * (AC-E03). One of the row's two Project measures - the other is `project_buy_qty` -
   * and they are shown side by side because they answer different questions: what the
   * projects have ordered, and what CS has confirmed we must buy for them.
   */
  project_demand: number;
  /**
   * Open RETAIL-class SO quantity. The stored column is still `dealer_outstanding`;
   * the API and every screen call it retail, which is the user's word (AC-E03).
   */
  retail_outstanding: number;
  /**
   * Demand whose SO carries no persisted `demand_class`. Visible as an exception and
   * excluded from the actionable suggestion until it is classified (AC-E06). NULL on
   * a legacy run, which has no breakdown and is never backfilled.
   */
  unclassified_demand_qty: number | null;
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
  /**
   * What the engine proposes for the PRODUCT, after MOQ and the order multiple are
   * applied ONCE to the product total (AC-E06 / AC-F11) at `uom_decimal_places`.
   * Never the sum of per-location rounded quantities.
   */
  suggested_qty: number;
  /**
   * Confirmed unplaced Buy on Project-class lines, summed across fulfilment
   * locations (AC-E04). Firm demand: Retail free-supply netting never reduces it.
   * NULL on a legacy run.
   */
  project_buy_qty: number | null;
  /** Normally netted Retail replenishment, summed across locations. NULL on legacy. */
  retail_replenishment_qty: number | null;
  /** Earliest required date behind `project_buy_qty`. NULL when it is 0 or legacy. */
  earliest_project_need_date: string | null;
  /**
   * The product's base-UOM `decimal_places`, FROZEN when the run was calculated
   * (AC-F12). Chosen-quantity validation and the location split read this snapshot,
   * never live UOM master data, so editing the UOM later cannot change a frozen run.
   * NULL during rollout and on legacy runs, which resolves to 0.
   */
  uom_decimal_places: number | null;
  /**
   * The chosen quantity split back to locations by the allocator rerun (AC-F08).
   * The quantities sum EXACTLY to `chosen_qty`. NULL until a quantity is chosen, and
   * on a run whose decisions are owned by the per-location grain.
   */
  location_allocations: OrderSummaryLocationAllocation[] | null;

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
  retail_outstanding_line_count: number;
  /** How many SO lines carry no demand class, so the exception can be opened. */
  unclassified_line_count: number;
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
  /**
   * The grain STAMPED on this run when it was created, from the admin plan-grain
   * policy setting (AC-F01). Not the current policy value, and not a choice offered
   * here: the run keeps it forever. NULL only on a legacy run.
   */
  decision_grain: PlanGrain | null;
  /**
   * A run created before the front-planning contract. Its channel breakdown is
   * unavailable, is never inferred or backfilled, and it accepts no decision in
   * either grain (AC-F10).
   */
  is_legacy: boolean;
  rows: OrderSummaryRow[];
}

/** One location's share of a chosen product quantity. Sums exactly to `chosen_qty`. */
export interface OrderSummaryLocationAllocation {
  warehouse_code: string;
  warehouse_name: string;
  allocated_qty: number;
}

/**
 * One member location behind a product row (AC-F08).
 *
 * Demand is split by channel; supply is NOT. Stock, incoming SPO, PO and the reorder
 * level are single shared facts of the product-location and are counted once, which
 * is why they carry no channel dimension here (AC-F07).
 */
export interface OrderSummaryLocationRow {
  warehouse_code: string;
  warehouse_name: string;
  /** Channel demand at this location. NULL on a legacy run. */
  project_need: number | null;
  retail_need: number | null;
  unclassified_need: number | null;
  /**
   * The unconfirmed sheet-origin Project leg, already netted inside `retail_need` and
   * never an addend of it. Optional because a run frozen before the confirmed/sheet split
   * never stated it.
   */
  project_sheet_need?: number | null;
  /** Shared supply, counted once. */
  on_hand: number;
  incoming_spo: number;
  on_order_po: number;
  /** The location's own reorder level. NULL means nobody has set one, which is not 0. */
  reorder_level: number | null;
  /** Velocity behind the Retail netting. NULL where the product has no statistic. */
  avg_daily_demand: number | null;
  /** This location's share of the chosen quantity. NULL until a quantity is chosen. */
  allocated_qty: number | null;
}

/** What a product row's Locations drill opens to. */
export interface OrderSummaryLocations {
  product_code: string;
  /** The run's stamped grain, so the drill can say who owns the decision. */
  decision_grain: PlanGrain | null;
  is_legacy: boolean;
  uom: string | null;
  uom_decimal_places: number | null;
  /** The once-rounded product figure, repeated here so the drill reconciles. */
  suggested_qty: number;
  chosen_qty: number | null;
  locations: OrderSummaryLocationRow[];
}

/**
 * Which aggregate a drill decomposes.
 *
 * `dealer` is the legacy name of `retail` and is accepted on the wire so an older
 * caller keeps working; every screen says retail.
 */
export type OrderSummaryDemandKind = 'project' | 'retail' | 'unclassified' | 'dealer';

/** One contributing project line (AC-C2.3 / AC-D06 / AC-E07). */
export interface ProjectDemandLine {
  project_name: string;
  so_number: string;
  qty: number;
  /** ISO date the line is required on site. Null when the SO carries no date. */
  required_date: string | null;
  /** Human SO line number, so Purchasing can find the line it is looking at. */
  line_no: number | null;
  /** The fulfilment location the line's need sits at. */
  warehouse_code: string | null;
  /**
   * The decision revision and inquiry the Buy came from, as a human reference
   * ("Rev 2 / INQ-2026-0188") - never a UUID (AC-D06). Null on a line whose SO has
   * no confirmed decision, which is counted through the sheet leg instead.
   */
  decision_ref: string | null;
}

/** One SO line whose demand class is missing, shown as an exception (AC-E02). */
export interface UnclassifiedDemandLine {
  customer_name: string;
  so_number: string;
  line_no: number | null;
  qty: number;
  /** ISO date the order was raised. */
  ordered_date: string | null;
  /** Why it has no class, in the words the exception is recorded with. */
  exception: string;
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
  /** Populated when `kind` is `retail`, empty otherwise. */
  retail_lines: DealerDemandLine[];
  /** Legacy name of `retail_lines`, kept so an older payload still renders. */
  dealer_lines?: DealerDemandLine[];
  /** Populated when `kind` is `unclassified`, empty otherwise. */
  unclassified_lines: UnclassifiedDemandLine[];
  /**
   * Trailing-window historical order context (captain, 20 Aug follow-up): "for project
   * here, you need to show the past year project order for this item; for retail, the
   * last 3 months, for user to judge whether to top up the quantity ordered." Distinct
   * from `total_qty` (still-open demand) - this is the flow of orders PLACED over the
   * window, whatever their status today.
   */
  project_12m_qty?: number | null;
  retail_3m_qty?: number | null;
  project_window_months?: number | null;
  retail_window_months?: number | null;
  demand_context_as_of?: string | null;
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
  /**
   * The chosen quantity, at most `uom_decimal_places` fractional digits (AC-F12).
   * A finer figure is refused with 422; a write against a run decided at the other
   * grain, or a legacy run, is refused with 409.
   */
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
  /**
   * The chosen quantity split back to locations by the allocator rerun (AC-F12).
   * The quantities sum EXACTLY to `chosen_qty` - no rescaling formula is applied -
   * and they are returned with the decision so the split is visible the moment it
   * is recorded.
   */
  location_allocations: OrderSummaryLocationAllocation[];
}
