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
import type { BoardContribution } from './fulfilmentPlanning.types';

/** What changed on the line, exactly as the book's own diff names it (AC-R02). */
export type PlanningChangeKind = 'delayed' | 'advanced' | 'qty_up' | 'qty_down' | 'closed' | 'added';

/** The verb the planner already knows from the board (section 0's rule table). */
export type PlanningChangeReaction = 'keep' | 'release' | 'replan' | 'reduce' | 'retire';

/**
 * The one decision per row (AC-R04). `null` on a row with no active decision (AC-R03): such a
 * row shows `Not decided` and offers no control at all, because there is nothing to accept or
 * keep - it simply enters the board at its new date/quantity.
 */
export type PlanningChangeDecision = 'accept' | 'keep' | 'board' | null;

/**
 * What Apply did to this row (AC-R05, R06, R07, R11). `pending` before Apply is pressed;
 * `superseded` when the order was re-planned on the board between review and apply (AC-R11).
 */
export type PlanningChangeAppliedState = 'pending' | 'applied' | 'failed' | 'superseded';

/** The line's state at one side of the change: what it was, or what it is now. */
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
 * The facts the rule used to choose the verb (AC-R02): "nothing is inferred by the reader; the
 * row says which fact chose the verb."
 */
export interface PlanningChangeFacts {
  dealer_hot_selling: boolean;
  discontinued: boolean;
  within_reserve_window: boolean;
  buy_actioned: boolean;
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
}

/** `GET /project-sales/planning-changes/{batch_id}`. */
export interface PlanningChangeBatch {
  id: string;
  created_at: string;
  created_by_name: string;
  source: { upload_id: string; file_name: string };
  applied_at?: string | null;
  applied_by_name?: string | null;
  orders: PlanningChangeOrder[];
}

/** Row of `GET /project-sales/planning-changes` (AC-R10). */
export interface PlanningChangeBatchSummary {
  id: string;
  created_at: string;
  created_by_name: string;
  source: { upload_id: string; file_name: string };
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
}

/** `POST /project-sales/planning-changes/{batch_id}/apply` response. */
export interface ApplyPlanningChangesResult {
  applied_orders: string[];
  failed_orders: { so_number: string; reason: string }[];
  already_applied: boolean;
}
