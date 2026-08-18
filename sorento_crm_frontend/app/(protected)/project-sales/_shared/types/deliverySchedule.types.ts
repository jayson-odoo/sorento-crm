/**
 * Delivery schedule intake (P6). Shapes come from CONTRACT-project-lead-to-so.md section 4.
 *
 * Two conventions from that contract are load-bearing here:
 *
 * 1. Quantities are STRINGS ("927", "135"). They are Numeric in Postgres and a float round
 *    trip loses precision on a 1.8 million ringgit commitment. Nothing in this slice turns
 *    a quantity into a number: totals and comparisons go through the decimal-safe helpers
 *    in `../../[projectId]/delivery-schedules/lib/scheduleTotals`.
 * 2. Reconciliation is PER COLUMN, never per document. Measured on the client's own two
 *    schedules, 29/37 and 35/38 columns reconciled on the first pass, so a whole-document
 *    verdict would reject nearly every real schedule.
 *
 * Fields marked GUESS are not in contract section 4. They are additive and optional, so a
 * backend that omits them degrades to a readable screen rather than a crash.
 */

/**
 * `queued | running | done | failed` are the contract's four states (section 2, reused by
 * section 4). `partial` is a GUESS: the extractor works page by page, so "read 5 of 7
 * pages" is a real outcome and it must not render as success.
 */
export type ScheduleExtractionState =
  | 'queued'
  | 'running'
  | 'done'
  | 'failed'
  | 'partial';

/** What the screen actually branches on. `partial` is also inferred, see resolveExtractionPhase. */
export type ExtractionPhase = 'queued' | 'running' | 'done' | 'partial' | 'failed';

export type ScheduleResolutionSource = 'map' | 'code' | 'manual' | null;

/**
 * A phase row. Identity is `(area_group, sequence)` and NOT the label: the COMMON AREA
 * rows on the real documents carry no label at all, and matching by label collapsed three
 * phases into one (finding G6).
 */
export interface DeliverySchedulePhase {
  id: string;
  area_group: string | null;
  sequence: number;
  label: string | null;
  delivery_date: string | null;
}

/**
 * A product column. Three numbers travel together because comparing them IS the feature:
 * `column_total` (our sum of the cells), `reported_total` (the schedule's own TOTAL QTY
 * row, transcribed) and `po_qty` (what the named PO version ordered).
 */
export interface DeliveryScheduleProduct {
  product_id: string | null;
  product_code: string | null;
  product_name: string | null;
  customer_code_raw: string | null;
  resolution_source: ScheduleResolutionSource;
  column_total: string | null;
  reported_total: string | null;
  po_qty: string | null;
  reconciled: boolean;
  /**
   * GUESS. `PUT .../products/{product_index}` in the contract implies a stable column
   * index; the products array carries none. Callers fall back to the array position, so
   * this only matters if the backend ever reorders the array.
   */
  product_index?: number | null;

  /**
   * A person overruled this column's failing check as a false signal. The check itself is
   * not withdrawn, so the sentences describing it are still shown; the column simply stops
   * blocking the confirm. Cleared by anything that changes the column.
   */
  dismissed?: boolean;
  dismissed_reason?: string | null;
  dismissed_by_name?: string | null;

  /**
   * Something worth saying about a column that still reconciles: it agrees with the PO and is
   * nonetheless worth a second look. Never blocks the confirm, so the screen renders it amber
   * rather than red, and there is nothing to fix.
   */
  warning?: string | null;
}

/**
 * One quantity in the matrix. A cell that does not exist means this phase does not take
 * this product, which is NOT the same as ordering zero of it, so it renders blank.
 */
export interface DeliveryScheduleCell {
  phase_id: string;
  product_id: string | null;
  qty: string;
  /**
   * GUESS. The contract keys cells on `product_id`, which cannot address a column whose
   * product is still unidentified. When present this lets the grid show the quantities the
   * extractor read for such a column; when absent that column renders blank until resolved.
   */
  product_index?: number | null;
}

export interface DeliveryScheduleReconciliation {
  reconciled_columns: number;
  total_columns: number;
}

