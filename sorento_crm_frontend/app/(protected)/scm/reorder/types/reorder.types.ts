/**
 * SCM M3 — Reorder planning types (read-only run + results).
 *
 * These mirror the Phase-2 backend contract documented at the top of
 * `services/reorderRunService.ts`. M3 UI is READ-ONLY — no Accept/Adjust/Dismiss
 * (M4), no LLM prose (M5). Every money figure renders one-line via `fmtMoney`,
 * every count/qty is tabular-nums, and SKU/warehouse are human codes (no UUIDs).
 */

/** Run lifecycle. The background RQ job transitions running → completed | failed. */
export type ReorderRunStatus = 'running' | 'completed' | 'failed';

/** The four evaluation stages surfaced live while the job runs. Purely for the
 *  progress stepper — the backend exposes a coarse `stage` index/label. */
export type ReorderRunStage =
  | 'resolving_policies'
  | 'computing_reorder_points'
  | 'selecting_suppliers'
  | 'writing_recommendations';

/** Recommendation kind. `buy` = triggered reorder; `disposition` = dead/overstock;
 *  `exception` = a would-be buy with no linked supplier (flagged, nothing to order). */
export type ReorderRecType = 'buy' | 'disposition' | 'exception';

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
 *  zeroed) when unavailable — e.g. `margin` for an uncosted SKU (`present:false`,
 *  `value:null`) — so it never dilutes the score (graceful-degrade). */
export type RankFactorKey = 'urgency' | 'margin' | 'abc' | 'priority' | 'committed' | 'market';

/** One weighted factor behind a recommendation's rank_score. Surfaced so a novice
 *  can see WHICH factors were present and which dominated the ranking. */
export interface RankFactor {
  key: RankFactorKey;
  /** Configured weight from the active cash_ranking_policy (0–1). */
  weight: number;
  /** Normalized factor value 0–1; null when the factor was unavailable. */
  value: number | null;
  /** False when the factor was dropped (e.g. margin with no cost). */
  present: boolean;
}

/** M4 funding disposition, applied live at view-time against the slid budget.
 *  `needs_cost` = an uncosted buy that CANNOT be cash-ranked (M4-D16) — it's a
 *  real must-buy but un-priced, so it never funds/defers or touches the budget.
 *  null = not yet allocated (no budget applied). */
export type FundingStatus = 'funded' | 'deferred' | 'needs_cost' | null;

/** One candidate supplier — the selected one plus ranked alternatives. */
export interface SupplierChoice {
  supplier_code: string;
  supplier_name: string;
  /** Landed unit cost driving the cash impact. null when uncosted. */
  unit_cost: number | null;
  /** Lead time (measured M2 → declared → policy default). null when unknown. */
  lead_time_days: number | null;
  /** Composite performance score 0–100 (M2). null when no sample. */
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
  /** Stable row id (never rendered — used only for row keys / detail fetch). */
  id: string;
  type: ReorderRecType;
  /** Human product code — never a UUID. */
  sku: string;
  product_name: string;
  abc_class: 'A' | 'B' | 'C' | null;
  xyz_class: 'X' | 'Y' | 'Z' | null;
  /** Warehouse code for a per-warehouse row; null for an aggregated network row. */
  warehouse_code: string | null;
  warehouse_name: string | null;
  is_network: boolean;
  /** Populated on network buy rows — the suggested per-warehouse split. */
  allocation: AllocationLine[] | null;
  /** Suggested buy quantity (null for disposition rows) — AFTER MoQ / pack rounding. */
  order_qty: number | null;
  /** Pre-rounding buy qty (order-up-to − net), before MoQ / pack-multiple rounding.
   *  Populated on buy rows only — powers the explanation popup's qty arithmetic. */
  recommended_qty: number | null;
  /** Reorder point — populated on `reorder_point` trigger rows; null otherwise. */
  reorder_point: number | null;
  /** Min level — populated on `min_max` trigger rows; null otherwise. */
  min_qty: number | null;
  /** Max level — populated on `min_max` trigger rows; null otherwise. */
  max_qty: number | null;
  /** Order-up-to level — populated on `periodic_review` trigger rows; null otherwise. */
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
  /** The selected supplier — null flags a NO-SUPPLIER exception. */
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
  /** Service level (0–1) behind a statistical safety stock. */
  service_level: number | null;
  /** Buffer days behind a fixed-days safety stock. */
  safety_days: number | null;
  /** Review-period days folded into the order-up-to target. */
  review_days: number | null;
  /** Supplier minimum order quantity applied when rounding. */
  moq: number | null;
  /** Supplier pack / order multiple applied when rounding. */
  order_multiple: number | null;
  /** Policy type that drove the decision (reorder_point / periodic_review / min_max). */
  policy_type: ReorderReason | null;
  /** Which supplier-selection rule chose the supplier. */
  supplier_selection: 'primary' | 'best_score' | 'lowest_cost' | null;

  // --- M4 cash co-pilot (buy recommendations only) ----------------------------
  // Frozen at run time (rank_score / rank / rank_factors / cash_impact) except
  // `funding_status`, which is applied LIVE at view-time against the slid budget
  // (M4-D2/D3). Non-buy rows (disposition / exception) leave these null — they
  // don't participate in cash ranking or funding.
  /** Landed unit cost driving cash_impact; null for an uncosted SKU (margin dropped). */
  unit_cost: number | null;
  /** order_qty × unit_cost, in RM; null when the SKU is uncosted. */
  cash_impact: number | null;
  /** 1-based rank by frozen rank_score (1 = fund first). null on non-buy rows. */
  rank: number | null;
  /** Sequential 1..N position WITHIN its displayed section (funded / deferred),
   *  assigned client-side at view-time so the user sees a clean priority order
   *  (1, 2, 3…) rather than the raw global rank. Null until allocated. */
  display_rank?: number | null;
  /** Frozen weighted score 0–1 (M4-D14 graceful-degrade). null on non-buy rows. */
  rank_score: number | null;
  /** Live funding disposition against the current budget (M4-D3). */
  funding_status: FundingStatus;
  /** Days until this SKU stocks out at forecast demand — surfaced on deferred rows
   *  as the visible risk of NOT funding it (M4-D4). null when not derivable. */
  days_to_stockout: number | null;
  /** The factors that fed rank_score, with present/dropped flags (explainability). */
  rank_factors: RankFactor[];
  /** M7 — the market signal that moved this rank (opt-in runs only); null otherwise. */
  market_signal?: string | null;
}

/** Roll-up counts + cash impact for the completed run. */
export interface ReorderRunSummary {
  buy_count: number;
  disposition_count: number;
  exception_count: number;
  /** Σ(order_qty × unit_cost) across buy rows with a supplier, in RM. */
  total_cash_impact: number;
  /** Total rows to review (buy + disposition) — powers the completion CTA. */
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

/** Request to launch a run. `budget_id` is greyed in the UI until M4. */
export interface CreateReorderRunRequest {
  warehouse_codes: string[];
  buy_scope: BuyScope;
  /** M4 — always null in M3. */
  budget_id?: string | null;
  /** M7 — opt-in: factor market-trend signals into the funding priority (rank), not qty. */
  include_market?: boolean;
}
