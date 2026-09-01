/**
 * SCM Policy Configuration - types.
 *
 * These mirror the Phase-2 backend contract documented at the top of
 * `services/scmPolicyService.ts`. Three policy families feed the reorder engine:
 *   1. reorder_policy     - scoped CRUD, resolved most-specific-active-wins.
 *   2. abc_xyz_policy      - single global classification-threshold row.
 *   3. supplier_scoring_policy - single global supplier-scoring row.
 * Plus a resolution preview that (Phase 2) calls the SAME resolver the run uses.
 *
 * No UUIDs are ever surfaced in the UI: SKU shows `product_code · name`, class
 * shows its category name, cell shows `A·X`, global shows an em dash. The SKU
 * picker holds `products.id` as a HIDDEN option value (resolver key), never
 * displayed. (Cursor rule: no UUIDs in FE UI; AC-NAV-4.)
 */

/** Precedence order: sku > abc_xyz_cell > product_class > global. */
export type ScopeType = 'sku' | 'product_class' | 'abc_xyz_cell' | 'global';

/**
 * `reorder_level` is the manual-planning basis - the GLOBAL row carries it whenever S1's
 * planning-mode switch is set to "manual" (backend migration 356). It is set through the
 * planning-mode switch, not created here, but the grid must still be able to LIST and EDIT
 * a row that carries it without falling over on an unrecognised enum value.
 */
export type PolicyType = 'reorder_point' | 'periodic_review' | 'min_max' | 'reorder_level';

export type SafetyStockMethod = 'fixed_days' | 'statistical' | 'manual';

export type SupplierSelection = 'primary' | 'best_score' | 'lowest_cost';

/** One reorder-policy row as returned by the list endpoint. */
export interface ReorderPolicyRow {
  id: string;
  scope_type: ScopeType;
  /**
   * Resolver comparison key per scope (never rendered raw):
   *   sku            → products.id (UUID)
   *   product_class  → product_categories.category_code
   *   abc_xyz_cell   → "A-X"
   *   global         → null
   */
  scope_ref: string | null;
  /** Human-readable target, no UUID. `-` for global. */
  scope_label: string;
  policy_type: PolicyType;
  /** Statistical service level 0-1 (exclusive); null unless statistical. */
  service_level: number | null;
  safety_stock_method: SafetyStockMethod;
  /** Buffer days for fixed_days; also the manual SS value carrier. */
  safety_days: number | null;
  review_period_days: number | null;
  forecast_window_days: number | null;
  /** S13d trajectory windows: months of orders deciding sustaining vs dying off.
   *  Null = code default (retail 3, project 12). */
  trajectory_window_retail_months: number | null;
  trajectory_window_project_months: number | null;
  /** S13e price-advice thresholds: when a last price is too old to trust, and what
   *  price difference is worth acting on. Null = code default (180 days, 5%). */
  price_stale_after_days: number | null;
  price_movement_threshold_pct: number | null;
  baseline_source: string | null;
  spike_handling: string | null;
  buy_scope: string | null;
  dead_stock_days: number | null;
  overstock_days: number | null;
  /** Min/Max overrides for a min_max policy. */
  min_override: number | null;
  max_override: number | null;
  priority: number;
  is_active: boolean;
  /** Hoisted out of the engine's `factor_toggles` JSONB. */
  supplier_selection: SupplierSelection;
  lead_time_default_days: number | null;
}

/** Write payload - same as the row minus server-owned id + scope_label. */
export type ReorderPolicyWrite = Omit<ReorderPolicyRow, 'id' | 'scope_label'>;

/** Global classification thresholds (single active row). */
export interface AbcXyzPolicy {
  /** Cumulative-value cut for class A (0-1). */
  abc_a_pct: number;
  /** Cumulative-value cut for class B (0-1); A + B < 1. */
  abc_b_pct: number;
  /** Demand CV ceiling for class X. */
  xyz_x_max: number;
  /** Demand CV ceiling for class Y (X ≤ Y). */
  xyz_y_max: number;
  /** False when no row exists yet - the panel shows seeded defaults. */
  exists: boolean;
}

export type AbcXyzWrite = Omit<AbcXyzPolicy, 'exists'>;

