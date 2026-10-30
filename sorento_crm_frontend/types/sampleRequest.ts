/**
 * Sample request shapes (SR-CORE), shared by the staff feature and the portal form.
 * Names are the backend contract in documentation/plans/projects/PLAN-sample-request-core-15oct.md.
 */

export type SampleRequestStatus =
  | 'draft'
  | 'submitted'
  | 'processing'
  | 'customer_confirmed'
  | 'delivered'
  | 'cancelled';

export type SampleRequestDeliveryMode = 'driver' | 'self_deliver' | 'self_collect';
export type SampleRequestLoanUnit = 'days' | 'months';
export type SampleRequestGoodsFrom = 'demo' | 'new' | 'either';

export const DELIVERY_MODE_LABELS: Record<SampleRequestDeliveryMode, string> = {
  driver: 'Deliver-Van',
  self_deliver: 'Self-Deliver',
  self_collect: 'Self-Collection',
};

export const GOODS_FROM_LABELS: Record<SampleRequestGoodsFrom, string> = {
  demo: 'Demo Sets',
  new: 'New Goods',
  either: 'Either',
};

/** One line as written (create and draft update replace all lines). */
export interface SampleRequestLineInput {
  product_id: string;
  qty: number;
  remark: string | null;
}

/** The write payload, staff and portal alike. */
export interface SampleRequestWrite {
  customer_id?: string | null;
  customer_name?: string | null;
  project_id?: string | null;
  project_title?: string | null;
  /** The quotation the lines were pre-filled from (SAMPLE-FROM-QUOTE); the issue is null when it was never issued. */
  quotation_document_id?: string | null;
  quotation_issue_id?: string | null;
  scope_note?: string | null;
  delivery_date?: string | null;
  delivery_mode?: SampleRequestDeliveryMode | null;
  ship_to_name?: string | null;
  ship_to_address?: string | null;
  site_contact_name?: string | null;
  site_contact_phone?: string | null;
  site_contact_note?: string | null;
  loan_value?: number;
  loan_unit?: SampleRequestLoanUnit;
  goods_from?: SampleRequestGoodsFrom;
  purpose?: string | null;
  board_mounting?: boolean;
  board_label?: string | null;
  lines?: SampleRequestLineInput[];
}

export interface SampleRequestLine {
  id: string;
  line_no: number;
  product_id: string;
  product_code: string | null;
  product_name: string | null;
  brand_name: string | null;
  product_active: boolean;
  qty: number;
  remark: string | null;
}

export interface SampleRequestDetail extends SampleRequestWrite {
  id: string;
  request_no: string;
  status: SampleRequestStatus;
  status_label: string;
  source: 'staff' | 'portal';
  salesperson_id: string | null;
  salesperson_name: string | null;
  customer_code: string | null;
  project_code: string | null;
  project_name: string | null;
  /** The source quotation as a person reads it, e.g. `<document no> (R2)`; null when none. */
  quotation_ref: string | null;
  request_date: string | null;
  submitted_at: string | null;
  confirmed_at: string | null;
  delivered_at: string | null;
  return_due: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  consignment_no: string | null;
  po_no: string | null;
  created_at: string | null;
  updated_at: string | null;
  lines: SampleRequestLine[];
}

/** A list row. Never carries the site contact phone or the ship-to address. */
export interface SampleRequestRow {
  id: string;
  request_no: string;
  status: SampleRequestStatus;
  status_label: string;
  request_date: string | null;
  submitted_at: string | null;
  delivery_date: string | null;
  delivery_mode: SampleRequestDeliveryMode | null;
  customer_name: string | null;
  customer_code: string | null;
  project_id: string | null;
  project_name: string | null;
  ship_to_name: string | null;
  salesperson_name: string | null;
  line_count: number;
  board_mounting: boolean;
}

/** The source quotation a product search is narrowed to (SFQ-27). */
export interface SampleRequestProductSource {
  quotation_document_id: string;
  quotation_issue_id: string | null;
}

/** One quotation document of the project, as the pre-fill picker lists it. */
export interface SampleRequestQuotationOption {
  id: string;
  document_no: string;
  issue_id: string | null;
  issue_no: number | null;
  /** `<document no> (R2)` or `<document no> (not issued)`. */
  label: string;
}

/** A quotation line that could not become a sample line. */
export interface SampleRequestPrefillSkip {
  reason: 'no_product' | 'inactive';
  description: string;
}

/** The rows a new request on a project starts with (SAMPLE-FROM-QUOTE). No prices. */
export interface SampleRequestQuotationPrefill {
  documents: SampleRequestQuotationOption[];
  document_id: string | null;
  issue_id: string | null;
  lines: { product_id: string; product_code: string; product_name: string; brand_name: string | null }[];
  skipped: SampleRequestPrefillSkip[];
}

export interface SampleRequestProductHit {
  id: string;
  product_code: string;
  product_name: string;
  brand_name: string | null;
}

export interface SampleRequestPage {
  data: SampleRequestRow[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}

/** A refusal that names the payload key it is about (`details.field`). */
export class SampleRequestError extends Error {
  readonly code: string | null;
  readonly field: string | null;

  constructor(message: string, code: string | null, field: string | null) {
    super(message);
    this.name = 'SampleRequestError';
    this.code = code;
    this.field = field;
  }
}