export interface DeliveryScheduleVersion {
  id: string;
  delivery_schedule_id: string;
  version_no: number;
  revision_label: string | null;
  issuer_party_label: string | null;
  po_version_id: string | null;
  po_version_no: number | null;
  extraction_state: ScheduleExtractionState;
  document_url: string | null;
  schedule_date: string | null;
  phases: DeliverySchedulePhase[];
  products: DeliveryScheduleProduct[];
  cells: DeliveryScheduleCell[];
  reconciliation: DeliveryScheduleReconciliation;
  confirmed_at: string | null;

  /** GUESS: honest progress and the partial case both need these. */
  extraction_error?: string | null;
  page_count?: number | null;
  pages_extracted?: number | null;
  /** Additive: how long the model took. Null on documents read before it was recorded. */
  extraction_elapsed_ms?: number | null;
  /**
   * Additive: when the reader picked this document up, so a wait can be reported as a
   * length rather than as a spinner with nothing behind it.
   */
  extraction_started_at?: string | null;

  /** GUESS: the header must name the PO and the person without rendering a UUID. */
  purchase_order_id?: string | null;
  po_number?: string | null;
  confirmed_by_name?: string | null;
  uploaded_by_name?: string | null;
  created_at?: string | null;
}

/**
 * A schedule with its version history rolled up.
 *
 * GUESS: contract section 4 has no list endpoint. This mirrors the shape phase 1 already
 * uses for quotations (`GET /projects/{id}/quotations` + `GET /quotations/{id}/versions`),
 * which is the closest existing precedent.
 */
export interface DeliverySchedule {
  id: string;
  purchase_order_id: string;
  po_number: string | null;
  version_count: number;
  latest_version_id: string | null;
  latest_version_no: number | null;
  latest_revision_label: string | null;
  issuer_party_label: string | null;
  schedule_date: string | null;
  extraction_state: ScheduleExtractionState;
  reconciled_columns: number;
  total_columns: number;
  confirmed_at: string | null;
  created_at?: string | null;
}

/** One row of the version history list. */
export interface DeliveryScheduleVersionSummary {
  id: string;
  delivery_schedule_id: string;
  version_no: number;
  revision_label: string | null;
  issuer_party_label: string | null;
  schedule_date: string | null;
  extraction_state: ScheduleExtractionState;
  reconciled_columns: number;
  total_columns: number;
  confirmed_at: string | null;
  created_at: string | null;
  uploaded_by_name?: string | null;
}

/** `202` from the upload. Extraction has not run yet. */
export interface DeliveryScheduleUploadResult {
  delivery_schedule_id: string;
  schedule_version_id: string;
  version_no: number;
  extraction_state: ScheduleExtractionState;
  page_count?: number | null;
}

export interface DeliveryScheduleUploadBody {
  file: File;
  issuer_party_id?: string | null;
  revision_label?: string | null;
  delivery_schedule_id?: string | null;
  po_version_id?: string | null;
}

export interface DeliveryScheduleCellInput {
  phase_id: string;
  product_id: string;
  /** `"0"` deletes the cell, per the contract. */
  qty: string;
}

export interface DeliveryScheduleConfirmBody {
  acknowledge_unreconciled?: boolean;
  reason?: string;
}

/** `reason` is required when dismissing; the server answers 422 without it. */
export interface DeliveryScheduleDismissBody {
  dismissed: boolean;
  reason?: string | null;
}

/**
 * Reduces the wire state to the five the screen renders.
 *
 * A `done` version carrying an extraction error is PARTIAL, not success: some pages were
 * read and some were not, and the difference is exactly what the reviewer needs to know
 * before trusting a column total.
 */
export function resolveExtractionPhase(version: {
  extraction_state: ScheduleExtractionState;
  extraction_error?: string | null;
  page_count?: number | null;
  pages_extracted?: number | null;
}): ExtractionPhase {
  if (version.extraction_state === 'partial') return 'partial';
  if (version.extraction_state === 'failed') return 'failed';
  if (version.extraction_state === 'queued') return 'queued';
  if (version.extraction_state === 'running') return 'running';
  if (version.extraction_error) return 'partial';
  const read = version.pages_extracted;
  const total = version.page_count;
  if (typeof read === 'number' && typeof total === 'number' && total > 0 && read < total) {
    return 'partial';
  }
  return 'done';
}

/** True while the version is still being read, so the caller should keep polling. */
export function isExtractionPending(phase: ExtractionPhase): boolean {
  return phase === 'queued' || phase === 'running';
}
