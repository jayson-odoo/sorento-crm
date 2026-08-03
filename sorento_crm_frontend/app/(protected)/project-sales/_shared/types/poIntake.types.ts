/**
 * Customer PO intake (P4) and handwriting review cards (P5).
 *
 * Shapes come from `documentation/plans/CONTRACT-project-lead-to-so.md` sections 2 and 3.
 * Money and quantities are STRINGS the whole way through, exactly as the contract says:
 * a float round trip loses cents on a 1.8 million ringgit PO, and the one number this
 * screen exists to show is the difference between two totals.
 *
 * Fields marked "additive" are optional on purpose. They are things the confirm screen
 * needs and the contract is silent about, so the UI degrades to something honest when the
 * backend does not send them rather than rendering a wrong page or a blank stamp.
 */

export type POExtractionState = 'queued' | 'running' | 'done' | 'failed';

/**
 * What the screen actually branches on. `partial` is not a backend state: it is `done`
 * carrying an extraction error or a short page count, and it must never look like success.
 */
export type POExtractionPhase = POExtractionState | 'partial';

export type POResolutionSource = 'code' | 'description' | 'map' | 'manual' | null;

export interface POVersionHeader {
  po_number: string | null;
  po_date: string | null;
  term_days: number | null;
  sales_person: string | null;
  customer_order_ref: string | null;
  admin_ref: string | null;
  remark: string | null;
}

export interface POVersionTotals {
  /** The total printed on the document itself. Null when no total could be read. */
  extracted_total: string | null;
  /** Our sum of the lines. */
  lines_total: string;
  arithmetic_passed: number;
  arithmetic_total: number;
}

export interface POVersionLine {
  id: string;
  line_no: number;
  stock_code_raw: string | null;
  description_raw: string | null;
  qty: string;
  uom_raw: string | null;
  unit_price: string;
  amount: string;
  /** `qty * unit_price == amount` to two decimals, computed by the backend, never the model. */
  arithmetic_ok: boolean;
  is_cancelled: boolean;
  resolved_product_id: string | null;
  resolved_product_code: string | null;
  resolution_source: POResolutionSource;
  /** Additive: the page this line was read from, so the viewer can follow the focused row. */
  page_no?: number | null;
}

export type POAnnotationInterpretation =
  | 'cancel_line'
  | 'amend_code'
  | 'amend_description'
  | 'successor_po'
  | 'signature'
  | 'other';

export type POAnnotationState = 'proposed' | 'accepted' | 'edited' | 'rejected';

export interface POAnnotation {
  id: string;
  page_no: number;
  /** Presigned crop of just that region. Null when no crop was captured. */
  crop_url: string | null;
  raw_text: string | null;
  written_date: string | null;
  refers_to_lines: number[];
  interpretation: POAnnotationInterpretation;
  interpretation_json: Record<string, unknown> | null;
  state: POAnnotationState;
  actioned_by_name: string | null;
  actioned_at: string | null;
  action_note: string | null;
}

/**
 * Additive: the approval stamps live on the phase-1 PO row, and the version response is
 * the only thing the confirm screen reads. Either shape is accepted.
 */
export interface POApprovalStamps {
  po_number?: string | null;
  status?: string | null;
  approved_by_name?: string | null;
  approved_at?: string | null;
  countersigned_by_name?: string | null;
  countersigned_at?: string | null;
}

export interface POVersion {
  id: string;
  purchase_order_id: string;
  version_no: number;
  extraction_state: POExtractionState;
  extraction_error: string | null;
  extraction_model: string | null;
  page_count: number | null;
  /** Presigned document URL for the side-by-side viewer. */
  document_url: string | null;
  header: POVersionHeader;
  totals: POVersionTotals;
  lines: POVersionLine[];
  annotations: POAnnotation[];
  confirmed_at: string | null;
  /** Additive. */
  confirmed_by_name?: string | null;
  /** Additive: pages that produced content, when the backend counts them. */
  pages_extracted?: number | null;
  /** Additive: how long the model took. Null on documents read before it was recorded. */
  extraction_elapsed_ms?: number | null;
  /** Additive: pages extraction could not read. */
  failed_pages?: number[] | null;
  /** Additive: the PO row's approval stamps, nested. */
  purchase_order?: POApprovalStamps | null;
  /** Additive: the same stamps, flat. */
  approved_by_name?: string | null;
  approved_at?: string | null;
  countersigned_by_name?: string | null;
  countersigned_at?: string | null;
}

