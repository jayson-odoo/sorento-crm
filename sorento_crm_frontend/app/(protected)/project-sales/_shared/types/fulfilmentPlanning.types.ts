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
 * `needs_cs_review` again, so there is never a per-line one.
 *
 * `not_started` is the AutoCount-driven plan's addition (PLAN-fulfilment-planning-from-
 * autocount-so section 6): an outstanding project-class sales order that nobody has
 * planned yet. It is the state of a row that has no planning record at all, which is why
 * a `not_started` row carries no `id` and no `provisional_ref`.
 */
export type ReviewState =
  | 'not_started'
  | 'awaiting_reconciliation'
  | 'needs_cs_review'
  | 'confirmed';

export const REVIEW_STATE_LABELS: Record<ReviewState, string> = {
  not_started: 'Not started',
  awaiting_reconciliation: 'Awaiting reconciliation',
  needs_cs_review: 'Needs CS review',
  confirmed: 'Confirmed',
};

/**
 * Why the Project SO header is, or is not, attached to a core sales order.
 *
 * `adopted` is the AutoCount-driven arm: the planning record WAS the core sales order, so
 * there is no separately authored document to disagree with and reconciliation is a one-way
 * sync rather than a diff.
 */
export type ReconciliationHeaderOutcome =
  | 'no_document'
  | 'no_core_so'
  | 'linked'
  | 'adopted';

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

/**
 * Row of `GET /project-sales/fulfilment-planning`.
 *
 * The worklist is a union of two arms, one row per subject, and the arms are disjoint by
 * construction: arm 1 is an outstanding core sales order (`row_kind = 'sales_order'`), arm
 * 2 is a planning record that has no core sales order yet (`row_kind = 'planning_record'`).
 * A core order that HAS been planned still comes back as arm 1, carrying the planning
 * record's `id` and state.
 *
 * Everything a not-started row cannot have is optional, because it genuinely does not exist
 * yet: no planning record means no `id`, no `provisional_ref`, no `status`, and no counts
 * off a mirror nobody has written. `project_id` is nullable because an adopted order has no
 * project registration and must not invent one.
 */
