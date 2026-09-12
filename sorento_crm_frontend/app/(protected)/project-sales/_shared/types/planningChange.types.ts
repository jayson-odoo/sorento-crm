/**
 * Planning changes wire shapes, transcribed from
 * `documentation/plans/scm/PLAN-so-book-diff-replanning.md` section 3.
 *
 * A batch is born the moment a sales order changes after it was planned - a re-uploaded
 * AutoCount book, an ESB push or a manual edit alike: what changed, what the line's decision
 * holds today, the re-run at the new state diffed against that hold (`suggestion`), and the
 * one decision CS takes per row - Confirm the composition or Amend it. Nothing here is
 * written until Apply.
 *
 * Slice C of `documentation/plans/scm/PLAN-scm-change-management-one-engine.md` replaced the
 * rule table's reaction verbs (`suggested` / `why`) with that diff: see the Slice C contract
 * section there for the wire shape this file mirrors.
 *
 * Quantities are decimal STRINGS for the same reason every other supply-composition figure in
 * this module is (see `fulfilmentPlanning.types.ts`): a float round trip loses the tail of a
 * quantity the customer signed for.
 */
import type { BoardContribution, ConfirmLine } from './fulfilmentPlanning.types';

/**
 * What changed on the line, exactly as the book's own diff names it (AC-R02).
 *
 * `cancelled` (renamed from `closed`) and `product_changed` are Slice A
 * (`documentation/plans/scm/PLAN-scm-change-management-one-engine.md`, rule 5): "closed" read
 * as a delivery outcome, not a change kind, and a product swap on the same line used to fall
 * apart into a closed row plus an unrelated added row.
 */
export type PlanningChangeKind =
  | 'delayed'
  | 'advanced'
  | 'qty_up'
  | 'qty_down'
  | 'cancelled'
  | 'added'
  | 'product_changed';

/**
 * What the diff did to ONE component of the plan (Slice C, rule 3).
 *
 * The first four are what the re-run did to something the line already HELD; the last four
 * are how quantity the re-run left uncovered is sourced. There is no `replan` and no
 * `retire`: a change is a re-run at the new state diffed against the hold, so every line of
 * the suggestion is one of these eight and nothing else.
 */
export type PlanningChangeSuggestionAction =
  | 'keep'
  | 'reduce'
  | 'release'
  | 'reallocate'
  | 'use_own'
  | 'borrow'
  | 'spo'
  | 'buy';

/** Where the quantity in a component comes from, or went to. `null` when it has no source. */
export type PlanningChangeSuggestionSource =
  | 'reserve'
  | 'borrow'
  | 'spo'
  | 'buy'
  | 'po'
  | 'pool_share'
  | null;

/**
 * One line of the suggestion, with the sentence the board prints for it.
 *
 * `label` is composed SERVER-side and printed verbatim: the engine is the only side that
 * knows which rung covered what, against which document, for whose order, so a second
 * composition in TypeScript could only drift from it. Everything beside it is there so the
 * line can be read as data (filters, the amend dialog, a future grouping), never so the
 * frontend can re-write the sentence.
 */
export interface PlanningChangeSuggestionComponent {
  action: PlanningChangeSuggestionAction;
  source: PlanningChangeSuggestionSource;
  /** What the component held before, when the action changed an existing figure. */
  qty_was?: string | null;
  qty_now: string;
  /** The warehouse the quantity sits in or is freed at, e.g. `BRW-IB`. */
  location?: string | null;
  /** The document the quantity is on: `PO-A`, `SPO-77`. Never a UUID. */
  document?: string | null;
  /** Where a reallocation went, in words: `dealer pool`, `SO420103 ORDER 50`, `pool`. */
  target?: string | null;
  /** On a `product_changed` row: the NEW product this component sources. */
  item_code?: string | null;
  /** The sentence the board prints, e.g. `Keep PO-A 100 of 134`. */
  label: string;
}

/**
 * The whole suggestion for one changed line: the diff of the re-run against what is held.
 *
 * Held components come first, in held order, then the new sourcing - so the reader sees what
 * happens to what they already decided before they read what is being added.
 */
export interface PlanningChangeSuggestion {
  components: PlanningChangeSuggestionComponent[];
  /** The unit is kept but lands N days after the line's new date (S12). `null` when on time. */
  late_days?: number | null;
  /** Quantity nothing can cover in time (S11). `null` when the unit is covered. */
  shortfall_qty?: string | null;
}

/**
 * The one decision per row: Confirm the composed suggestion, or Amend it. `null` until CS
 * takes one (AC-C7).
 *
 * `accept` / `keep` / `board` are retired with the rule table that produced them (Slice C):
 * "accept" existed because the suggestion was a VERB the row could agree with, and agreeing
 * with a verb executed nothing; the suggestion is now a composition, so Confirm posts it and
 * Amend edits it, and there is nothing else to say about a row.
 */
export type PlanningChangeDecision = 'confirm' | 'amend' | null;

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
  /** The old/new product on a `product_changed` row only. `null` on every other kind. */
  item_code?: string | null;
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