/**
 * Version list row, for re-entering a review from the POs tab.
 *
 * `GET /purchase-orders/{po_id}/versions` is defined as "a subset of the single-version
 * body": id, version number, confirmed-at. Everything beyond that subset is optional here,
 * so a row that arrives without an extraction state renders without a state badge instead of
 * an empty one.
 */
export interface POVersionSummary {
  id: string;
  version_no: number;
  confirmed_at?: string | null;
  purchase_order_id?: string;
  extraction_state?: POExtractionState | null;
  extraction_error?: string | null;
  page_count?: number | null;
  created_at?: string | null;
}

export interface POUploadBody {
  file: File;
  po_number?: string | null;
  purchase_order_id?: string | null;
}

export interface POUploadResponse {
  purchase_order_id: string;
  po_version_id: string;
  version_no: number;
  extraction_state: POExtractionState;
  page_count: number | null;
}

export interface POLineUpdateBody {
  stock_code_raw?: string | null;
  description_raw?: string | null;
  qty?: string;
  uom_raw?: string | null;
  unit_price?: string;
  amount?: string;
  resolved_product_id?: string | null;
  is_cancelled?: boolean;
}

export interface POAnnotationEditBody {
  interpretation: POAnnotationInterpretation;
  interpretation_json: Record<string, unknown>;
  note?: string | null;
}

/** The one seam the mock scenarios and the live hooks both satisfy. */
export interface POIntakeController {
  version: POVersion | null;
  phase: POExtractionPhase | null;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  /** True while extraction is still running, so the screen can say so honestly. */
  isPolling: boolean;
  /** Line ids with a write in flight. */
  savingLineIds: string[];
  /** Annotation ids with a write in flight. */
  savingAnnotationIds: string[];
  isConfirming: boolean;
  isStamping: boolean;
  isSavingHeader: boolean;
  updateHeader: (body: Partial<POVersionHeader>) => Promise<void>;
  updateLine: (lineId: string, body: POLineUpdateBody) => Promise<void>;
  confirm: () => Promise<void>;
  acceptAnnotation: (annotationId: string, note?: string | null) => Promise<void>;
  editAnnotation: (annotationId: string, body: POAnnotationEditBody) => Promise<void>;
  rejectAnnotation: (annotationId: string, note: string) => Promise<void>;
  approve: () => Promise<void>;
  countersign: () => Promise<void>;
  /** Mock scenarios say so out loud rather than pretending a write reached the server. */
  isMock: boolean;
}

export const PO_INTERPRETATION_LABELS: Record<POAnnotationInterpretation, string> = {
  cancel_line: 'Cancels a line',
  amend_code: 'Changes a code',
  amend_description: 'Changes a description',
  successor_po: 'Names a replacement PO',
  signature: 'A signature',
  other: 'Something else',
};

export const PO_ANNOTATION_STATE_LABELS: Record<POAnnotationState, string> = {
  proposed: 'Not reviewed',
  accepted: 'Accepted',
  edited: 'Accepted with edits',
  rejected: 'Rejected',
};

/**
 * `done` plus an error, or fewer pages read than the document has, is a PARTIAL read.
 * Presenting that as success is how a misread page reaches a published sales order.
 */
export function resolveExtractionPhase(
  version: POVersion | null,
): POExtractionPhase | null {
  if (!version) return null;
  if (version.extraction_state !== 'done') return version.extraction_state;
  const failedPages = version.failed_pages ?? [];
  const shortRead =
    version.pages_extracted != null &&
    version.page_count != null &&
    version.pages_extracted < version.page_count;
  if (failedPages.length > 0 || shortRead || Boolean(version.extraction_error))
    return 'partial';
  return 'done';
}

export function poAnnotationIsReviewed(annotation: POAnnotation): boolean {
  return annotation.state !== 'proposed';
}
