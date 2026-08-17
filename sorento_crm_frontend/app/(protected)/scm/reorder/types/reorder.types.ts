/**
 * SCM M3 - Reorder planning types (read-only run + results).
 *
 * These mirror the Phase-2 backend contract documented at the top of
 * `services/reorderRunService.ts`. M3 UI is READ-ONLY - no Accept/Adjust/Dismiss
 * (M4), no LLM prose (M5). Every money figure renders one-line via `fmtMoney`,
 * every count/qty is tabular-nums, and SKU/warehouse are human codes (no UUIDs).
 */

/** Run lifecycle. The background RQ job transitions running → completed | failed. */
export type ReorderRunStatus = 'running' | 'completed' | 'failed';

/** The four evaluation stages surfaced live while the job runs. Purely for the
 *  progress stepper - the backend exposes a coarse `stage` index/label. */
export type ReorderRunStage =
  | 'resolving_policies'
  | 'computing_reorder_points'
  | 'selecting_suppliers'
  | 'writing_recommendations';

/** Recommendation kind. `buy` = triggered reorder; `disposition` = dead/overstock;
 *  `exception` = a would-be buy with no linked supplier (flagged, nothing to order);
 *  `needs_level` = the plan runs on the reorder-level basis and nobody has set one, so
 *  there is no quantity we are entitled to propose. */
export type ReorderRecType = 'buy' | 'covered' | 'disposition' | 'exception' | 'needs_level';

/** Why a buy fired, or why a disposition applies. Drives the "Triggered reason" cell. */
export type ReorderReason =
  | 'reorder_point'
  | 'periodic_review'
  | 'min_max'
  | 'dead'
  | 'overstock';

/** Disposition action for a non-buy recommendation. */
export type DispositionAction = 'discontinue' | 'promo' | 'hold';

/** Deterministic confidence band (xyz × data-sufficiency). Reuses the M2 badge look. */
export type ReorderConfidence = 'high' | 'medium' | 'low';

/** Buy scope for a run. `network` aggregates across the selected warehouses into
 *  one buy qty (auto-allocated); `warehouse` plans each warehouse independently. */
export type BuyScope = 'network' | 'warehouse';

/** M4 cash-ranking factor keys (M4-D1/D14). Each buy recommendation carries the
 *  set of factors that fed its frozen `rank_score`; a factor is DROPPED (not
 *  zeroed) when unavailable - e.g. `margin` for an uncosted SKU (`present:false`,
 *  `value:null`) - so it never dilutes the score (graceful-degrade). */
export type RankFactorKey = 'urgency' | 'margin' | 'abc' | 'priority' | 'committed' | 'market';

/** One weighted factor behind a recommendation's rank_score. Surfaced so a novice
 *  can see WHICH factors were present and which dominated the ranking. */
export interface RankFactor {
  key: RankFactorKey;
  /** Configured weight from the active cash_ranking_policy (0-1). */
  weight: number;
  /** Normalized factor value 0-1; null when the factor was unavailable. */
  value: number | null;
  /** False when the factor was dropped (e.g. margin with no cost). */
  present: boolean;
}

/** M4 funding disposition, applied live at view-time against the slid budget.
 *  `needs_cost` = an uncosted buy that CANNOT be cash-ranked (M4-D16) - it's a
 *  real must-buy but un-priced, so it never funds/defers or touches the budget.
 *  null = not yet allocated (no budget applied). */
export type FundingStatus = 'funded' | 'deferred' | 'needs_cost' | null;

