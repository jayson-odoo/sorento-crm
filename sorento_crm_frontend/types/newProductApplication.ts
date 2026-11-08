/**
 * New product application shapes (NEW-PRODUCT-APP), shared by the staff feature and the portal.
 * Names are the backend contract in
 * documentation/plans/procurement/PLAN-new-product-application-17oct.md ("API contract (as built)").
 */

export type NewProductApplicationStatus =
  | 'draft'
  | 'submitted'
  | 'resubmitted'
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
  /** The PRODUCT CODES this application is based on (header): left out keeps, [] clears. */
  current_product_ids?: string[];
  lines?: NewProductApplicationLineWrite[];
}

/** One current code on a line. */
export interface NewProductApplicationCurrentProduct {
  id: string;
  product_code: string;
  product_name?: string | null;
  is_active?: boolean;
}

/** GET /prefill: a Write-shaped body copied as text, plus the inquiry's number. */
export interface NewProductApplicationPrefill extends NewProductApplicationWrite {
  stock_inquiry_number: string | null;
  /** The product codes the inquiry's code text matched exactly (none when it did not). */
  current_products?: NewProductApplicationCurrentProduct[];
}

/** A code already created from exactly the same current codes (information only). */
export interface NewProductApplicationSuggestion {
  /** Null for a typed code AutoCount has not sent yet. */
  product_id: string | null;
  product_code: string;
  product_name: string | null;
  is_active: boolean;
  /** The earlier line's PRODUCT TYPE text. */
  description: string | null;
  created_at: string | null;
  /** Staff only: the portal drops both. */
  application_id?: string | null;
  application_no?: string | null;
}

/** A code made through an application, on the summary and the stock inquiry lists. */
export interface NewProductApplicationCreatedCode {
  product_code: string;
  current_codes: string[];
  created_at: string | null;
}

export interface NewProductApplicationSummary {
  id: string;
  application_no: string;
  status: NewProductApplicationStatus;
  status_label: string;
  /** "rejected" for an older Not opening result (owner 8 Nov); otherwise the status. */
  display_status?: string;
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
  created_codes?: NewProductApplicationCreatedCode[];
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

/** The stock inquiry an application was raised from (detail only). */
export interface NewProductApplicationStockInquiry {
  id: string;
  inquiry_number: string | null;
  product_code: string | null;
  status: string | null;
  item_description: string | null;
  purchasing_response: string | null;
  quantity: string | number | null;
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
  stock_inquiry?: NewProductApplicationStockInquiry | null;
  current_products?: NewProductApplicationCurrentProduct[];
  suggestions?: NewProductApplicationSuggestion[];
  /** The ONE new product code purchasing links (an older Not opening reason reads Rejected). */
  new_product_id?: string | null;
  /** Purchasing's written answer, like the stock inquiry's. */
  purchasing_response?: string | null;
  /** Update & Reply is offered (the inquiry's conversation exists and is writable). */
  can_reply?: boolean;
  /** The code purchasing typed when it is not in the catalogue yet. */
  new_code_text?: string | null;
  /** COST (MYR) of an application with no product rows. */
  cost_price?: string | number | null;
  new_product_code?: string | null;
  new_product_name?: string | null;
  new_product_active?: boolean | null;
  new_code_closed_reason?: string | null;
  new_code_by_name?: string | null;
  new_code_at?: string | null;
  /** Read from the linked product; the portal gets the supplier only. */
  new_product_facts?: {
    opened_category_name?: string | null;
    opened_base_uom_name?: string | null;
    opened_list_price?: string | number | null;
    opened_supplier_name?: string | null;
  } | null;
}

export interface NewProductApplicationPage {
  items: NewProductApplicationSummary[];
  total: number;
  page: number;
  limit: number;
}

/** PUT /purchasing-response: purchasing's one save. A key left out is unchanged; */
export interface NewProductApplicationPurchasingResponseWrite {
  purchasing_response?: string;
  outcome?: 'link' | 'new';
  product_id?: string;
  new_code?: string;
  reason?: string;
  lead_time?: string | null;
  cost_price?: string | null;
  lines?: { id: string; cost_price: string | null }[];
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

/** One row of a product's lineage (GET /lineage). The last three are for NPA view-all only. */
export interface NewProductApplicationLineageRow {
  application_no: string | null;
  /** Null for a typed code AutoCount has not sent yet. */
  product_id: string | null;
  product_code: string;
  product_name: string | null;
  is_active: boolean;
  current_products: NewProductApplicationCurrentProduct[];
  description: string | null;
  expected_qty: string | number | null;
  created_at: string | null;
  application_id?: string | null;
  customer_name?: string | null;
  project_name?: string | null;
}

export interface NewProductApplicationLineage {
  created_from: NewProductApplicationLineageRow[];
  made_from_this: NewProductApplicationLineageRow[];
}

/** A refusal that names a field arrives as `{message, code, details: {field}}`. */
export class NewProductApplicationError extends Error {
  readonly code: string | null;
  readonly field: string | null;
  /** The HTTP status of the refusal, when it came from a response. */
  readonly status: number | null;

  constructor(
    message: string,
    code: string | null,
    field: string | null,
    status: number | null = null,
  ) {
    super(message);
    this.status = status;
    this.name = 'NewProductApplicationError';
    this.code = code;
    this.field = field;
  }
}
