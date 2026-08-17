/**
 * Fulfilment Planning wire shapes (Stage 1B), transcribed from
 * `documentation/plans/scm/STAGE1B-scm-front-planning-reconciliation.md` section 3.
 *
 * The screen these feed answers one question: is this Project SO reconciled to the
 * AutoCount document yet, and if not, which line stops it. Nothing here carries a
 * per-line workflow state - the whole SO has exactly one pre-confirmation state
 * (AC-A03), so no line ever reads confirmed, partially confirmed or purchasing-ready.
 *
 * Quantities are decimal STRINGS for the same reason the sales-order lines are: a float
 * round trip loses the tail of a quantity the customer signed for.
 *
 * Fields the contract does not promise are optional, so a backend that has not shipped
 * one yet renders a stated absence rather than crashing.
 */

/**
 * The two values Stage 1B can produce. Stage 1C adds `confirmed` on top of these once an
 * active supply decision exists; nothing in this slice may invent a third.
 */
export type ReviewState = 'awaiting_reconciliation' | 'needs_cs_review';

export const REVIEW_STATE_LABELS: Record<ReviewState, string> = {
  awaiting_reconciliation: 'Awaiting reconciliation',
  needs_cs_review: 'Needs CS review',
};

/** Why the Project SO header is, or is not, attached to a core sales order. */
export type ReconciliationHeaderOutcome = 'no_document' | 'no_core_so' | 'linked';

/** What happened to one Project SO line when it was mapped against the core SO lines. */
export type ReconciliationLineLink = 'linked' | 'missing' | 'ambiguous';

/**
 * `surplus` is the only kind that has no Project line: it is a core line the AutoCount
 * document carries and the Project SO does not, so it is named by item code alone.
 */
export type ReconciliationExceptionKind = 'header' | 'missing' | 'ambiguous' | 'surplus';

/** Row of `GET /project-sales/fulfilment-planning`. */
export interface FulfilmentPlanningRow {
  id: string;
  provisional_ref: string;
  autocount_doc_no?: string | null;
  project_id: string;
  project_code: string;
  project_name: string;
  customer_name?: string | null;
  po_number?: string | null;
  area_group?: string | null;
  /** The existing sales-order status (published, amended, ...), not a review state. */
  status: string;
  line_count: number;
  lines_linked: number;
  exception_count: number;
  review_state: ReviewState;
  updated_at?: string | null;
}

export interface ReconciliationHeader {
  outcome: ReconciliationHeaderOutcome;
  /** The AutoCount number the core order carries. Never its id. */
  core_so_number?: string | null;
  /** The sentence the backend wrote. Shown as-is; the outcome code is never the message. */
  reason: string;
}

export interface ReconciliationLine {
  id: string;
  line_no: number;
  product_code?: string | null;
  description?: string | null;
  qty: string;
  uom?: string | null;
  delivery_date?: string | null;
  stock_location?: string | null;
  link: ReconciliationLineLink;
  /** How many core lines could still be this one. 1 on a linked line, 0 on a missing one. */
  candidate_count: number;
  reason: string;
}

export interface ReconciliationException {
  /** Absent on a surplus core line, which no Project line claims. */
  line_no?: number | null;
  item_code?: string | null;
  kind: ReconciliationExceptionKind;
  message: string;
}

/**
 * `GET /project-sales/sales-orders/{pso_id}/reconciliation`, and the body
 * `POST .../reconcile` answers with after it has written the links.
 */
export interface ReconciliationSummary {
  project_sales_order_id: string;
  provisional_ref: string;
  autocount_doc_no?: string | null;
  project_id: string;
  project_code: string;
  project_name: string;
  customer_name?: string | null;
  po_number?: string | null;
  area_group?: string | null;
  status: string;
  review_state: ReviewState;
  header: ReconciliationHeader;
  lines: ReconciliationLine[];
  exceptions: ReconciliationException[];
  lines_total: number;
  lines_linked: number;
  /**
   * When reconciliation last ran for this order. Added to the section 3 contract on
   * 2026-08-17 because the journey's header strip states it ("Reconciled at" when known)
   * and the original shape carried no timestamp at all. Optional: an order the engine has
   * never been run against states that instead of printing a date it does not have.
   */
  reconciled_at?: string | null;
}

export interface FulfilmentPlanningListParams {
  page?: number;
  limit?: number;
  query?: string;
  review_state?: ReviewState;
  project_id?: string;
  /**
   * Mock-only. Selects a whole-list fixture case (`empty`, `error`) while
   * `NEXT_PUBLIC_PROJECT_SO_MOCK=1`; the real service drops it, and the backend never
   * sees it. Remove with the fixtures when Phase 2 lands.
   */
  mock_case?: string;
}

export interface FulfilmentPlanningListEnvelope {
  data: FulfilmentPlanningRow[];
  total: number;
  page: number;
  limit: number;
}
