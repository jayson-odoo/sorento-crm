/**
 * Divergence between our sales order and AutoCount's copy of it (P8a, AC-N1 to AC-N7).
 *
 * Between the import file and the ESB swap the document lives in two systems and either
 * side can be edited. Neither wins silently: what arrives here is a per-row comparison
 * that a person answers.
 *
 * Values are STRINGS, quantized by the backend to the scale each column stores, and the
 * screen renders them exactly as compared. Re-deriving a quantity in the browser is how
 * a reconciliation ends up disagreeing with the reconciliation it is reporting on.
 *
 * Nothing here is shown as a UUID: rows carry the product CODE and the document NUMBER.
 */

export type DivergenceStatus = 'open' | 'resolved';

export type DivergenceScope = 'header' | 'line';

/** Which side has the row at all. `both` means it is a field-level difference. */
export type DivergencePresence = 'both' | 'ours_only' | 'theirs_only';

export type DivergenceResolution = 'accept_theirs' | 'keep_ours';

export type IngestOutcome = 'matched' | 'divergent' | 'ambiguous' | 'unmatched';

/** The compared values, keyed by field name. Absent on the side that has no row. */
export type DivergenceValues = Record<string, string | number | null>;

export interface DivergenceRow {
  id: string;
  scope: DivergenceScope;
  presence: DivergencePresence;
  so_line_id?: string | null;
  line_no?: number | null;
  product_code?: string | null;
  ours: DivergenceValues;
  theirs: DivergenceValues;
  /** Empty on a row that agrees, and on a row present on one side only. */
  differing_fields: string[];
  /** False for rows that agree: the screen collapses them behind a count (AC-N3). */
  needs_answer: boolean;
  resolution?: DivergenceResolution | null;
  reason?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
}

export interface DivergenceDetail {
  id: string;
  project_sales_order_id: string;
  project_id?: string | null;
  project_title?: string | null;
  provisional_ref?: string | null;
  autocount_doc_no?: string | null;
  status: DivergenceStatus | string;
  ingest_source?: string | null;
  compared_count: number;
  agreeing_count: number;
  differing_count: number;
  unresolved_count: number;
  /** Set the moment any row is answered KEEP OURS: AutoCount holds a value we rejected. */
  corrective_publish_required: boolean;
  corrective_publish_taken_at?: string | null;
  detected_at?: string | null;
  resolved_at?: string | null;
  resolved_by?: string | null;
  rows: DivergenceRow[];
}

export interface DivergenceSummary {
  id: string;
  project_sales_order_id: string;
  project_id?: string | null;
  project_title?: string | null;
  sales_order_ref?: string | null;
  provisional_ref?: string | null;
  autocount_doc_no?: string | null;
  status: DivergenceStatus | string;
  compared_count: number;
  agreeing_count: number;
  differing_count: number;
  unresolved_count: number;
  corrective_publish_required: boolean;
  detected_at?: string | null;
  resolved_at?: string | null;
  /** How long it has been sitting unanswered (AC-N6). */
  age_days: number;
}

export interface DivergenceListParams {
  status?: DivergenceStatus | string;
  project_id?: string;
  page?: number;
  limit?: number;
}

export interface DivergenceListEnvelope {
  data: DivergenceSummary[];
  total: number;
  page: number;
  limit: number;
}

export interface IngestResult {
  outcome: IngestOutcome | string;
  project_sales_order_id?: string | null;
  divergence_id?: string | null;
  differing_count: number;
  /** Populated on `ambiguous`: the sales orders a person has to choose between. */
  candidate_ids: string[];
  message: string;
}

/** The field labels a reviewer reads, rather than the column names. */
export const DIVERGENCE_FIELD_LABELS: Record<string, string> = {
  qty: 'Quantity',
  unit_price: 'Unit price',
  delivery_date: 'Delivery date',
  customer_code: 'Debtor',
  customer_po_no: 'Customer PO',
  terms: 'Terms',
  total_amount: 'Document total',
};

export const PRESENCE_LABELS: Record<DivergencePresence, string> = {
  both: 'Values differ',
  ours_only: 'Missing in AutoCount',
  theirs_only: 'Added in AutoCount',
};