/** One candidate supplier - the selected one plus ranked alternatives. */
export interface SupplierChoice {
  supplier_code: string;
  supplier_name: string;
  /**
   * Landed unit cost driving the cash impact.
   *
   * `null` means UNKNOWN and `0` means free, and they are different answers: an unknown
   * cost cannot be budgeted and lands in "Needs cost", while a free item funds at zero and
   * is planned like any other. Do not coalesce one into the other.
   */
  unit_cost: number | null;
  /** Where that figure came from: what we last paid, or a contract figure somebody typed. */
  unit_cost_source?: 'last_po' | 'contract' | null;
  /** The purchase order the cost was read off, when the source is `last_po`. */
  unit_cost_ref?: string | null;
  unit_cost_at?: string | null;
  currency?: string | null;
  /**
   * The same price restated in `base_currency`, which is the figure the ranking actually
   * used. Both travel: the supplier's own price is what the PO will say, and this is what
   * makes two suppliers in two currencies comparable at all.
   */
  unit_cost_base?: number | null;
  base_currency?: string | null;
  rate_to_base?: number | null;
  rate_as_of?: string | null;
  /** Set when this candidate's currency has no rate on file, so its price could not be
   *  compared. It never wins on a small number; the buyer is told which rate to add. */
  missing_rate_currency?: string | null;
  /** Lead time (measured M2 → declared → policy default). null when unknown. */
  lead_time_days: number | null;
  /** Composite performance score 0-100 (M2). null when no sample. */
  composite_score: number | null;
  is_primary: boolean;
  // --- scorecard detail (frozen; drives the "why this supplier" popover). May be
  //     null on older runs or suppliers with no M2 performance sample. ---
  /** PO→GR observations behind the composite score. */
  sample_size?: number | null;
  /** Deterministic confidence band for the score (high/medium/low). */
  confidence?: string | null;
  /** Where the lead time came from: measured / declared / default. */
  lead_time_source?: 'measured' | 'declared' | 'default' | string | null;
  /** Lead-time variance (days²) behind the reliability read. */
  lead_time_variance?: number | null;
  /** Supplier minimum order quantity. */
  moq?: number | null;
  /** Supplier pack / order multiple. */
  order_multiple?: number | null;
}

/** Per-warehouse split of a network buy qty. The qtys sum to `order_qty`. */
export interface AllocationLine {
  warehouse_code: string;
  warehouse_name: string;
  qty: number;
}

/** A single frozen recommendation row (AC-M3.8/M3.11 freeze the inputs). */
export interface ReorderRecommendation {
  /** Stable row id (never rendered - used only for row keys / detail fetch). */
  id: string;
  type: ReorderRecType;
  /** Human product code - never a UUID. */
  sku: string;
  product_name: string;
  abc_class: 'A' | 'B' | 'C' | null;
  xyz_class: 'X' | 'Y' | 'Z' | null;
  /** Warehouse code for a per-warehouse row; null for an aggregated network row. */
  warehouse_code: string | null;
  warehouse_name: string | null;
  /** Data-only ids - NEVER rendered. They let the days-cover demand drill call
   *  `GET /analytics/explain/demand?product_id=&warehouse_id=`. `warehouse_id` is
   *  null on a network (aggregated) row (demand then sums across warehouses). */
  product_id?: string | null;
  warehouse_id?: string | null;
  /** Data-only id - the pool this row's location belongs to
   *  (`COALESCE(pool_warehouse_id, id)`), so a cover source can be scoped to the row's own
   *  site. Null on a network row. */
  pool_warehouse_id?: string | null;
  is_network: boolean;
  /** Populated on network buy rows - the suggested per-warehouse split. */
  allocation: AllocationLine[] | null;
  /** Suggested buy quantity (null for disposition rows) - AFTER MoQ / pack rounding. */
  order_qty: number | null;
  /** Pre-rounding buy qty (order-up-to − net), before MoQ / pack-multiple rounding.
   *  Populated on buy rows only - powers the explanation popup's qty arithmetic. */
  recommended_qty: number | null;
  /** Reorder point - populated on `reorder_point` trigger rows; null otherwise. */
  reorder_point: number | null;
  /** Min level - populated on `min_max` trigger rows; null otherwise. */
  min_qty: number | null;
  /** Max level - populated on `min_max` trigger rows; null otherwise. */
  max_qty: number | null;
  /** Order-up-to level - populated on `periodic_review` trigger rows; null otherwise. */
  order_up_to: number | null;
  /** Net position (on-hand + inbound − committed). Can be negative; null when unknown. */
  net_position: number | null;
  /** Days of cover (null when not derivable). */
  days_of_cover: number | null;
  reason: ReorderReason | null;
  /** Human-readable trigger, e.g. "net ≤ ROP". null when not supplied. */
  reason_label: string | null;
  confidence: ReorderConfidence | null;
  /** PO→GR / demand sample behind the confidence band. */
  sample_size: number;
  /** The selected supplier - null flags a NO-SUPPLIER exception. */
  supplier: SupplierChoice | null;
  /** Ranked alternatives for M4 human override. */
  alternatives: SupplierChoice[];
  /** True when this row is a no-supplier exception (visibly flagged, no buy). */
  is_exception: boolean;
  /** Disposition action (disposition rows only). */
  disposition_action: DispositionAction | null;
  /** Advisory transfer hint, e.g. "consider transfer 60: WH-JB → WH-KL". */
  transfer_flag: string | null;

