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
 * The whole sales order's one state. `confirmed` is Stage 1C's addition and means an
 * ACTIVE supply decision exists; a superseded or challenged decision reads
 * `needs_cs_review` again, so there is never a fourth value and never a per-line one.
 */
export type ReviewState = 'awaiting_reconciliation' | 'needs_cs_review' | 'confirmed';

export const REVIEW_STATE_LABELS: Record<ReviewState, string> = {
  awaiting_reconciliation: 'Awaiting reconciliation',
  needs_cs_review: 'Needs CS review',
  confirmed: 'Confirmed',
};

/** Why the Project SO header is, or is not, attached to a core sales order. */
export type ReconciliationHeaderOutcome = 'no_document' | 'no_core_so' | 'linked';

/**
 * What happened to one Project SO line when it was mapped against the core SO lines.
 * `duplicate` is the core line another Project SO already holds, which is a different
 * problem from `missing`: the line exists, it is just not this sales order's to take.
 */
export type ReconciliationLineLink = 'linked' | 'missing' | 'ambiguous' | 'duplicate';

/**
 * `surplus` is the only kind that has no Project line: it is a core line the AutoCount
 * document carries and the Project SO does not, so it is named by item code alone.
 */
export type ReconciliationExceptionKind =
  | 'header'
  | 'missing'
  | 'ambiguous'
  | 'duplicate'
  | 'surplus';

/** Row of `GET /project-sales/fulfilment-planning`. */
export interface FulfilmentPlanningRow {
  id: string;
  provisional_ref: string;
  autocount_doc_no?: string | null;
  project_id: string;
  project_code?: string | null;
  project_name?: string | null;
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
  /**
   * How many core lines could still be this one: 1 on a linked line, the number of core
   * candidates at that product and date on an ambiguous one, 0 otherwise.
   */
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
  project_code?: string | null;
  project_name?: string | null;
  customer_name?: string | null;
  po_number?: string | null;
  area_group?: string | null;
  status: string;
  /**
   * Null on an order that is not published or amended: a draft is reconciled against
   * nothing, so it carries no state rather than one it has not earned (AC-A03), and
   * `ReviewStatePill` renders nothing for it.
   */
  review_state: ReviewState | null;
  header: ReconciliationHeader;
  lines: ReconciliationLine[];
  exceptions: ReconciliationException[];
  lines_total: number;
  lines_linked: number;
}

export interface FulfilmentPlanningListParams {
  page?: number;
  limit?: number;
  query?: string;
  review_state?: ReviewState;
  project_id?: string;
}

// ---------------------------------------------------------------------------
// Stage 1C: supply composition and atomic confirmation
// ---------------------------------------------------------------------------

/**
 * The four ways a line's open quantity can be met (plan 3.1). `timely_spo` is dated
 * location supply rather than a CS decision, so CS never types its quantity; the other
 * three are the components CS composes.
 */
export type SupplyComponentKind = 'timely_spo' | 'reserve' | 'borrow' | 'buy';

/** Where a Borrow comes from: free stock at another location, or another project's hold. */
export type BorrowSource = 'other_location' | 'other_project';

export type SupplyDecisionState = 'active' | 'superseded' | 'challenged';

export interface SupplyComponent {
  kind: SupplyComponentKind;
  qty: string;
  /**
   * The short sentence the rule that produced the quantity wrote (AC-B14), for example
   * "Reserve 10: free stock at BRW covers the need by the required date". Deterministic,
   * frozen with the snapshot at confirmation, and shown beside the quantity always.
   */
  reason: string;
  /** Warehouse CODE. The pool code on a BRW-pool Reserve, the donor's on a Borrow. */
  source_location?: string | null;
  /**
   * Addressing only, never rendered: the confirm payload names warehouses by id, and the
   * screen names them by code. Same reason `ReconciliationLine.id` exists.
   */
  source_warehouse_id?: string | null;
  /** The donor project's human reference on a cross-project Borrow. Never its id. */
  donor_project_ref?: string | null;
  donor_project_id?: string | null;
  /** What CS typed: the Borrow reason, or the reason a discontinued product is bought. */
  cs_reason?: string | null;
}

