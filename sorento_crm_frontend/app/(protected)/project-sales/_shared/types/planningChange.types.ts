/**
 * Planning changes wire shapes, transcribed from
 * `documentation/plans/scm/PLAN-so-book-diff-replanning.md` section 3.
 *
 * A batch is born the moment a re-uploaded AutoCount sales-order book changes a line that is
 * already planned: what changed, what the line's decision holds today, what the ladder
 * suggests, and the one decision the planner takes per row (accept the suggestion, keep the
 * plan as is, or go decide it by hand on the board). Nothing here is written until Apply.
 *
 * Quantities are decimal STRINGS for the same reason every other supply-composition figure in
 * this module is (see `fulfilmentPlanning.types.ts`): a float round trip loses the tail of a
 * quantity the customer signed for.
 */
import type { BoardContribution, ConfirmLine } from './fulfilmentPlanning.types';

/** What changed on the line, exactly as the book's own diff names it (AC-R02). */
export type PlanningChangeKind = 'delayed' | 'advanced' | 'qty_up' | 'qty_down' | 'closed' | 'added';

/** The verb the planner already knows from the board (section 0's rule table). */
export type PlanningChangeReaction = 'keep' | 'release' | 'replan' | 'reduce' | 'retire';

/**
 * The one decision per row (AC-R04). `null` on a row with no active decision (AC-R03), or on
 * a `replan`/`qty_up` row nobody has composed yet (it defaults to `null` too - "Leave on the
 * board"): such a row offers no `accept`/`keep`, because there is nothing to accept - it simply
 * enters the board at its new date/quantity until composed or opened there.
 *
 * `confirm`/`amend` apply only to a row carrying a `proposal`: `confirm` takes the board's own
 * proposal as it stands (turned into a composition server-side); `amend` takes the composition
 * the planner built in the reused `BoardAmendDialog`. Recording either is what makes accepting
 * a replan row actually DO something at Apply, rather than a decision Apply never executes.
 */
export type PlanningChangeDecision = 'accept' | 'keep' | 'board' | 'confirm' | 'amend' | null;

/**
 * What Apply did to this row (AC-R05, R06, R07, R11). `pending` before Apply is pressed;
 * `superseded` when the order was re-planned on the board between review and apply (AC-R11).
 */
export type PlanningChangeAppliedState = 'pending' | 'applied' | 'failed' | 'superseded';

/**
 * The line's state at one side of the change: what it was, or what it is now.
 *
 * `required_date` is the wire field name (matches the AutoCount book's own column); the UI
 * never says "Required" - Sorento's own screens call it "Delivery date" throughout.
 */
export interface PlanningChangeFromTo {
  required_date?: string | null;
  qty?: string | null;
  status?: string | null;
}

/** One warehouse holding a Reserve for this line today. */
export interface PlanningChangeHeldReserve {
  location: string;
  warehouse_id?: string | null;
  qty: string;
}

/** One donor holding a Borrow for this line today. */
export interface PlanningChangeHeldBorrow {
  location: string;
  warehouse_id?: string | null;
  qty: string;
  source?: string | null;
}

/**
 * What the line's ACTIVE decision holds today, read the same way the board reads a covered
 * line's frozen composition (`BoardLineDecision`). `null` on a line with no active decision
 * (AC-R03).
 */
export interface PlanningChangeHeld {
  reserve: PlanningChangeHeldReserve[];
  borrow: PlanningChangeHeldBorrow[];
  buy_qty: string;
  timely_spo_qty: string;
  revision_no: number;
}

/**
 * A yes/no fact with its evidence: WHERE it was found, so a chip can be hovered rather than
 * taken on faith. `where` is a list of location codes, e.g. `['BRW', 'BRW-IB']`.
 */
export interface PlanningChangeEvidencedFact {
  value: boolean;
  where: string[];
}

/**
 * Whether the new date still lands inside the reserve window, and the window itself - not
 * just the verdict, so "beyond window" can say WHICH window and by how much.
 */
export interface PlanningChangeReserveWindowFact {
  value: boolean;
  /** The window's length in days (currently a flat 60). */
  window_days: number;
  /** The line's new delivery date - what the window is being checked against. */
  new_date: string;
  /** The window's own end date, measured from the line's previous delivery date. */
  window_end: string;
}

/** Whether purchasing already placed the Buy this line holds, and which PO it landed on. */
export interface PlanningChangeBuyActionedFact {
  value: boolean;
  po_number: string | null;
}

/**
 * The facts the rule used to choose the verb (AC-R02): "nothing is inferred by the reader; the
 * row says which fact chose the verb, and the fact carries its own proof."
 *
 * `dealer_hot_selling` is retail (dealer) demand: this item is inside the top 80% of quantity
 * delivered on dealer orders in the last 12 months, at the locations named. `project_hot_selling`
 * is the same classification read against PROJECT demand instead - a different demand pool, so
 * a line can be hot on one, the other, both, or neither. Both are proof-carrying so "hot
 * selling" is never asserted without saying which demand and where.
 */
export interface PlanningChangeFacts {
  dealer_hot_selling: PlanningChangeEvidencedFact;
  project_hot_selling: PlanningChangeEvidencedFact;
  discontinued: boolean;
  /** How many days the delivery date moved, negative for an advance. Mirrors the row's own. */
  days_moved: number;
  within_reserve_window: PlanningChangeReserveWindowFact;
  buy_actioned: PlanningChangeBuyActionedFact;
}

/** One Order Inquiry row this line already raised, as purchasing sees it today. */
export interface PlanningChangeInquiryRow {
  id: string;
  verb: string;
  qty: string;
  state: string;
}