  // --- frozen derivation inputs (drive the plain-language explanation popup) ---
  // All frozen at run time (AC-M3.11); read-only, never recomputed on the client.
  /** Forecast demand in units/day (avg over the forecast window). */
  forecast_daily_demand: number | null;
  /** Lead time used in the ROP maths (days). */
  lead_time_days: number | null;
  /** Where the lead time came from: measured / declared / default. */
  lead_time_source: 'measured' | 'declared' | 'default' | null;
  /** Safety-stock units baked into the reorder point. */
  safety_stock: number | null;
  /** Safety-stock method actually applied (may differ from the policy on fallback). */
  safety_stock_method: 'fixed_days' | 'statistical' | 'manual' | null;
  /** Human note when the requested SS method fell back (e.g. thin sample). */
  safety_stock_fallback: string | null;
  /** Service level (0-1) behind a statistical safety stock. */
  service_level: number | null;
  /** Buffer days behind a fixed-days safety stock. */
  safety_days: number | null;
  /** Review-period days folded into the order-up-to target. */
  review_days: number | null;
  /** Supplier minimum order quantity applied when rounding. */
  moq: number | null;
  /** Supplier pack / order multiple applied when rounding. */
  order_multiple: number | null;
  /**
   * Policy basis that drove the decision. Usually a `ReorderReason`; also `reorder_level`
   * on a manual-mode line (S1's global toggle, or a per-product override) - the engine has
   * supported that basis since before S1, this type simply had not caught up to it.
   */
  policy_type: ReorderReason | 'reorder_level' | null;
  /** Which supplier-selection rule chose the supplier. */
  supplier_selection: 'primary' | 'best_score' | 'lowest_cost' | null;
  /**
   * Why this supplier and not the runner-up, frozen at run time.
   *
   * Frozen rather than re-derived, because the costs on screen can move after the run and
   * a reason recomputed from today's figures would explain a decision nobody made.
   * `saving_per_unit` is present only when BOTH costs were known - the gap to an unpriced
   * runner-up is unknowable, not infinite - and `only_supplier` means there was nothing to
   * compare against, so "cheaper" would be a fabrication.
   */
  supplier_reason?: {
    basis:
      | 'lowest_cost'
      | 'best_score'
      | 'primary'
      | 'only_supplier'
      | 'no_supplier'
      /** Every candidate was priced in money we hold no rate for, so nothing was ranked
       *  on cost and saying "cheapest" would be a claim we cannot support. */
      | 'no_comparable_cost'
      | string;
    runner_up?: string | null;
    /** The runner-up's price as the SUPPLIER quotes it, in `runner_up_currency`. */
    runner_up_cost?: number | null;
    runner_up_currency?: string | null;
    /** The same price restated in `compared_in`, which is the figure the ranking used. */
    runner_up_cost_base?: number | null;
    /** The currency both prices were converted into before being compared. */
    compared_in?: string | null;
    /** Currencies among the candidates that have no rate on file, so the buyer knows
     *  which rate to add rather than deducing it from a row that will not fund. */
    missing_rates?: string[] | null;
    saving_per_unit?: number | null;
  } | null;