/** One incoming SPO leg at the line's location. Timely covers, advisory does not. */
export interface SupplySpoRef {
  spo_number: string;
  arrival_date?: string | null;
  qty: string;
}

/** What Borrowing this quantity does to whoever holds it now (AC-B09). */
export interface BorrowDonorImpact {
  free_before: string;
  free_after_full_borrow: string;
  /** Already committed to another sales order at that location. */
  committed_qty: string;
}

export interface BorrowCandidate {
  source: BorrowSource;
  warehouse_code: string;
  /** Addressing only (see `SupplyComponent.source_warehouse_id`). */
  warehouse_id: string;
  donor_project_ref?: string | null;
  donor_project_id?: string | null;
  free_qty: string;
  donor_impact: BorrowDonorImpact;
}

/** The components as they were frozen at confirmation, read back on a confirmed order. */
export interface SupplyFrozenLine {
  open_qty: string;
  components: SupplyComponent[];
}

export interface SupplyLine {
  project_line_id: string;
  line_no: number;
  item_code?: string | null;
  description?: string | null;
  uom?: string | null;
  /** The core line's current open fulfilment quantity (AC-B01), in the line UOM. */
  open_qty: string;
  required_date?: string | null;
  /** Warehouse CODE of the line's fulfilment location. */
  fulfilment_location?: string | null;
  is_dealer_hot_selling: boolean;
  /** No classification row at any qualifying dealer warehouse (AC-B05). */
  classification_unavailable: boolean;
  is_discontinued: boolean;
  pool_location?: string | null;
  /** `max(pool free - coalesce(pool reorder level, 0), 0)` when hot-selling (AC-B06). */
  pool_cap?: string | null;
  pool_reorder_level?: string | null;
  components: SupplyComponent[];
  timely_spo: SupplySpoRef[];
  advisory_spo: SupplySpoRef[];
  borrow_candidates: BorrowCandidate[];
  frozen?: SupplyFrozenLine | null;
}

export interface SupplyDecision {
  revision_no: number;
  state: SupplyDecisionState;
  confirmed_by_name?: string | null;
  confirmed_at?: string | null;
  /** Why the active revision no longer matches the order. Present when challenged. */
  challenged_reason?: string | null;
}

/** A line the server will not confirm, named the only way it may be (AC-C02). */
export interface SupplyFailingLine {
  line_no: number;
  item_code?: string | null;
  reason: string;
}

/** `GET /project-sales/sales-orders/{pso_id}/supply`. */
export interface SupplyProposal {
  project_sales_order_id: string;
  provisional_ref: string;
  autocount_doc_no?: string | null;
  project_id: string;
  project_code?: string | null;
  project_name?: string | null;
  status: string;
  review_state: ReviewState | null;
  decision?: SupplyDecision | null;
  lines: SupplyLine[];
  failing_lines?: SupplyFailingLine[];
}

export interface ConfirmReserveComponent {
  warehouse_id: string;
  qty: string;
}

export interface ConfirmBorrowComponent {
  source: BorrowSource;
  warehouse_id: string;
  donor_project_id?: string | null;
  qty: string;
  /** Mandatory: no Borrow is written without one (AC-B09). */
  reason: string;
}

export interface ConfirmLine {
  project_line_id: string;
  timely_spo_qty: string;
  reserve: ConfirmReserveComponent[];
  borrow: ConfirmBorrowComponent[];
  buy_qty: string;
  /** Mandatory when the product is discontinued and `buy_qty > 0` (AC-B11). */
  buy_reason?: string | null;
}

export interface ConfirmSupplyBody {
  lines: ConfirmLine[];
}

export interface ConfirmException {
  line_no: number;
  item_code?: string | null;
  message: string;
}

/** `POST /project-sales/sales-orders/{pso_id}/confirm`. */
export interface ConfirmResult {
  revision_no: number;
  confirmed_at: string;
  review_state: 'confirmed';
  inquiry_rows_created: number;
  exceptions: ConfirmException[];
}

export interface FulfilmentPlanningListEnvelope {
  data: FulfilmentPlanningRow[];
  total: number;
  page: number;
  limit: number;
}