export interface FulfilmentPlanningRow {
  /** Which arm this row came from. Addressing only, never rendered. */
  row_kind?: 'sales_order' | 'planning_record';
  /** The planning record's id. Absent on a not-started row: there is no record. */
  id?: string | null;
  /** The core `sales_orders` id, for addressing the SCM sales order. Never rendered. */
  sales_order_id?: string | null;
  /** The AutoCount / core sales-order number. The human key of an arm-1 row. */
  so_number?: string | null;
  /** Whether the planning record was authored here or adopted from the core book. */
  origin?: 'authored' | 'adopted' | null;
  provisional_ref?: string | null;
  autocount_doc_no?: string | null;
  project_id?: string | null;
  project_code?: string | null;
  project_name?: string | null;
  /** The project name when one is registered, else the core order's own project string. */
  project_label?: string | null;
  customer_name?: string | null;
  po_number?: string | null;
  area_group?: string | null;
  /** The existing sales-order status (published, amended, adopted, ...), not a review state. */
  status?: string | null;
  line_count: number;
  lines_linked?: number;
  exception_count?: number;
  /** Decimal STRING, summed over the still-owed lines. Same reason line quantities are. */
  outstanding_qty?: string | null;
  /** Earliest still-owed required date across the lines. The order the work is due in. */
  earliest_required_date?: string | null;
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
  /** Nullable: an adopted order has no project registration. */
  project_id?: string | null;
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

/**
 * The columns the server can order the union by, and therefore the only ones the worklist
 * offers a sort affordance on. A header that toggled a sort the server ignores would look like
 * a broken control, so the closed set lives here and drives both the grid and the URL.
 */
export const FULFILMENT_PLANNING_SORT_FIELDS = [
  'so_number',
  'customer_name',
  'project_label',
  'earliest_required_date',
  'outstanding_qty',
  'line_count',
  'review_state',
  'provisional_ref',
  'po_number',
  'area_group',
  'updated_at',
] as const;

export type FulfilmentPlanningSortField = (typeof FULFILMENT_PLANNING_SORT_FIELDS)[number];

export interface FulfilmentPlanningListParams {
  page?: number;
  limit?: number;
  query?: string;
  review_state?: ReviewState;
  project_id?: string;
  sales_order_id?: string;
  /** One of `FULFILMENT_PLANNING_SORT_FIELDS`. Omitted leaves the server's own order. */
  sort?: string;
  dir?: 'asc' | 'desc';
}

/**
 * What Start planning answers with (`POST /project-sales/fulfilment-planning/adopt`).
 *
 * Adoption is idempotent: pressing it twice, or a second CS pressing it, returns the record
 * that already exists with `already_adopted` true rather than writing a second one. That is
 * why it takes no confirmation dialog - it destroys nothing and it repeats safely.
 */
export interface AdoptSalesOrderResult {
  project_sales_order_id: string;
  so_number: string;
  review_state: ReviewState;
  already_adopted: boolean;
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

/**
 * A donor, with its OWN position beside what it could give (PLAN 13.11).
 *
 * The captain, on a list that stated free stock alone: "before I decide to borrow, I need to
 * know I am not hurting them". Free nets reserved and confirmed holds only, so it reads as
 * raw on-hand on this book; the AutoCount triple is what says whether they can spare it.
 *
 * The server RANKS the list by what meeting THIS line would leave each donor with
 * (`available_after_need`, then availability, then free) and flags exactly one row
 * `recommended`. The screen never re-sorts it: a list that reshuffles as a quantity is typed
 * is not a recommendation.
 */
export interface BorrowCandidate {
  source: BorrowSource;
  warehouse_code: string;
  /** Addressing only (see `SupplyComponent.source_warehouse_id`). */
  warehouse_id: string;
  donor_project_ref?: string | null;
  donor_project_id?: string | null;
  /** What this donor can give: the location's free stock, or the donor project's own hold. */
  free_qty: string;
  /** AutoCount's Stock Status columns for the donor's own (product, location) pile. */
  qty_on_hand?: string | null;
  so_qty?: string | null;
  spo_qty?: string | null;
  /** on hand - SO + SPO. Signed: a donor the book has oversold says so. */
  available_qty?: string | null;
  qty_free?: string | null;
  qty_committed?: string | null;
  /** What this line still has to cover at the borrow rung: the Buy the ladder proposed. */
  need_qty?: string | null;
  /** `available_qty - need_qty`, signed. The ranking key, and the default "After borrow". */
  available_after_need?: string | null;
  /** First in the ranking. Exactly one candidate carries it. */
  recommended?: boolean;
  donor_impact: BorrowDonorImpact;
}

/** The components as they were frozen at confirmation, read back on a confirmed order. */
export interface SupplyFrozenLine {
  open_qty: string;
  components: SupplyComponent[];
  /** The reason given for overriding the proposal, when one was. Absent otherwise. */
  amend_reason?: string | null;
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
  /**
   * Warehouse CODE of the line's fulfilment location, read off the CORE sales-order line's
   * own `warehouse_id`. Nobody is asked for it and nothing defaults it (captain's decision,
   * PLAN-fulfilment-planning-from-autocount-so section 11 question 2).
   */
  fulfilment_location?: string | null;
  /**
   * The core sales-order line states no warehouse, so this line cannot be planned against a
   * location at all. Nothing is proposed for it and Confirm refuses it by name; the way out
   * is to state the location on the SCM sales order, which the sheet links to. Never a
   * guessed default.
   */
  fulfilment_location_missing?: boolean;
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

/**
 * A line the server will not confirm, named the only way it may be (AC-C02).
 *
 * `line_no` is optional because a refusal can be about the sales order rather than about
 * one of its lines (nothing is mapped yet, the order moved on underneath the sheet), and
 * the screen then names the order instead - the same rule `ReconciliationException`
 * follows for a surplus core line.
 */
export interface SupplyFailingLine {
  line_no?: number | null;
  item_code?: string | null;
  reason: string;
}

/** `GET /project-sales/sales-orders/{pso_id}/supply`. */
export interface SupplyProposal {
  project_sales_order_id: string;
  provisional_ref: string;
  autocount_doc_no?: string | null;
  /** The core sales-order number. The human key of an adopted order. */
  sales_order_number?: string | null;
  /** The core `sales_orders` id. Addressing only, for the /scm link; never rendered. */
  sales_order_id?: string | null;
  /** Nullable: an adopted order has no project registration. */
  project_id?: string | null;
  project_code?: string | null;
  project_name?: string | null;
  status?: string | null;
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
  /**
   * Why this composition is not the engine's, in the planner's own words. Frozen with the
   * line: every other component carries the sentence of the RULE that produced it, and those
   * explain a decision nobody took once a person has overridden them.
   */
  amend_reason?: string | null;
}

export interface ConfirmSupplyBody {
  lines: ConfirmLine[];
}

export interface ConfirmException {
  line_no?: number | null;
  item_code?: string | null;
  message: string;
}

/** `POST /project-sales/sales-orders/{pso_id}/confirm`. */
export interface ConfirmResult {
  revision_no: number;
  confirmed_at?: string | null;
  review_state: string;
  inquiry_rows_created: number;
  exceptions: ConfirmException[];
}

export interface FulfilmentPlanningListEnvelope {
  data: FulfilmentPlanningRow[];
  total: number;
  page: number;
  limit: number;
}

// ---------------------------------------------------------------------------
// The multi-order planning board (PLAN section 13)
//
// The board is a LENS (section 13.4): it reads across several sales orders and writes no
// decision object of its own. The persisted decision stays per sales order, atomic across
// its lines, exactly where Stage 1C put it. Everything below is either a read model or the
// board's own working draft.
//
// Axis naming is deliberate: `dateBuckets` across, `productRows` down. The delivery-schedule
// matrix calls a PRODUCT a `column` (its API's word, kept even after that grid was
// transposed), so borrowing its vocabulary would leave two grids using one word for opposite
// things.
// ---------------------------------------------------------------------------

/**
 * How the date axis is cut, as a calendar control: day, week or month (13.3, captain's
 * decision). Week is the default. Day renders a scrolling 30-day window rather than a column
 * per distinct date, because the book carries 349 of them.
 */
export type BoardGranularity = 'day' | 'week' | 'month';

/**
 * A column of the board. Every dated column is a real date, however far past (the captain,
 * verbatim: "don't put overdue together, still split by the date, don't put under overdue").
 * `no_date` is the one answer that has no place on a timeline, and it is pinned last.
 */
export type BoardBucketKind = 'dated' | 'no_date';

export interface BoardDateBucket {
  key: string;
  kind: BoardBucketKind;
  /** What the column header reads. Already formatted for display. */
  label: string;
  /** ISO date of the bucket start, for a dated bucket only. Ordering key. */
  start?: string | null;
  /**
   * The bucket's WHOLE period ended before the board's `as_of`, so nothing in it can still be
   * met on time. The period CONTAINING `as_of` is false - some of its dates are still to come,
   * and tinting this week as lost would be wrong - and `no_date` is always false.
   *
   * The SERVER's verdict, read and never re-derived, for the same reason
   * `BoardPolicy.discriminates_nothing` is: only the side that did the bucketing knows where a
   * week or month falls relative to `as_of`, and a tint derived here would disagree with the
   * columns it is painting.
   *
   * This is the TINT only. The count of late lines comes from `BoardContribution.is_past`,
   * which is a different question - see there.
   */
  is_past?: boolean;
}

/**
 * How a contributing line's quantity is proposed to be met. Mirrors SupplyComponentKind.
 *
 * `borrow` only ever appears on a COVERED line. The engine proposes none on either surface - a
 * Borrow needs a donor and a reason from a person (AC-B09) - but a line an active decision
 * covers states the composition that was FROZEN for it, and a frozen Borrow is a source like
 * any other. Printing it as anything else would describe a decision nobody took.
 */
export type BoardSourceKind = 'reserve' | 'timely_spo' | 'buy' | 'borrow' | 'unplannable';

/** The rungs of the source ladder, in the order the engine walks them. */
export type BoardTrailKind = 'reserve_own' | 'reserve_pool' | 'incoming' | 'borrow' | 'buy';

/**
 * What happened at one rung.
 *
 *   took          the source gave something
 *   nothing_left  it was checked and had nothing to give
 *   not_eligible  a RULE skipped it (hot-selling protects dealer stock; no shared pool exists)
 *   offered       found, and deliberately not taken - Borrow needs a donor and a person's reason
 *   none_needed   the line was already covered before the ladder reached it
 */
export type BoardTrailOutcome =
  | 'took'
  | 'nothing_left'
  | 'not_eligible'
  | 'offered'
  | 'none_needed';

/**
 * One rung of the ladder, as it was walked for one line (the captain: "can you justify how you
 * arrive at the buy, like what's the process you have gone through ... need more justification",
 * and then "the justification needs to be STRUCTURED instead of plain text").
 *
 * EVERY rung arrives, including the ones that gave nothing: "the pool was checked and had none"
 * is the answer to that question, and a step the server omitted would read as a step nobody took.
 * A line that cannot be planned carries an empty trail, because no ladder was walked for it.
 */
export interface BoardTrailStep {
  /** 1-based, in the order the ladder walked. */
  step: number;
  kind: BoardTrailKind;
  /** The source's warehouse code. Null for Buy, which is held nowhere, and for Borrow. */
  location?: string | null;
  /** The same warehouse by id. Addressing only, never rendered. */
  warehouse_id?: string | null;
  /** What the source held when the ladder reached this line, before the demand ahead of it. */
  opening?: string | null;
  /** Own location only: what the queue in front of this line wants, and how long it is. */
  ahead_qty?: string | null;
  ahead_lines?: number | null;
  /**
   * WHO is in that queue: the top of it in rank order, how many more, and a count of the WHOLE
   * queue by the factor that put each line in front.
   *
   * The captain, reading `478 | 18730 across 142 lines | 0 | 0 | 21 | Nothing left`: "what does
   * this mean? why do the orders stand ahead of me? why?" Totals answer neither question.
   * Own-location rung only; every other rung sends an empty list, because no other rung queues.
   */
  ahead?: BoardAheadLine[];
  ahead_more?: number;
  ahead_by_factor?: Record<string, number>;
  /** What this source could give THIS line once its own rules were applied. */
  offered: string;
  /** What the line actually took. Always 0 for Borrow, which is offered and never proposed. */
  taken: string;
  /** Still uncovered after this step. Zero on the last one. */
  remaining_after: string;
  outcome: BoardTrailOutcome;
  /**
   * WHY it ended that way, in one plain sentence from the server. Never assembled here: the side
   * that walked the ladder is the side that knows, and a sentence written on the client would
   * eventually describe a rule the engine no longer applies.
   */
  why?: string | null;
  /** One short hint, never a paragraph: "hot-selling: pool only", "MWH-IB 12000 · BRW 9000". */
  note?: string | null;
}

/** One line standing in front of this one at its pile, and what put it there. */
export interface BoardAheadLine {
  so_number: string;
  line_no?: number | null;
  qty: string;
  required_date?: string | null;
  rank_score: number;
  /**
   * The policy factor with the largest weighted difference in that line's favour. `line_order`
   * or `tie_break` when the two scores are EQUAL: the policy separated nothing and the queue
   * was decided by the tie-break, so naming a factor would claim a difference that is not there.
   */
  leading_factor?: string | null;
  /** An earlier line of the SAME sales order, which is not a rival at all. */
  same_order?: boolean;
}

/** One donor of a FROZEN Borrow, as the confirmation takes it back. */
export interface BoardDecisionBorrow {
  source: BorrowSource;
  warehouse_id?: string | null;
  /** The donor's warehouse CODE, which is what the screen reads. */
  location?: string | null;
  donor_project_id?: string | null;
  qty: string;
  /** The PERSON's reason. The confirmation refuses a Borrow that carries none. */
  reason: string;
}

/**
 * What the ACTIVE revision froze for one line (13.4).
 *
 * The WHOLE composition rather than a summary of it, because the board POSTS it back: a second
 * confirmation on the same order covers the UNION of what was decided before and what is being
 * decided now, so every already-decided line has to be re-emitted from this. A board that sent
 * only its newly decided lines silently un-decided the earlier ones.
 */
export interface BoardLineDecision {
  revision_no: number;
  confirmed_at?: string | null;
  timely_spo_qty: string;
  /** Same shape as an amendment's Reserve: addressed by id, labelled by code. */
  reserve: BoardReserveComponent[];
  borrow: BoardDecisionBorrow[];
  buy_qty: string;
  /** Why the composition was not the engine's, in the planner's own words. */
  amend_reason?: string | null;
}

/**
 * One contributing sales-order line inside a cell: the row of the breakdown table the captain
 * asked for ("which sales order, which customer, which project, the quantity, where should it
 * be supplied from").
 */
export interface BoardContribution {
  /** Stable key for the draft. Addressing only, never rendered. */
  key: string;
  sales_order_id: string;
  /**
   * The CORE sales-order line id, which is how its pile queue is asked for. Addressing only,
   * never rendered. NOT `project_line_id`: that is the mirror and is null until the order is
   * adopted, while a line with no mirror still stands in the queue at its pile.
   */
  line_id?: string | null;
  /**
   * The product this line is for, for the drill-down only, never rendered. Two products on the
   * live book share the item code `B2155-NL-BLUE`, so a queue looked up by code would answer
   * confidently about the wrong pile.
   */
  product_id?: string | null;
  so_number: string;
  customer_name?: string | null;
  /**
   * The customer's own id, for GROUPING only - never rendered (no UUIDs in the UI).
   *
   * Two customers can share a name, and a board that merged them would show one row totalling
   * two companies' demand. Absent falls back to the name, which is the merge this exists to
   * prevent, so the fallback is a stated compromise rather than the design.
   */
  customer_id?: string | null;
  project_label?: string | null;
  /**
   * The project's normalised key, for grouping only, never rendered.
   *
   * A STRING rather than an id on purpose: an adopted order has no project registration, so the
   * project string on the order IS its identity. Grouping on the raw label instead would merge
   * two spellings of one project and split one project written two ways.
   */
  project_key?: string | null;
  line_no: number;
  item_code: string;
  /** The still-owed quantity. `qty_outstanding` is the same number under its own name. */
  qty: string;
  /**
   * What the sales order ORDERED on this line, as a fact off the server.
   *
   * Never derived here by adding delivered to owed: a number the client invented is a number
   * nobody can be held to, and the two would drift the first time a return or a cancellation
   * moved one of them. Absent renders as a stated absence, never as a guess.
   */
  qty_ordered?: string | null;
  /** The owed quantity under its own name. `qty` is kept as an alias of it. */
  qty_outstanding?: string | null;
  /** What has already been delivered against the line. Ordered - delivered = outstanding. */
  qty_delivered?: string | null;
  /**
   * The engine's own proposal, as numbers rather than as a sum over `sources`.
   *
   * Read, never re-derived. The board now proposes what the SHEET proposes - pool and borrow
   * are considered, not just own-location reserve then buy - so any client notion of "nothing
   * free here, therefore buy" would be a second, worse allocator disagreeing with the real one.
   */
  qty_proposed_reserve?: string | null;
  qty_proposed_incoming?: string | null;
  qty_proposed_buy?: string | null;
  /**
   * WHY the Reserve is the size it is, in the strip's vocabulary (PLAN 13.7, fair share).
   *
   * A line may reserve from its own location only what is left after the demand the active
   * policy ranks ahead of it there. `so_qty_ahead` is what those lines still want and
   * `lines_ahead` is how many they are - the active policy decides the order, required date is
   * the tie-break.
   */
  so_qty_ahead?: string | null;
  lines_ahead?: number | null;
  /**
   * What was LEFT AT THIS LINE'S OWN LOCATION when it was reached: on hand, less reserved, less
   * what confirmed decisions hold, less `so_qty_ahead`.
   *
   * THREE NUMBERS LIVE NEAR EACH OTHER AND NONE MAY BE PRINTED AS ANOTHER:
   *   - `BoardCellLocation.available_qty` is the WHOLE pile's position, signed, as AutoCount
   *     states it (on hand - all SO + all SPO). It is about the pile, not about any line;
   *   - this is what was left for THIS line at its own location;
   *   - `qty_proposed_reserve` is what the line actually TOOK, and it may EXCEED this one,
   *     because the shared pool is a second source with a queue of its own. A live card reads
   *     "0 left for this line" beside a Reserve of 9 drawn from the pool, and both are true.
   */
  available_to_this_line?: string | null;
  /** How much could be borrowed for this line, across the donors below. */
  qty_borrow_available?: string | null;
  borrow_candidates?: BoardBorrowCandidate[];
  /**
   * The mirror line the confirmation names. Addressing only, never rendered.
   *
   * A board row cannot be committed without it: `ConfirmLine.project_line_id` is what the
   * per-order confirm endpoint keys on.
   */
  project_line_id?: string | null;
  /** The line's REAL required date, not the bucket it landed in. */
  required_date?: string | null;
  /**
   * This LINE's own required date is before `as_of`.
   *
   * Not the same question as `BoardDateBucket.is_past`, and the difference is the whole reason
   * both exist: a line due yesterday is late even though the week it sits in has not ended, so
   * counting late lines off the bucket flag undercounts them.
   */
  is_past?: boolean;
  /** The core sales-order line's own warehouse code. Null means the source record is silent. */
  fulfilment_location?: string | null;
  /**
   * The same warehouse by id, for the confirm payload only. Never rendered.
   *
   * Needed on the LINE and not only on the sources: an amendment that reserves on a line the
   * engine proposed nothing for has no reserve source to read a warehouse off.
   */
  fulfilment_warehouse_id?: string | null;
  /** The line states no location, so it cannot be planned and blocks its order (AC-FP16). */
  unplannable: boolean;
  /** `sales_order_lines.priority`, when anybody stated one. Almost nobody does. */
  priority?: 'high' | 'medium' | 'low' | null;
  /**
   * Where this row came in the competition for the cell's stock, and why (13.5).
   *
   * `rank_score` is the reorder engine's own `SUM(w*v) / SUM(w present)` over the active
   * `scm.priority_policy`. The factors are carried with it because a ranking nobody can
   * inspect is a ranking nobody will trust: the planner has to be able to see that this order
   * won on need-by date and lost on document age.
   */
  rank_score: number;
  rank_factors: BoardRankFactor[];
  /** The default rule's proposal for this row, in the order the engine proposes them. */
  sources: BoardSource[];
  /**
   * HOW that proposal was arrived at: the ladder, rung by rung, in the order it was walked.
   *
   * The sources say what the answer is; this says what was checked to get there, including the
   * rungs that gave nothing. Empty for a line that cannot be planned at all.
   */
  trail?: BoardTrailStep[];
  /**
   * Free stock at this row's location ran out before this row was reached, so the default
   * rule gave it to an earlier-dated row and this one is bought instead (13.5). Named because
   * today the two orders would both silently propose the same stock and the second would only
   * be refused at confirmation.
   *
   * Always false on a covered row: a decided line is not competing for anything.
   */
  contested: boolean;
  /**
   * An ACTIVE decision on this line's sales order already covers it (13.4).
   *
   * The board went on proposing for such a line - "Buy 43" beside a decision that had borrowed
   * 10 and bought 33 - because it kept the line in its own demand while the pile's queue
   * rightly left it out. A covered row is not re-planned: `sources` and `qty_proposed_*` are
   * the FROZEN composition, the trail is empty (no ladder was walked), and the three share
   * fields are absent because it is not in the queue they count.
   */
  covered?: boolean;
  /** What was frozen, when the row is covered. Absent otherwise, never an empty object. */
  decision?: BoardLineDecision | null;
}

/**
 * One weighted factor behind a row's rank. `present: false` means the value was unknown and the
 * factor was dropped from BOTH sums, never scored as zero: an unknown is not a bad score, and
 * treating it as one is how a ranking starts lying.
 */
export interface BoardRankFactor {
  key: string;
  /** What the policy weights it at. Shown in the tooltip, never as a bare number beside the
   * normalised value: `demand_class 1.00 x0` reads to everybody as a weight of 1.00. */
  weight: number;
  value: number | null;
  /**
   * The absolute fact behind the normalised value, as text: "2026-09-03", "45 days",
   * "project". This is what a planner recognises; the normalised 0-to-1 number is an artefact
   * of the scoring and means nothing on its own, so the raw fact leads.
   */
  raw?: string | null;
  present: boolean;
}

/** The `scm.priority_policy` row a board was ranked by. Named on screen, never assumed. */
export interface BoardPolicy {
  name: string;
  factors: Record<string, number>;
  demand_class_weights: Record<string, number>;
  /**
   * True when this is a what-if the planner asked for rather than the row that is live.
   * A previewed ranking is labelled and cannot be committed against (13.5).
   */
  is_preview: boolean;
  /**
   * The SERVER's verdict that this policy separates none of these rows, so the ranking is flat.
   *
   * Read, never re-derived. The screen can see a weight of zero, but it cannot see a factor
   * that is weighted and CONSTANT - every row on this board is project-class, so `demand_class`
   * can carry weight 3.0 and still order nobody. Only the side that scored the rows knows that.
   */
  discriminates_nothing: boolean;
}

export interface BoardSource {
  kind: BoardSourceKind;
  qty: string;
  /** Warehouse code for a Reserve; null for Buy, which has no location by definition. */
  location?: string | null;
  /**
   * The same warehouse by id, for the confirm payload only. Never rendered (no UUIDs in the
   * UI): `ConfirmReserveComponent.warehouse_id` is what the endpoint takes, and the screen
   * names warehouses by code.
   */
  warehouse_id?: string | null;
  /** The sentence the rule wrote, shown beside the quantity. Never a bare code. */
  reason: string;
  /** SPO number when the source is incoming stock. */
  spo_number?: string | null;
  arrival_date?: string | null;
}

/** A donor the engine found for a line's Borrow. Named, never an id. */
export interface BoardBorrowCandidate {
  source: BorrowSource;
  warehouse_code: string;
  /**
   * Addressing only, never rendered. The board COMPOSES a Borrow now rather than only
   * mentioning that one is possible, and `ConfirmBorrowComponent` names the donor by id: a
   * warehouse code cannot be resolved into one here without guessing at an id.
   */
  warehouse_id?: string | null;
  donor_project_ref?: string | null;
  donor_project_id?: string | null;
  free_qty: string;
  /** The donor's own AutoCount position, and where the ranking put it (PLAN 13.11). */
  qty_on_hand?: string | null;
  so_qty?: string | null;
  spo_qty?: string | null;
  available_qty?: string | null;
  qty_free?: string | null;
  qty_committed?: string | null;
  /** This line's residual at the borrow rung, and what the donor keeps once it is met. */
  need_qty?: string | null;
  available_after_need?: string | null;
  recommended?: boolean;
  /** What taking it costs whoever holds it (AC-B09). Shown while the borrow is chosen. */
  donor_impact?: BorrowDonorImpact;
}

/** One incoming purchase leg at a location, with the document that carries it. */
export interface BoardIncomingLeg {
  spo_number: string;
  arrival_date?: string | null;
  qty: string;
}

/**
 * What one cell owes at ONE location, and what is actually there - the captain's "where will I
 * need to source to fulfil", answered with facts rather than with a proposal.
 *
 * EVERY STOCK FIGURE IS NULL, NEVER ZERO, when the sales order states no location. Rendering a
 * null as "0" would tell the planner there is nothing in stock when the truth is that nobody
 * said where to look, and those are opposite instructions.
 */
export interface BoardCellLocation {
  location: string | null;
  /**
   * The product and warehouse this position is about, for the drill-down only, never rendered.
   *
   * Two products on the live book share the item code `B2155-NL-BLUE`, so resolving a stock
   * position from the code would answer about the wrong one.
   */
  product_id?: string | null;
  warehouse_id?: string | null;
  /** AutoCount's own four, in AutoCount's own words. `available_qty` is SIGNED. */
  so_qty?: string | null;
  spo_qty?: string | null;
  available_qty?: string | null;
  /** What is owed here. `qty` is kept as an alias of it. */
  qty: string;
  qty_demand?: string | null;
  qty_on_hand?: string | null;
  qty_reserved?: string | null;
  qty_free?: string | null;
  /** Free stock left AFTER this board's own proposals have drawn it down. */
  qty_free_remaining?: string | null;
  /**
   * What confirmed decisions are already holding here. On hand, less reserved, less this, IS
   * `qty_free` - the third term of that arithmetic, so the sum can close on screen.
   */
  qty_held_by_decisions?: string | null;
  /** What the WHOLE BOOK still owes here, not merely the orders on this board. */
  qty_owed_all_orders?: string | null;
  /** Of that, the part a confirmed decision already covers. */
  qty_owed_confirmed?: string | null;
  qty_incoming?: string | null;
  incoming?: BoardIncomingLeg[];
  qty_proposed_reserve?: string | null;
  qty_proposed_incoming?: string | null;
  qty_proposed_buy?: string | null;
}

/** One cell: this row, by this bucket, across every selected order. */
export interface BoardCell {
  /**
   * What the cell is LABELLED by. The item code on the product axis, and the sales-order
   * number, customer name or project label on the pivoted ones - so the dialog title reads the
   * same way whichever axis produced the cell.
   */
  item_code: string;
  /**
   * What the cell is KEYED by, when that is not its label. Client-side only, set when the board
   * is pivoted: two customers can share a name, so the label cannot be the key.
   */
  row_key?: string;
  bucket_key: string;
  /** Summed across every contributing line, including the unplannable ones (13.7). */
  total_qty: string;
  /** One entry per distinct source location; more than one is normal, not exotic. */
  locations: BoardCellLocation[];
  contributions: BoardContribution[];
  /** Contributions whose sales order states no location for them. */
  unplannable_count: number;
  /** Contributions the default allocation rule could not cover from free stock. */
  contested_count: number;
  /**
   * Contributions whose own required date is already past. Sent so the summary can be counted
   * without walking every contribution of every cell.
   */
  past_count?: number;
  /** How many DIFFERENT sales orders contribute here. One means an order competing with itself. */
  distinct_order_count?: number;
  /** Whether the ranking actually put these rows in an order, or they all scored alike. */
  rank_separates?: boolean;
}

export interface BoardProductRow {
  item_code: string;
  description?: string | null;
}

/**
 * What the board's VERTICAL axis is (the captain: "how about if we want vertical is sales
 * order, is customer, is project").
 *
 * The horizontal axis is always dates. The pivot is a different grouping of the SAME
 * contributions into cells - no second fetch, and no second idea of what a line is.
 */
export type BoardRowAxis = 'product' | 'sales_order' | 'customer' | 'project';

/**
 * One row of the board, whichever axis is chosen.
 *
 * `key` is an id wherever an id exists and is never rendered; `label` is what the reader sees.
 * Keeping them apart is the whole reason two customers with one name stay two rows.
 */
export interface BoardAxisRow {
  key: string;
  label: string;
  /** Secondary text for the row header, e.g. a product's name under its code. */
  description?: string | null;
}

/** One selected order's standing, which is what makes the partial-decision reality visible. */
export interface BoardOrderStanding {
  sales_order_id: string;
  so_number: string;
  /**
   * The PLANNING RECORD's id, which is what `POST .../sales-orders/{pso_id}/confirm` takes.
   * Addressing only, never rendered. An order that has not been adopted has none, and the
   * board says so instead of offering a Confirm that cannot post.
   */
  project_sales_order_id?: string | null;
  customer_name?: string | null;
  /** Lines of this order inside the SELECTION - never only the ones a window is showing. */
  line_count: number;
  /** How many of those lines carry a verdict in the draft. The client's, never the server's. */
  decided_count: number;
  /**
   * Of those, how many would actually be POSTED by a Confirm - approved and amended, never
   * rejected. A rejected line is a decision to leave it undecided, so a button counting it
   * would promise to commit something the body deliberately omits.
   */
  committing_count?: number;
  /** Lines that can never be decided here because their sales order states no location. */
  unplannable_count: number;
}

/**
 * What one order is about to commit, and what it is deliberately leaving behind.
 *
 * Confirm is NOT gated on completeness (13.4, captain's decision): a planner commits the lines
 * they are sure about precisely so the undecided ones keep flowing to reorder planning. So the
 * screen owes them a plain statement of what is being left, rather than a disabled button.
 */
export interface BoardCommitPreview {
  /** Lines carrying a verdict that would be written by this confirmation. */
  committing: number;
  /** Lines with no verdict, which stay outstanding and keep counting as demand. */
  leaving_undecided: number;
  /** Of those, the ones that could never be decided here (no location on the sales order). */
  blocked: number;
}

/**
 * `GET /project-sales/fulfilment-planning/board`. A pure read: opening it claims nothing.
 *
 * The four `*_count` totals are SELECTION-scoped: counted over every contributing line before
 * any window is applied, so they are identical on day, week and month and do not move when the
 * day window is scrolled somewhere empty. Anything summed off `cells` is window-scoped and
 * answers a different question - see `line_count`.
 */
export interface PlanningBoard {
  granularity: BoardGranularity;
  /** Which policy produced the ranking on show. Always stated (13.5). */
  policy: BoardPolicy;
  /** The date the board was built against, so `is_past` is reproducible in a test. */
  as_of: string;
  /**
   * Every contributing line in the selection, windowed or not. The denominator of every
   * headline number on this screen: summing `cells[].contributions.length` instead counts what
   * a window happens to be showing, which is how "160 of 160" became "1 of 2" on a day view.
   */
  line_count: number;
  /** Of those, the lines whose own required date is past. The banner's numerator. */
  past_line_count: number;
  /** Of those, the lines whose sales order states no fulfilment location (AC-FP16). */
  unplannable_line_count: number;
  /** Of those, the lines the allocation rule could not cover from free stock (13.5). */
  contested_line_count: number;
  dateBuckets: BoardDateBucket[];
  productRows: BoardProductRow[];
  cells: BoardCell[];
  /**
   * One standing per selected order, built from ALL its rows rather than the displayed ones.
   * `decided_count` is always 0 here (deviation 4) and is overlaid from the client draft.
   */
  orders: BoardOrderStanding[];
}

/** What CS did to one contributing row. The board's working draft, persisted nowhere yet. */
export type BoardVerdict = 'approved' | 'amended' | 'rejected';

/** One warehouse's share of an amended Reserve. Addressed by id, labelled by code. */
export interface BoardReserveComponent {
  warehouse_id: string;
  /** The warehouse CODE, for the pill and the editor. Never the id. */
  location?: string | null;
  qty: string;
}

/** One donor an amendment borrows from. The confirm body's borrow component, plus its code. */
export interface BoardBorrowComponent {
  source: BorrowSource;
  warehouse_id: string;
  warehouse_code?: string | null;
  donor_project_ref?: string | null;
  donor_project_id?: string | null;
  qty: string;
  /** Mandatory: no Borrow is written without one (AC-B09). */
  reason: string;
}

export interface BoardDecision {
  verdict: BoardVerdict;
  /**
   * The whole Reserve as one number.
   *
   * Kept beside the components below because it is what a decision taken before the board
   * could compose one carries, and what the pill falls back to. The components are the
   * decision; this is a summary of them.
   */
  reserve_qty?: string;
  /**
   * The composition the planner typed, in full: the SAME four kinds the per-order sheet
   * composes, so an amendment made on the board and one made on the sheet reach the
   * confirmation as the same body.
   *
   * Present on an amend made in the editor. Absent on an approval (the proposal stands, and
   * the confirmation reads the server's own numbers) and on a rejection (nothing is posted).
   */
  reserve?: BoardReserveComponent[];
  borrow?: BoardBorrowComponent[];
  buy_qty?: string;
  /** The server's incoming cover, carried through unedited: it is dated supply, not a choice. */
  timely_spo_qty?: string;
  /**
   * Mandatory on an amend that displaces the default priority rule, and on a reject. Same
   * shape as the Borrow reason the per-line card already demands (AC-B09): a decision a
   * person made by hand has to say why, or the snapshot cannot explain itself later.
   */
  reason?: string;
}

/** Keyed by `BoardContribution.key`. Client-side in Phase 1 (13.4). */
export type BoardDraft = Record<string, BoardDecision>;


// ---------------------------------------------------------------------------
// Stock Status with Detail: what the figures on a location ROW of the cell's stock table are
// made of, expanded under that row.
//
// AutoCount shows this as a document list under the position, and the captain reads it there.
// The FE mirrors that: a header line that is the arithmetic, then the documents that produce
// it, then a total that adds back up to the header.
// ---------------------------------------------------------------------------

/** One sales order standing behind the SO quantity. */
export interface StockDetailSalesOrder {
  sales_order_id: string;
  so_number: string;
  customer_name?: string | null;
  customer_id?: string | null;
  project_label?: string | null;
  demand_class?: string | null;
  doc_date?: string | null;
  delivery_date?: string | null;
  so_qty: string;
  /** Already covered by a confirmed decision, so it is not competing for this stock. */
  is_covered?: boolean;
}

/** One purchase order standing behind the SPO quantity. */
export interface StockDetailIncoming {
  spo_number: string;
  supplier_name?: string | null;
  expected_date?: string | null;
  spo_qty: string;
}

/**
 * `GET /project-sales/fulfilment-planning/stock-detail?product_id=&warehouse_id=`.
 *
 * The field names are the SERVER's, checked against `app/schemas/project_board.py`. This type
 * used to declare a `warehouse_code` the backend never sends and to omit three fields it always
 * sends, so a reader of the type learnt the wrong shape and a renderer of `warehouse_code` would
 * have printed nothing for ever without a type error.
 */
export interface StockDetail {
  product_id: string;
  item_code: string;
  description?: string | null;
  warehouse_id: string;
  /** The warehouse CODE, which is what the screen shows. Named `location` by the server. */
  location: string;
  qty_on_hand: string;
  so_qty: string;
  spo_qty: string;
  /** SIGNED: on hand - SO + SPO. Negative is the shortfall and is shown as it arrives. */
  available_qty: string;
  qty_reserved: string;
  /** What confirmed decisions hold here. On hand, less reserved, less this, IS `qty_free`. */
  qty_held_by_decisions: string;
  qty_free: string;
  sales_orders: StockDetailSalesOrder[];
  incoming: StockDetailIncoming[];
}

/**
 * One line of the queue at a pile: `GET /project-sales/fulfilment-planning/queue`.
 *
 * The captain, having been shown the top three beside the rung: "I need to know what is ahead of
 * me to have the visibility, and why they are ahead of me, meaning I need to know their rank
 * also."
 */
export interface PileQueueLine {
  /** 1-based, in the order the stock is served. */
  position: number;
  /** The CORE sales-order line. Addressing only. */
  line_id: string;
  /** Its sales order, so the row can link to it. Addressing only, never rendered. */
  sales_order_id?: string | null;
  so_number: string;
  /** Null until the order has been adopted: an un-mirrored line has no line number. */
  line_no?: number | null;
  customer_name?: string | null;
  qty: string;
  required_date?: string | null;
  order_date?: string | null;
  payment_terms_days?: number | null;
  demand_class?: string | null;
  rank_score: number;
  /** The same per-factor breakdown a board row carries, so one popover explains both. */
  rank_factors: BoardRankFactor[];
  /** Which factor puts this line in front of the one that asked. Null for that line itself. */
  leading_factor?: string | null;
  /** What the queue has claimed by the time it has served this row, this row included. */
  cumulative_ahead_qty: string;
  is_this_line: boolean;
  /** Always false on a row that is here: a covered line is EXCLUDED from the queue. */
  is_covered_excluded: boolean;
}

/** The whole queue at one pile, in the order the stock is actually served. */
export interface PileQueue {
  product_id: string;
  item_code: string;
  description?: string | null;
  warehouse_id: string;
  /** The warehouse CODE, which is what the screen shows. */
  location: string;
  /** What the pile held before the queue drew on it: the trail's own opening figure. */
  qty_free_opening: string;
  /** Where the asked-about line stands. Null when no line was named. */
  this_line_position?: number | null;
  /** The rule that produced this order, named. Always the LIVE policy. */
  policy_name: string;
  lines: PileQueueLine[];
}
