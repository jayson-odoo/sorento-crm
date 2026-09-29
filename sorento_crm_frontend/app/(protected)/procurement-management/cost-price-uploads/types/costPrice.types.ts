/**
 * Shapes for the cost price change set (Lane A, S1 + S2, #1288).
 *
 * Field names mirror the API contract verbatim (snake_case, as the backend will send them):
 * `documentation/plans/purchasing/cost-price-api-contract.md`. Phase 1 is mocked at the
 * service boundary (`services/costPriceService.ts`) - these types are what both the mock
 * and the real backend, once wired in Phase 2, hand back.
 */

export type ChangeSetStatus = 'draft' | 'pending_verification' | 'applied';
export type ChangeSetChannel = 'staff_upload' | 'supplier_page' | 'supplier_upload';

export type MatchOutcome = 'exact' | 'alias' | 'ladder' | 'manual' | 'unmatched';
export type LineState = 'changed' | 'unchanged' | 'new_link' | 'needs_attention' | 'skipped';
export type LineDecision = 'accepted' | 'rejected' | null;

export interface SupplierRef {
  id: string;
  supplier_code: string;
  supplier_name: string;
}

export interface SheetSummary {
  name: string;
  header_row: number | null;
  rows: number;
  skipped_reason: string | null;
}

export interface CostPriceProbeResult {
  file_name: string;
  file_date: string | null;
  sheets: SheetSummary[];
  total_rows: number;
  suggested_supplier: SupplierRef | null;
  currency: { code: string | null; source: 'header' | 'supplier' | null };
}

export interface CostPriceChangeSetListItem {
  id: string;
  code: string;
  status: ChangeSetStatus;
  supplier: SupplierRef;
  channel: ChangeSetChannel;
  file_name: string | null;
  currency: string;
  start_date: string | null;
  end_date: string | null;
  lines_changed: number;
  uploaded_by_name: string | null;
  created_at: string;
  applied_at: string | null;
  verified: boolean | null;
  verified_by_name: string | null;
}

export interface CostPriceDuplicateRow {
  id: string;
  sheet: string;
  row_no: number;
  supplier_code: string;
  packaging_method: string;
  new_unit_cost: number | null;
}

export interface CostPriceChangeSetCounts {
  changed: number;
  unchanged: number;
  new_link: number;
  unmatched: number;
  duplicate_code: number;
  needs_attention: number;
  skipped: number;
  accepted: number;
  rejected: number;
  undecided: number;
}

export interface CostPriceChangeSetActions {
  can_apply: boolean;
  apply_blocked_reason: string | null;
  apply_count: number;
  can_submit: boolean;
  can_decide: boolean;
  can_return: boolean;
  can_discard: boolean;
  decide_blocked_reason: string | null;
  /** True on a Draft set, when the caller holds upload and at least one line is stale
   *  (S6): the set can re-capture current prices via `refresh-prices` before it goes on.
   *  Optional so existing fixtures that predate this field still type-check - the
   *  backend always sends it, an absent value reads the same as `false`. */
  can_refresh_prices?: boolean;
}

export interface CostPriceChangeSetDetail {
  id: string;
  code: string;
  status: ChangeSetStatus;
  channel: ChangeSetChannel;
  supplier: SupplierRef;
  currency: string;
  start_date: string | null;
  end_date: string | null;
  file_name: string | null;
  has_source_file: boolean;
  sheets: SheetSummary[];
  total_rows: number;
  uploaded_by_name: string | null;
  created_at: string;
  submitted_by_name: string | null;
  submitted_at: string | null;
  returned_reason: string | null;
  returned_by_name: string | null;
  returned_at: string | null;
  applied_by_name: string | null;
  applied_at: string | null;
  verified: boolean | null;
  verification_enabled: boolean;
  counts: CostPriceChangeSetCounts;
  largest_rise: { supplier_code: string; change_pct: number } | null;
  actions: CostPriceChangeSetActions;
}

export interface CostPriceChangeLine {
  id: string;
  sheet: string;
  row_no: number;
  line_no: string | null;
  supplier_code_raw: string;
  supplier_code: string;
  /** Round 8 (owner, 28 Sep 2026): the code's bracket text as the supplier wrote it ("彩盒",
   *  "OPP"), `standard` for a plain code. Part of the line's key with the code. */
  packaging_method: string;
  configuration: string | null;
  flags: string[];
  match_outcome: MatchOutcome;
  match_rung: string | null;
  product: { id: string; product_code: string; description: string } | null;
  current_unit_cost: number | null;
  current_currency: string | null;
  new_unit_cost: number | null;
  change_pct: number | null;
  line_state: LineState;
  skipped: boolean;
  skip_reason: string | null;
  new_link_lead_time_days: number | null;
  decision: LineDecision;
  decision_reason: string | null;
  decided_by_name: string | null;
  /** Set when the current price on file moved after this line was captured (S6): the
   *  recorded `current_unit_cost`/`current_currency` is what the line was built against,
   *  this is what the product-supplier link holds right now. */
  stale: { live_unit_cost: number | null; live_currency: string | null } | null;
  /** Round 6 R6 (round 8: same code AND same packaging): the other rows, in file order.
   *  They are not applied; the line carries the row `choose_duplicate_row` picked. */
  duplicate_rows?: CostPriceDuplicateRow[];
}

export interface CostPriceHistoryEvent {
  action: string;
  actor_name: string;
  at: string;
  summary: string;
}

/** Cost list row (`product_supplier_costs`), section 2.1 / 2.2 of the contract. */
export type CostRowStatus = 'in_force' | 'scheduled' | 'ended' | 'always' | 'overridden';

export interface ProductSupplierCostRow {
  id: string;
  /** Round 8: the packaging this cost is for; `standard` for a plain code. */
  packaging_method: string;
  unit_cost: number;
  currency: string;
  start_date: string | null;
  end_date: string | null;
  status: CostRowStatus;
  /** `sheet` + `row_no`: the row of the upload this cost came from (round 6, R6). */
  source: { change_set_id: string; code: string; sheet?: string | null; row_no?: number | null } | null;
  created_at: string;
}

/** One product AND packaging method of the supplier (round 8). */
export interface SupplierCostListEntry {
  product_supplier_id: string;
  packaging_method: string;
  packaging_key: string;
  product: { id: string; product_code: string; description: string };
  supplier_code: string | null;
  unit_cost: number | null;
  currency: string | null;
  costs: ProductSupplierCostRow[];
}
