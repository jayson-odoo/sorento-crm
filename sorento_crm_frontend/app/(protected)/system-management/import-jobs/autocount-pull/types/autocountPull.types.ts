/**
 * AutoCount pull + review - shared FE shapes.
 * See `documentation/plans/autocount/PLAN-autocount-pull-review.md` ("Routes" and the pull job
 * metadata shape) and its UAC for the contract these mirror.
 */

/** The two entities a pull can be started for; the values match the backend route param. */
export type AutocountPullEntity = 'products' | 'stock_balances';

/**
 * Where a pull is in its life. `building` = FoundryX still assembling the snapshot (no
 * Sorento worker job yet); `previewing` = the preview task is running; `review` = ready for
 * Confirm; `confirmed` = the apply job has been created; `failed` / `expired` = dead ends.
 */
export type AutocountPullPhase =
  | 'building'
  | 'previewing'
  | 'review'
  | 'confirmed'
  | 'failed'
  | 'expired';

export interface AutocountPullProgress {
  pagesDone: number;
  pagesTotal: number;
  stage?: string | null;
}

export interface ProductPullCounts {
  received: number;
  new: number;
  changed: number;
  unchanged: number;
  failed: number;
  left_out: number;
  price_to_zero: number;
}

export interface StockPullCounts {
  received: number;
  fed: number;
  not_applied_inactive: number;
  not_applied_unknown: number;
  qty_changes: number;
  set_to_zero: number;
  skipped_product_not_found: number;
  negative_in_autocount: number;
}

export type AutocountPullCounts = ProductPullCounts | StockPullCounts;

export interface AutocountPullCompareSummary {
  filename: string;
  compared_at: string;
  total: number;
  matched: number;
  different: number;
  only_in_excel: number;
  only_in_pull: number;
  qty_total_excel?: number | null;
  qty_total_pull?: number | null;
}

/** One field-level (or row-level) difference the Compare tab lists and can export. */
export interface AutocountCompareDifference {
  item_code: string;
  /** Stock compare only - the pair's location. */
  location?: string;
  field: string;
  your_excel: string;
  autocount_pull: string;
}

export interface AutocountComparePullResult {
  summary: AutocountPullCompareSummary;
  differences: AutocountCompareDifference[];
}

/** `GET /api/v1/autocount/pulls/{job_id}` response - also what `POST /` and `/current` return. */
export interface AutocountPull {
  job_id: string;
  entity: AutocountPullEntity;
  company_code: string;
  phase: AutocountPullPhase;
  progress?: AutocountPullProgress | null;
  /** FoundryX's `extractedAt` / `expiresAt`, once the snapshot is ready. */
  extracted_at?: string | null;
  expires_at?: string | null;
  counts?: AutocountPullCounts | null;
  /** Set only when Confirm is blocked (e.g. stock AC-SP-1); Confirm stays enabled otherwise. */
  confirm_blocked_reason?: string | null;
  compare?: AutocountPullCompareSummary | null;
  /** Set once Confirm has been clicked - the apply job the page links to. */
  apply_job_id?: string | null;
  /** Set on `failed` / `expired`. */
  error_message?: string | null;
}

/** The Excel-view row shape for `products` - same columns, same order as the manual template. */
export interface ProductExcelRow {
  item_code: string;
  description: string;
  desc_2: string;
  item_group: string;
  item_brand: string;
  price: number;
  is_active: boolean;
}

/** The Excel-view row shape for `stock_balances`. FED rows only. */
export interface StockExcelRow {
  item_code: string;
  item_description: string;
  location: string;
  on_hand_qty: number;
}

export type AutocountPullExcelRow = ProductExcelRow | StockExcelRow;

export interface AutocountPullRowsQuery {
  pageIndex: number;
  pageSize: number;
  query?: string;
}