/**
 * One changed planned line (AC-R02). `proposal` is present only for `replan` (advance / new
 * line) and the `qty_up` delta - the same shape a board cell's contribution is (AC-R07), so the
 * row and the board show one proposal, not two.
 *
 * `applied_reason` carries `result_json` from the persisted row (section 2's data model) - it
 * is set when `applied_state` is `failed` (why the order's revision could not be written) or
 * `superseded` (why the row was skipped). Absent on every other state.
 */
export interface PlanningChangeRow {
  id: string;
  line_no: number;
  item_code: string;
  product_name?: string | null;
  kind: PlanningChangeKind;
  from: PlanningChangeFromTo;
  to: PlanningChangeFromTo;
  days_moved?: number | null;
  held: PlanningChangeHeld | null;
  facts: PlanningChangeFacts;
  suggested: PlanningChangeReaction;
  why: string;
  proposal?: BoardContribution | null;
  inquiry_rows: PlanningChangeInquiryRow[];
  decision: PlanningChangeDecision;
  /** What Apply will post for this line - set only by `confirm`/`amend`. */
  composition?: ConfirmLine | null;
  applied_state: PlanningChangeAppliedState;
  applied_reason?: string | null;
  /** Deep link to the cell of this line on the board (AC-R04's "Open on the board"). */
  board_link: string;
}

/** One planned order the batch changed. */
export interface PlanningChangeOrder {
  project_sales_order_id: string;
  so_number: string;
  customer_name?: string | null;
  project_label?: string | null;
  revision_no: number;
  rows: PlanningChangeRow[];

  /**
   * Addressing only, never rendered: how the SO number reaches its own document (AC-R04's
   * "click the SO number"). An adopted order (mirror of the AutoCount book) opens
   * `/scm/sales-orders/{core_sales_order_id}`; an authored project SO opens
   * `/project-sales/{project_id}/sales-orders/{project_sales_order_id}`.
   */
  is_adopted: boolean;
  core_sales_order_id?: string | null;
  project_id?: string | null;
}

/** The kind of upload/event that raised a batch. One kind exists today; kept as a union. */
export type PlanningChangeSourceKind = 'so_book_upload';

export const PLANNING_CHANGE_SOURCE_KIND_LABEL: Record<PlanningChangeSourceKind, string> = {
  so_book_upload: 'SO book upload',
};

/** What raised the batch - the trigger, said as data rather than left to be inferred. */
export interface PlanningChangeBatchSource {
  upload_id: string;
  file_name: string;
  kind: PlanningChangeSourceKind;
  /**
   * The import job this upload ran as - `/system-management/import-jobs/{import_job_id}`.
   * `null` when the batch is not traceable to an import job (backend: `Optional[str]`).
   */
  import_job_id?: string | null;
}

/**
 * What Apply did, across the whole batch (AC-R05, AC-R06) - the "what happens next" a planner
 * asks after pressing Apply, read back as data: which orders got a new revision, which did
 * not and why, what purchasing's Order Inquiry list picked up, how many lines re-entered the
 * board, and whether purchasing was told.
 */
export interface PlanningChangeResult {
  orders_revised: { so_number: string; revision_no: number }[];
  orders_failed: { so_number: string; reason: string }[];
  /** One entry per Order Inquiry verb Apply raised or changed, e.g. `{ verb: 'DELAY', count: 2 }`. */
  inquiry_rows_changed: { verb: string; count: number }[];
  /** Lines that left the batch and re-entered the fulfilment planning board. */
  lines_replanned: number;
  /** Rows decided `confirm`/`amend` that Apply actually wrote. */
  lines_confirmed: number;
  purchasing_notified: boolean;
}

/** `GET /project-sales/planning-changes/{batch_id}`. */
export interface PlanningChangeBatch {
  id: string;
  created_at: string;
  /** `null` when the upload ran with no acting user (e.g. an API-key import). */
  created_by_name?: string | null;
  source: PlanningChangeBatchSource;
  applied_at?: string | null;
  applied_by_name?: string | null;
  /** `null` until Apply has run. */
  result?: PlanningChangeResult | null;
  orders: PlanningChangeOrder[];
}

/** Row of `GET /project-sales/planning-changes` (AC-R10). */
export interface PlanningChangeBatchSummary {
  id: string;
  created_at: string;
  /** `null` when the upload ran with no acting user (e.g. an API-key import). */
  created_by_name?: string | null;
  source: PlanningChangeBatchSource;
  order_count: number;
  line_count: number;
  /** Rows still pending a decision or an Apply. */
  pending_count: number;
  /** Rows Apply could not write, across every order. Drives the "Partly failed" pill. */
  failed_count: number;
  applied_at?: string | null;
  applied_by_name?: string | null;
}

export interface PlanningChangeListParams {
  page?: number;
  limit?: number;
  query?: string;
  state?: 'pending' | 'applied';
  sort?: string;
  dir?: 'asc' | 'desc';
}

export interface PlanningChangeListEnvelope {
  data: PlanningChangeBatchSummary[];
  total: number;
  page: number;
  limit: number;
}

/** `PUT /project-sales/planning-changes/{batch_id}/rows/{row_id}` body. */
export interface UpdatePlanningChangeRowBody {
  decision: PlanningChangeDecision;
  /** Required when `decision === 'amend'`; ignored otherwise. */
  composition?: ConfirmLine;
}

/** `POST /project-sales/planning-changes/{batch_id}/apply` response. */
export interface ApplyPlanningChangesResult {
  applied_orders: string[];
  failed_orders: { so_number: string; reason: string }[];
  already_applied: boolean;
}