/** Whether purchasing already placed the Buy this line holds, and which PO it landed on. */
export interface PlanningChangeBuyActionedFact {
  value: boolean;
  po_number: string | null;
  /** The sum of every currently placed-or-actioned Buy on the line. */
  qty?: string | null;
}

/**
 * How much of this line's demand is already ON a document, and which one (S2, S12).
 *
 * Read off the placement LINKS, not the row's state: a row placed for part of its quantity
 * still reads `partly_linked` and keeps its full demand.
 */
export interface PlanningChangePlacedFact {
  qty: string;
  /** `PO-A`, `SPO-77`. Never a UUID. */
  document: string | null;
  /** When that supply is expected - what "late by N days" is measured from. */
  arrival_date: string | null;
}

/**
 * The facts the rule used to choose the verb (AC-R02): "nothing is inferred by the reader; the
 * row says which fact chose the verb, and the fact carries its own proof."
 *
 * `within_reserve_window` is RETIRED (Slice C rule 2): the ladder's own step 0 decides
 * whether a line that far out may hold stock, and a second window constant in the change
 * service could only disagree with it. What the row says now is what the re-run PROPOSED,
 * which already has that decision inside it.
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
  buy_actioned: PlanningChangeBuyActionedFact;
  placed: PlanningChangePlacedFact;
}

/** One Order Inquiry row this line already raised, as purchasing sees it today. */
export interface PlanningChangeInquiryRow {
  id: string;
  verb: string;
  qty: string;
  state: string;
}

/**
 * One changed planned line (AC-R02). `proposal` is the re-run itself - the same shape a board
 * cell's contribution is (AC-R07), so the row, the amend dialog and the board show one
 * proposal, not two; `suggestion` is that proposal DIFFED against `held`, which is what the
 * board prints.
 *
 * `applied_reason` carries `result_json` from the persisted row (section 2's data model) - it
 * is set when `applied_state` is `failed` (why the order's revision could not be written) or
 * `superseded` (why the row was skipped). Absent on every other state.
 */
export interface PlanningChangeRow {
  id: string;
  /**
   * The planning mirror line this row is about, so a board cell can be matched EXACTLY rather
   * than by product and sales order (AC-P3-2). `null` on an `added` row - the mirror does not
   * exist yet - and on a line whose order has no planning record.
   */
  project_line_id?: string | null;
  line_no: number;
  item_code: string;
  product_name?: string | null;
  kind: PlanningChangeKind;
  from: PlanningChangeFromTo;
  to: PlanningChangeFromTo;
  days_moved?: number | null;
  held: PlanningChangeHeld | null;
  facts: PlanningChangeFacts;
  /**
   * The diff of the re-run against what the line holds, as the board prints it (AC-C1).
   * `null` only on a row raised before Slice C, which has no composed suggestion to show.
   */
  suggestion: PlanningChangeSuggestion | null;
  proposal?: BoardContribution | null;
  inquiry_rows: PlanningChangeInquiryRow[];
  decision: PlanningChangeDecision;
  /**
   * What Apply posts for this line. PRE-FILLED at build from the re-run's own proposal, so
   * Confirm posts it unchanged and Amend edits it in the board's own `BoardAmendDialog`
   * (AC-C7). `null` on a row the engine could compose nothing for.
   */
  composition?: ConfirmLine | null;
  applied_state: PlanningChangeAppliedState;
  applied_reason?: string | null;
  /**
   * A transfer already MOVED for this line, in one phrase: `10 moved BRW -> BRW-IB, line
   * cancelled` (AC-P3-9). Stock that is physically somewhere else is a fact a person has to
   * act on, so it is stated rather than reversed automatically. `null` on every row with no
   * moved transfer, which is nearly all of them.
   */
  moved_transfer?: string | null;
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

/** The kind of upload/event that raised a batch. Must grow with the backend's
 *  PlanningChangeSourceKind literal - a value missing there 500s the listing. */
export type PlanningChangeSourceKind = 'so_book_upload' | 'so_manual_edit';

export const PLANNING_CHANGE_SOURCE_KIND_LABEL: Record<PlanningChangeSourceKind, string> = {
  so_book_upload: 'SO book upload',
  so_manual_edit: 'Manual SO edit',
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
  /**
   * B1 (code review, 20 Aug 2026): a revised order's PREVIOUS revision covered lines this
   * batch never named, and the new one (or, for a material change, no revision at all)
   * dropped them back to undecided as a side effect - never carried from a challenged or
   * superseded revision. Empty on a clean apply.
   */
  returned_to_review: PlanningChangeReturnedToReview[];
}

/** One order's silently-dropped bystander lines (B1). See `PlanningChangeResult.returned_to_review`. */
export interface PlanningChangeReturnedToReview {
  so_number: string;
  line_count: number;
  line_nos: number[];
  reason: string;
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
  /**
   * The sales orders this batch touched, by NUMBER (AC-P3-1). What the row's Plan action
   * addresses the board with - `?orders=SO381895&batch=<id>` - so the list needs no second
   * call to open the batch on the board it will be decided on.
   */
  so_numbers: string[];
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
  /** See `PlanningChangeResult.returned_to_review` - the same data, direct off the apply call. */
  returned_to_review: PlanningChangeReturnedToReview[];
}
