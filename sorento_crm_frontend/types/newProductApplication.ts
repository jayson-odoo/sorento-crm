/**
 * New product application shapes (NEW-PRODUCT-APP), shared by the staff feature and the portal.
 * Names are the backend contract in
 * documentation/plans/procurement/PLAN-new-product-application-17oct.md ("API contract (as built)").
 */

export type NewProductApplicationStatus =
  | 'draft'
  | 'submitted'
  | 'approved'
  | 'rejected'
  | 'completed'
  | 'cancelled';

/**
 * One product as written (v4 paper layout, AC-NPA-70). `id` is sent only for a saved product so
 * the server keeps it (and its images); null clears a field. The applicant never writes cost.
 */
export interface NewProductApplicationLineWrite {
  id?: string;
  proposed_code?: string | null;
  /** PRODUCT TYPE on the paper form, the only required field. */
  description?: string | null;
  dimension?: string | null;
  material?: string | null;
  thickness?: string | null;
  packing?: string | null;
  brand_id?: string | null;
  /** Numbers travel as strings or numbers; null clears, never 0. */
  expected_qty?: string | number | null;
}

/** The write payload, staff and portal alike. `needed_by` is YYYY-MM-DD. */
export interface NewProductApplicationWrite {
  stock_inquiry_id?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  project_name?: string | null;
  needed_by?: string | null;
  remark?: string | null;
  lines?: NewProductApplicationLineWrite[];
}

/** GET /prefill: a Write-shaped body copied as text, plus the inquiry's number. */
export interface NewProductApplicationPrefill extends NewProductApplicationWrite {
  stock_inquiry_number: string | null;
}

export interface NewProductApplicationSummary {
  id: string;
  application_no: string;
  status: NewProductApplicationStatus;
  status_label: string;
  source: string;
  applicant_id: string | null;
  applicant_name: string | null;
  stock_inquiry_id: string | null;
  stock_inquiry_number: string | null;
  customer_name: string | null;
  project_name: string | null;
  first_line: string | null;
  lines_total: number;
  lines_done: number;
  opened_codes: string[];
  needed_by: string | null;
  submitted_at: string | null;
  created_at: string | null;
}

/** One file attached to the application (shape of the generic attachment list). */
export interface NewProductApplicationAttachment {
  link_id: string;
  attachment_id: string;
  filename: string | null;
  size: number | null;
  url: string | null;
  content_type?: string | null;
  uploaded_at?: string | null;
  uploaded_by_name?: string | null;
  uploaded_by_role?: string | null;
  can_unlink?: boolean;
}

export interface NewProductApplicationLine extends NewProductApplicationLineWrite {
  id: string;
  line_no: number;
  brand_name: string | null;
  /** Purchasing feedback: COST, one per product. */
  cost_price: string | number | null;
  /** Read from the linked product (staff only except the supplier, PQ1). */
  opened_category_name?: string | null;
  opened_base_uom_name?: string | null;
  opened_list_price?: string | number | null;
  opened_supplier_name: string | null;
  opened_product_id: string | null;
  opened_product_code: string | null;
  opened_product_name: string | null;
  opened_product_active: boolean | null;
  closed_reason: string | null;
  resolved_by: string | null;
  resolved_by_name: string | null;
  resolved_at: string | null;
}

export interface NewProductApplicationDetail extends NewProductApplicationSummary {
  stock_inquiry_product_code: string | null;
  customer_id: string | null;
  customer_code: string | null;
  remark: string | null;
  /** Purchasing feedback: LEADTIME, one per application. */
  lead_time: string | null;
  attachments?: NewProductApplicationAttachment[];
  feedback_by_name?: string | null;
  feedback_at?: string | null;
  decided_at: string | null;
  decided_by: string | null;
  decided_by_name: string | null;
  reject_reason: string | null;
  revise_reason: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  completed_at: string | null;
  updated_at: string | null;
  lines: NewProductApplicationLine[];
}

export interface NewProductApplicationPage {
  items: NewProductApplicationSummary[];
  total: number;
  page: number;
  limit: number;
}

/** PUT /feedback: one lead time, one cost per product; null clears. */
export interface NewProductApplicationFeedbackWrite {
  lead_time: string | null;
  lines: { id: string; cost_price: string | null }[];
}

/** GET /products rows (the only fields the screens read). */
export interface NewProductApplicationProductHit {
  id: string;
  product_code: string;
  product_name: string;
  brand_name: string | null;
}

/** A refusal that names a field arrives as `{message, code, details: {field}}`. */
export class NewProductApplicationError extends Error {
  readonly code: string | null;
  readonly field: string | null;

  constructor(message: string, code: string | null, field: string | null) {
    super(message);
    this.name = 'NewProductApplicationError';
    this.code = code;
    this.field = field;
  }
}