/** Global supplier-scoring weights (single active row). */
export interface SupplierScoringPolicy {
  /** On-time delivery weight (0-1); delivery + quality = 1. */
  delivery_weight: number;
  /** Quality weight (0-1). */
  quality_weight: number;
  /** Days a delivery may slip and still count "on time". */
  grace_days: number;
  /** Minimum PO→GR samples before a score is trusted. */
  min_sample_size: number;
  exists: boolean;
}

export type SupplierScoringWrite = Omit<SupplierScoringPolicy, 'exists'>;

/** The ONE universal planning-mode switch (S1). Reads/writes the GLOBAL
 *  reorder_policy row's `policy_type`: 'auto' -> reorder_point, 'manual' ->
 *  reorder_level. Per-product override rows still win over this default. */
export interface PlanningMode {
  mode: 'auto' | 'manual';
}

export type PlanningModeWrite = PlanningMode;

/**
 * Where a plan row's "use stock" may draw from before it buys.
 *
 * > "why am I allowed to use stock from other locations? It is either I use stock from BRW,
 * >  or buy."
 *
 * `own_pool` keeps cover inside the row's own site (its pool); `all_locations` offers every
 * location that holds spare stock. Global setting, on the same GLOBAL reorder_policy row as
 * the planning mode.
 */
export type CoverScope = 'own_pool' | 'all_locations';

export interface CoverScopeSetting {
  cover_scope: CoverScope;
}

export type CoverScopeWrite = CoverScopeSetting;

/**
 * The single active `scm.priority_policy` row - the ranking that decides both what goes in
 * a container and which purchase-order line arriving stock is assigned to (AC-H5). A PUT
 * writes a NEW revision and activates it; it never edits an old row in place, so `id` /
 * `name` on the response describe whichever revision is active NOW, not a record the FE can
 * address by id.
 *
 * `factors` / `demand_class_weights` are open records (JSONB on the backend) rather than
 * fixed fields, so a policy can carry a factor this UI does not yet render without losing it
 * on save - `PUT` sends back whatever `GET` returned, edited in place.
 */
export interface FulfilmentPriorityPolicy {
  name: string;
  /** Ranking-factor weights, keyed by factor (see `lib/labels.ts::FULFILMENT_FACTOR_ORDER`). */
  factors: Record<string, number>;
  /** Demand-class weights, keyed by `project` / `retail`. */
  demand_class_weights: Record<string, number>;
  /** A line required AFTER this calendar date is proposed as `Buy now`, untouched -
   *  the captain's "purchasing reorders until October". `null` = no coverage limit set. */
  reorder_coverage_until: string | null;
  /** Demand dated ON or AFTER this calendar date is TBA: it takes no supply, is never
   *  covered, and never donates. `YYYY-MM-DD`, NOT NULL on the backend - `Reset` on the
   *  panel restores `DEFAULT_TBA_DATE_FROM`. (Borrow ladder v7.1 R20 / AC-S1-2.) */
  tba_date_from: string;
  /** Days charged onto a non-own-location option's fulfil date, so a pool take that is not
   *  free reads a realistic day rather than the same day as an own-location one (31 Aug
   *  ruling R-B, migration 451). Default 0: no charge until a tenant configures one. */
  transfer_days: number;
  /** False only on a database that has never activated a fulfilment-priority policy. */
  exists: boolean;
}

export type FulfilmentPriorityWrite = Omit<FulfilmentPriorityPolicy, 'name' | 'exists'>;

/**
 * The column default of `scm.priority_policy.tba_date_from` (migration 443). The field is
 * NOT NULL, so `Reset` on the panel means "back to this", never "empty".
 */
export const DEFAULT_TBA_DATE_FROM = '2029-01-01';

/** Why a scope link did (or did not) win, for the preview teaching surface. */
export type ResolutionReason =
  | 'most-specific-active'
  | 'priority-tiebreak'
  | 'no-match'
  | 'inactive';

export interface ResolutionChainLink {
  scope_type: ScopeType;
  scope_ref: string | null;
  scope_label: string;
  matched: boolean;
  is_winner: boolean;
  reason: ResolutionReason;
}

/** Result of the resolution-preview tester. */
export interface ResolutionResult {
  product: { product_code: string; product_name: string };
  warehouse: { warehouse_code: string; warehouse_name: string } | null;
  abc_xyz_cell: string | null;
  product_class: string | null;
  winner: ReorderPolicyRow | null;
  chain: ResolutionChainLink[];
  /** AC-PREV-5 nice-to-have; DEFERRED in Phase 1 (omitted). */
  affected_sku_count?: number;
}
