/**
 * Friendly labels + option lists for policy enums. Centralised so the grid,
 * modal, and preview all read the same human wording (never a raw enum, never a
 * UUID).
 */
import type {
  CoverScope,
  PolicyType,
  SafetyStockMethod,
  ScopeType,
  SupplierSelection,
} from '../types/policy.types';

export const SCOPE_TYPE_LABEL: Record<ScopeType, string> = {
  global: 'Global default',
  product_class: 'Product class',
  abc_xyz_cell: 'ABC-XYZ cell',
  sku: 'SKU',
};

export const POLICY_TYPE_LABEL: Record<PolicyType, string> = {
  reorder_point: 'Reorder point',
  periodic_review: 'Periodic review',
  min_max: 'Min-max',
  // Set by the planning-mode switch (Auto/Manual), never chosen here directly.
  reorder_level: 'Reorder level',
};

export const SAFETY_METHOD_LABEL: Record<SafetyStockMethod, string> = {
  fixed_days: 'Fixed days',
  statistical: 'Statistical',
  manual: 'Manual',
};

export const SUPPLIER_SELECTION_LABEL: Record<SupplierSelection, string> = {
  primary: 'Primary supplier',
  best_score: 'Best score',
  lowest_cost: 'Lowest cost',
};

// Scope choices offered in the Add modal - `global` is deliberately absent
// (the global default is edited, never created; AC-EDIT-1/AC-EDIT-4).
export const SCOPE_TYPE_OPTIONS: { value: Exclude<ScopeType, 'global'>; label: string }[] = [
  { value: 'sku', label: 'SKU' },
  { value: 'product_class', label: 'Product class' },
  { value: 'abc_xyz_cell', label: 'ABC-XYZ cell' },
];

export const POLICY_TYPE_OPTIONS: { value: PolicyType; label: string }[] = [
  { value: 'reorder_point', label: 'Reorder point' },
  { value: 'periodic_review', label: 'Periodic review' },
  { value: 'min_max', label: 'Min-max' },
  { value: 'reorder_level', label: 'Reorder level' },
];

export const SAFETY_METHOD_OPTIONS: { value: SafetyStockMethod; label: string }[] = [
  { value: 'fixed_days', label: 'Fixed days' },
  { value: 'statistical', label: 'Statistical' },
  { value: 'manual', label: 'Manual' },
];

// Where "use stock" may draw from before buying. Two options only, and the wording is the
// buyer's own: a site, or anywhere.
export const COVER_SCOPE_LABEL: Record<CoverScope, string> = {
  own_pool: 'Own site only',
  all_locations: 'Any location',
};

export const COVER_SCOPE_OPTIONS: { value: CoverScope; label: string }[] = [
  { value: 'own_pool', label: COVER_SCOPE_LABEL.own_pool },
  { value: 'all_locations', label: COVER_SCOPE_LABEL.all_locations },
];

export const SUPPLIER_SELECTION_OPTIONS: { value: SupplierSelection; label: string }[] = [
  { value: 'primary', label: 'Primary supplier' },
  { value: 'best_score', label: 'Best score' },
  { value: 'lowest_cost', label: 'Lowest cost' },
];

// Engine baseline / spike / buy-scope toggles (plain labels; values match the
// engine defaults seeded by reorder_engine.ensure_reorder_policy_defaults).
export const BASELINE_SOURCE_OPTIONS: { value: string; label: string }[] = [
  { value: 'continuous_only', label: 'Continuous demand only' },
  { value: 'all', label: 'All demand' },
];

export const SPIKE_HANDLING_OPTIONS: { value: string; label: string }[] = [
  { value: 'committed_only', label: 'Committed orders only' },
  { value: 'statistical', label: 'Statistical' },
  { value: 'ignore', label: 'Ignore' },
];

export const BUY_SCOPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'network', label: 'Network' },
  { value: 'warehouse', label: 'Per warehouse' },
];

export const ABC_OPTIONS = [
  { value: 'A', label: 'A' },
  { value: 'B', label: 'B' },
  { value: 'C', label: 'C' },
];

export const XYZ_OPTIONS = [
  { value: 'X', label: 'X' },
  { value: 'Y', label: 'Y' },
  { value: 'Z', label: 'Z' },
];

// Fulfilment-priority ranking factors, named the way the board's cell drawer names them
// (`project-sales/_shared/lib/fulfilmentBoard.ts::factorLabel`) - kept as its own copy here
// rather than an import, so this tab never breaks from an edit to the board's own file. Order
// matches the weight inputs on the Fulfilment tab.
export const FULFILMENT_FACTOR_ORDER = [
  'need_by_date',
  'document_age',
  'customer_credit',
  'demand_class',
  'po_document_sequence',
] as const;

export const FULFILMENT_FACTOR_LABEL: Record<string, string> = {
  need_by_date: 'Delivery date',
  document_age: 'Order date',
  customer_credit: 'Payment terms',
  demand_class: 'Demand type',
  po_document_sequence: 'Purchase order sequence',
};

export function fulfilmentFactorLabel(key: string): string {
  const known = FULFILMENT_FACTOR_LABEL[key];
  if (known) return known;
  const words = key.replace(/_/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// Demand-class weight rows the Fulfilment tab shows - `project` / `retail` (S1's closed
// vocabulary, `app.services.scm.demand_class.DEMAND_CLASSES`).
export const FULFILMENT_CLASS_ORDER = ['project', 'retail'] as const;

export const FULFILMENT_CLASS_LABEL: Record<string, string> = {
  project: 'Project',
  retail: 'Retail',
};

/**
 * Plain-language safety-stock summary for a grid row (novice-friendly), e.g.
 * "7-day buffer", "Statistical @ 95%", "Manual".
 */
export function safetyStockSummary(
  method: SafetyStockMethod,
  safetyDays: number | null,
  serviceLevel: number | null,
): string {
  if (method === 'statistical') {
    return serviceLevel != null
      ? `Statistical @ ${Math.round(serviceLevel * 100)}%`
      : 'Statistical';
  }
  if (method === 'fixed_days') {
    return safetyDays != null ? `${safetyDays}-day buffer` : 'Fixed days';
  }
  return 'Manual';
}
