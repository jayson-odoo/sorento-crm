/**
 * SCM Policy Configuration - types.
 *
 * These mirror the Phase-2 backend contract documented at the top of
 * `services/scmPolicyService.ts`. Three policy families feed the reorder engine:
 *   1. reorder_policy       - scoped CRUD, resolved most-specific-active-wins.
 *   2. abc_xyz_policy        - single global classification-threshold row.
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

export type PolicyType = 'reorder_point' | 'periodic_review' | 'min_max';

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