  // --- M4 cash co-pilot (buy recommendations only) ----------------------------
  // Frozen at run time (rank_score / rank / rank_factors / cash_impact) except
  // `funding_status`, which is applied LIVE at view-time against the slid budget
  // (M4-D2/D3). Non-buy rows (disposition / exception) leave these null - they
  // don't participate in cash ranking or funding.
  /** What the SUPPLIER charges, in `currency`. This is the figure the PO will carry. */
  unit_cost: number | null;
  /** The currency `unit_cost` is quoted in. Null reads as the base currency. */
  currency?: string | null;
  /**
   * What the buy draws from the budget, ALWAYS in `base_currency`.
   *
   * Deliberately in different money from `unit_cost`: the budget is one pot of ringgit,
   * and a USD buy counted at face value understates it roughly fourfold. Null when the
   * price could not be converted, which is `cost_status`.
   */
  cash_impact: number | null;
  base_currency?: string | null;
  /** The rate this run used, frozen, so the figures still explain themselves later. */
  rate_to_base?: number | null;
  rate_as_of?: string | null;
  /**
   * Why there is no cash figure, when there is none. `no_cost` (nobody has ever priced
   * it) and `no_rate` (priced, in money we cannot convert) are fixed on two different
   * screens, so one label would send half the rows to the wrong one.
   */
  cost_status?: 'ok' | 'no_cost' | 'no_rate' | null;
  /** `covered` rows only: the committed demand, and what the location already holds.
   *  The two numbers the use-stock-or-buy choice turns on. */
  /** The decision taken on a covered row: `use_stock` | `buy` | `proposed` (undecided).
   *  The row keeps its place in the list after a decision so it can be changed. */
  decision_status?: string | null;
  covered_committed?: number | null;
  covered_available?: number | null;
  /** How much of this row's demand arrived on a sales-order line naming no warehouse.
   *  The part of a buy most likely to be wrong, so it is stated rather than assumed. */
  unlocated_demand?: number | null;
  /** Who this location sells to: `dealer` or `project`. Cost, price and sales history
   *  all mean something different on each side of it. */
  segment?: string | null;
  /** The weekly checklist, frozen with the row so it still reads true next month.
   *  `incoming_spo` is stock on the water; `outstanding_po` is the ordered-not-received
   *  purchase book. Two different questions, kept apart. */
  on_hand?: number | null;
  incoming_spo?: number | null;
  outstanding_po?: number | null;
  outstanding_sales?: number | null;
  /** The level the buyer owns. Null means nobody has set one, which is NOT zero: the row
   *  arrives as `needs_level` rather than as a buy. */
  reorder_level?: number | null;
  reorder_level_source?: string | null;
  /** When the buyer's level was set. Not yet emitted by the backend (S3 ledger renders it
   *  conditionally so this can be threaded through later with no FE change). */
  reorder_level_set_at?: string | null;
  /** The reorder settings held on the PRODUCT record. Shown beside what the plan computed;
   *  the engine does not read them. Null means not set, which is not zero. */
  /** The window the daily demand rate was averaged over, so the row can show the units
   *  behind the rate rather than the rate alone. */
  demand_window_days?: number | null;
  master_reorder_level?: number | null;
  master_reorder_quantity?: number | null;
  /** What we last paid, and HOW it was attributed. `unattributed` is said out loud: most
   *  purchase history names no destination, so presenting it as the dealer or project cost
   *  would invent the very split the buyer asked for. */
  last_purchase_cost?: number | null;
  last_purchase_currency?: string | null;
  last_purchase_date?: string | null;
  last_purchase_ref?: string | null;
  last_purchase_basis?: 'own_segment' | 'unattributed' | 'never_purchased' | null;
  /** What three months of movement implies. Never applied on the buyer's behalf. */
  suggested_level?: number | null;
  suggestion_basis?: {
    months?: { month: string; qty: number }[];
    months_studied?: number;
    avg_monthly?: number;
    cover_months?: number;
    raw_level?: number;
    no_movement?: boolean;
  } | null;
  missing_rate_currencies?: string[];
  /** 1-based rank by frozen rank_score (1 = fund first). null on non-buy rows. */
  rank: number | null;
  /** Sequential 1..N position WITHIN its displayed section (funded / deferred),
   *  assigned client-side at view-time so the user sees a clean priority order
   *  (1, 2, 3…) rather than the raw global rank. Null until allocated. */
  display_rank?: number | null;
  /** Frozen weighted score 0-1 (M4-D14 graceful-degrade). null on non-buy rows. */
  rank_score: number | null;
  /** Live funding disposition against the current budget (M4-D3). */
  funding_status: FundingStatus;
  /** Days until this SKU stocks out at forecast demand - surfaced on deferred rows
   *  as the visible risk of NOT funding it (M4-D4). null when not derivable. */
  days_to_stockout: number | null;
  /** The factors that fed rank_score, with present/dropped flags (explainability). */
  rank_factors: RankFactor[];
  /** M7 - the market signal that moved this rank (opt-in runs only); null otherwise. */
  market_signal?: string | null;

