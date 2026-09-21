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
 * Confirm; `confirmed` = the apply job has been created; `failed` / `expired` / `discarded`
 * = dead ends - `discarded` is the owner throwing an open pull away on purpose
 * (PLAN-autocount-pull-discard.md), never a refusal.
 */
export type AutocountPullPhase =
  | 'building'
  | 'previewing'
  | 'review'
  | 'confirmed'
  | 'failed'
  | 'expired'
  | 'discarded';

export interface AutocountPullProgress {
  pagesDone: number;
  pagesTotal: number;
  stage?: string | null;
}

/** B3 (small-fix track): the preview task's own row-by-row progress through
 *  `MasterIngestService.ingest`'s `on_progress` (products) or set once at the end
 *  (stock, which has no per-record hook) - `null` before the task has published a
 *  total yet, and outside `previewing` (nothing left to show once the phase has
 *  moved on). Distinct from `progress` above, which is FoundryX's own page-fetch
 *  progress during `building`. */
export interface AutocountPullPreviewProgress {
  processed: number;
  total: number;
}

/**
 * The FoundryX ready header, as the pull route stores + returns it - camelCase, stripped of
 * `excludedRows` / `negativePairList` (AC-BD-2; both can be large and are not needed on the
 * page). Present once the snapshot has been read (`review` / `confirmed`), `null` before that.
 */
export interface AutocountPullHeader {
  snapshotId: string;
  entity: AutocountPullEntity;
  companyCode: string;
  extractedAt: string;
  expiresAt: string;
  recordCount: number;
  complete: boolean;
  contentHash: string;
  sourcePageSize?: number;
  /** Products only. */
  zeroListPriceCount?: number;
  negativeListPriceCount?: number;
  /** Stock only (SR4). */
  zeroPairs?: number;
  negativePairs?: number;
  fractionalPairs?: number;
  excludedCount?: number;
  excludedNonzeroCount?: number;
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

/** One field-level (or row-level) difference the Compare tab lists and can export - the
 *  REAL backend shape (`app/services/autocount_pull_compare.py`): `excel` / `pull`, not
 *  `your_excel` / `autocount_pull`. */
export interface AutocountCompareDifference {
  item_code: string;
  /** Stock compare only - the pair's location. */
  location?: string;
  field: string;
  excel: string;
  pull: string;
}

/** `POST /api/v1/autocount/pulls/{job_id}/compare` response. `summary` is the STORED
 *  compare summary (same shape `GET /{job_id}` returns as `compare`); `only_in_excel` /
 *  `only_in_pull` here are the item-code LISTS the comparison just computed - distinct
 *  from `summary.only_in_excel` / `summary.only_in_pull`, which are counts. */
export interface AutocountComparePullResult {
  summary: AutocountPullCompareSummary;
  differences: AutocountCompareDifference[];
  only_in_excel: string[];
  only_in_pull: string[];
}

/** The apply job's own `import_jobs.status` (backend `JobStatus`). */
export type AutocountApplyStatus = 'pending' | 'queued' | 'started' | 'finished' | 'failed' | 'cancelled';

/** `GET /api/v1/autocount/pulls/{job_id}` response - also what `POST /` and `/current` return. */
export interface AutocountPull {
  job_id: string;
  entity: AutocountPullEntity;
  company_code: string;
  phase: AutocountPullPhase;
  progress?: AutocountPullProgress | null;
  preview_progress?: AutocountPullPreviewProgress | null;
  /** The FoundryX ready header (camelCase), once the snapshot has been read; `null` before. */
  header?: AutocountPullHeader | null;
  counts?: AutocountPullCounts | null;
  /** Set only when Confirm is blocked (e.g. stock AC-SP-1); Confirm stays enabled otherwise. */
  confirm_blocked_reason?: string | null;
  compare?: AutocountPullCompareSummary | null;
  /** Set once Confirm has been clicked - the apply job the page links to. */
  apply_job_id?: string | null;
  /** The apply job's own status (fix round 3, item 2); `null` while there is no apply job
   *  yet. `usePull` keeps polling past `phase === 'confirmed'` while this is not yet
   *  `finished`/`failed` - the apply task's own `stock_list_not_archived` warning lands on
   *  the pull's metadata only once the apply task actually runs. */
  apply_status?: AutocountApplyStatus | null;
  /** String warning codes (e.g. `content_hash_mismatch`) - never a refusal, absent or empty
   *  means a clean match. */
  warnings?: string[];
  /** Set on `failed` / `expired`. */
  error?: string | null;
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