  // --- Stage 2 front planning: the frozen demand-channel split (AC-F07) ---------
  // Demand is split by channel; SUPPLY IS NOT. `on_hand`, `incoming_spo`,
  // `outstanding_po` and `reorder_level` above stay single shared facts of the
  // product-location and gain no channel dimension, because counting the same stock
  // once per channel would double the supply the plan believes it has.
  /** Confirmed unplaced Project Buy at this location. Firm: never netted again. */
  project_need?: number | null;
  /** Retail-class need after normal netting. */
  retail_need?: number | null;
  /**
   * Demand whose SO carries no persisted class. Visible, and EXCLUDED from the
   * actionable need in both grains until it is classified (AC-F05 / AC-E06).
   */
  unclassified_need?: number | null;
  /**
   * True when this run is decided at the Product grain, or is legacy, so the
   * per-location row is a read and drill row rather than a decision surface
   * (AC-F02 / AC-F09). The per-location view is never retired by Product grain.
   */
  decisions_read_only?: boolean;
}

/** Roll-up counts + cash impact for the completed run. */
export interface ReorderRunSummary {
  buy_count: number;
  disposition_count: number;
  exception_count: number;
  /** Σ(order_qty × unit_cost) across buy rows with a supplier, in RM. */
  total_cash_impact: number;
  /** Total rows to review (buy + disposition) - powers the completion CTA. */
  recommendation_count: number;
}

/** The run record returned by create / poll. `stage` is UI-only progress. */
export interface ReorderRun {
  run_id: string;
  status: ReorderRunStatus;
  stage: ReorderRunStage;
  buy_scope: BuyScope;
  summary: ReorderRunSummary | null;
  /** Human error message when status = failed. */
  error: string | null;
}

/** Request to launch a run. `budget_id` is greyed in the UI until M4. Planning scope
 *  is fixed server-side (M8-D5) - `buy_scope` is no longer a request field. */
export interface CreateReorderRunRequest {
  warehouse_codes: string[];
  /**
   * Optional product scope (AC-B8a) - human product codes, never ids. Omitted or
   * empty means EVERY product, so the scheduled daily run is unchanged. Sent only
   * when non-empty; the Phase-2 backend adds the matching request field (today's
   * `CreateReorderRunRequest` schema ignores it).
   */
  product_codes?: string[];
  /** M4 - always null in M3. */
  budget_id?: string | null;
  /** M7 - opt-in: factor market-trend signals into the funding priority (rank), not qty. */
  include_market?: boolean;
}
