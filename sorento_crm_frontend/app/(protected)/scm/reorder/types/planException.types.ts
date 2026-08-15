/**
 * SCM S5 - Plan Exceptions (UAC Group D).
 *
 * **An exception is a disagreement between the plan and supply already placed.** The
 * demand book is re-uploaded, the affected products are recomputed, and the new dated
 * position is diffed against POs that are already out with a supplier. Most deltas
 * change nothing anyone must act on; the few that contradict a placed order become
 * these rows (AC-D2b). That reduction IS the screen - a delta count of 400 producing 6
 * exceptions is the system doing its job, not a thin result.
 *
 * Four shapes are load-bearing.
 *
 *   - **Before and after, side by side** (AC-D4). An exception that states only the new
 *     position asks the reviewer to remember the old one. Both timelines travel with the
 *     row.
 *   - **The reading, with its sources** (AC-D9, AC-D12). Every exception carries the
 *     item's lifecycle, velocity, business class and last purchase date, each naming the
 *     field it came from, so somebody can disagree with the REASONING and not only the
 *     outcome. None of it is newly computed: all four already exist.
 *   - **Actions ordered by that reading, not by quantity** (AC-D10). The same arithmetic
 *     on a discontinued C/Z retail item proposes keeping the PO and pooling the stock
 *     FIRST, where an active A/X project item proposes reallocating. A discontinued
 *     surplus is never first-proposed for cancellation or ETA deferral, because that
 *     stock is the last obtainable (AC-D11).
 *   - **Nothing is amended without approval** (AC-D6). Approving a reallocation writes
 *     an allocation decision; it does not amend the purchase order (AC-D7).
 *
 * No ids surface. Product code, warehouse code, a human name; `run_id` and
 * `exception_id` are opaque and never rendered.
 */

/**
 * What the plan and the placed supply disagree about (AC-D3).
 *
 * Four types is the stated minimum and each names a DIFFERENT remedy, which is why the
 * type is stored rather than derived from the sign of a number: a shortfall that moved
 * earlier and supply that is permanently surplus are both "the dates no longer line up"
 * arithmetically, and nothing sensible can be proposed without knowing which.
 */
export type PlanExceptionType =
  | 'shortfall_earlier'
  | 'supply_early'
  | 'supply_surplus'
  | 'supply_wrong_location';

export const EXCEPTION_TYPE_LABELS: Record<PlanExceptionType, string> = {
  shortfall_earlier: 'Short sooner than planned',
  supply_early: 'Supply arrives before it is needed',
  supply_surplus: 'Supply no longer needed',
  supply_wrong_location: 'Supply going to the wrong place',
};

/**
 * What a reviewer may do about it (AC-D11a).
 *
 * `release_to_pool` is the flow's "deallocate back to BRW" and is a location change, not
 * a cancellation. `split` exists because a partial change was unrepresentable before and
 * is the most common real shape (AC-D11b).
 */
export type PlanExceptionActionCode =
  | 'relink_so'
  | 'change_location'
  | 'release_to_pool'
  | 'split'
  | 'push_eta'
  | 'keep_and_pool'
  | 'accept';

export const ACTION_LABELS: Record<PlanExceptionActionCode, string> = {
  relink_so: 'Move to another order',
  change_location: 'Send to a different location',
  release_to_pool: 'Release into the shared pool',
  split: 'Split the line',
  push_eta: 'Push the arrival date out',
  keep_and_pool: 'Keep the order and pool the stock',
  accept: 'Accept as is',
};

/** One signal in the item's reading, carrying the field it was read from (AC-D12). */
export interface ReadingSignal {
  /** Rendered value, already human-readable ("Discontinued", "A / X", "Project"). */
  value: string | null;
  /** The field it came from, shown so the reasoning can be checked, e.g. `products.is_discontinued`. */
  source: string;
}

/**
 * The four signals that order the proposed actions (AC-D9).
 *
 * All four are read from data that already exists. A null `value` means the item carries
 * no such signal - an item never purchased has no last PO date - and is displayed as
 * unknown rather than defaulted, because defaulting it would silently change the order
 * of the actions below.
 */
export interface ItemReading {
  lifecycle: ReadingSignal;
  velocity: ReadingSignal;
  business: ReadingSignal;
  last_po: ReadingSignal;
}

/** One dated point on either timeline. */
export interface TimelinePoint {
  /** ISO date. */
  date: string;
  /** Net position on that date. */
  net: number;
  /** What moved on that date, e.g. "PO 12345 arrives" or "SO 998 due". */
  label: string | null;
}

/**
 * The same product's position before and after the restatement (AC-D4).
 *
 * `shortfall_at` is the peak-deficit date, not the first gap, so it matches the figure
 * the buy plan is built from. Null on either side means no uncovered committed demand,
 * which is a legitimate answer and reads as "none" rather than as a missing value.
 */
export interface BeforeAfterTimeline {
  before_points: TimelinePoint[];
  after_points: TimelinePoint[];
  before_shortfall_at: string | null;
  after_shortfall_at: string | null;
  before_shortfall_qty: number | null;
  after_shortfall_qty: number | null;
}

/**
 * One proposed action, ranked by the reading (AC-D10).
 *
 * `rank` 1 is what the engine proposes first. `rationale` states WHY it is first in the
 * reading's terms ("last obtainable stock of a discontinued item"), so the ordering is
 * arguable rather than magic.
 */
export interface ProposedAction {
  code: PlanExceptionActionCode;
  rank: number;
  rationale: string;
  /**
   * Where a reallocation is possible, the order it would move to and that order's
   * need-by date (AC-D5). Null on actions that move nothing.
   */
  candidate_so_number: string | null;
  candidate_need_by: string | null;
  /** Destination for a location change. Null on actions that move nothing. */
  candidate_warehouse_code: string | null;
}

export type PlanExceptionStatus = 'open' | 'approved' | 'rejected';

export const EXCEPTION_STATUS_LABELS: Record<PlanExceptionStatus, string> = {
  open: 'Open',
  approved: 'Approved',
  rejected: 'Rejected',
};

/** One exception: what disagrees, by how much, and what may be done about it. */
export interface PlanException {
  /** Opaque. Never rendered. */
  exception_id: string;
  exception_type: PlanExceptionType;

  product_code: string;
  product_name: string | null;
  uom: string | null;
  /** Where the placed supply is going. Null when the supply names no location. */
  warehouse_code: string | null;
  /** The fulfilment pool the recompute ran over, since netting is pooled, not per-warehouse. */
  pool_code: string | null;

  /** The placed supply this exception is about. Human PO number, never an id. */
  po_number: string | null;
  po_expected_date: string | null;
  /** Quantity in disagreement, in `uom`. Always positive; the TYPE carries the direction. */
  quantity: number;

  timeline: BeforeAfterTimeline;
  reading: ItemReading;
  /** At least one, ordered by rank ascending (AC-D5). */
  actions: ProposedAction[];

  status: PlanExceptionStatus;
  /** Human name, never a user id. Null while open. */
  decided_by: string | null;
  decided_at: string | null;
  /** Which action was approved. Null while open or when rejected. */
  decided_action: PlanExceptionActionCode | null;
  /** Required on reject (AC-D6), optional on approve. */
  decision_reason: string | null;
}

/**
 * Delta counts from the upload that produced this batch, kept beside the exception count
 * so the two reconcile on the screen (AC-D2b).
 */
export interface ExceptionBatchCounts {
  /** Lines the restatement changed. */
  delta_count: number;
  /** Of those, the ones that disagree with placed supply. */
  exception_count: number;
  open_count: number;
  approved_count: number;
  rejected_count: number;
}

/** Every exception produced by one run's batch. */
export interface PlanExceptionReport {
  /** Opaque run key. Never rendered. */
  run_id: string;
  /** ISO date the batch was diffed against. Null when the run produced no batch. */
  as_of: string | null;
  /** Naive Malaysia wall-clock ISO timestamp the batch was generated. */
  generated_at: string | null;
  /**
   * When the demand book was last uploaded. The plan is only as current as this, and the
   * journey is explicit that it belongs ON the screen rather than in a footnote.
   */
  last_upload_at: string | null;
  counts: ExceptionBatchCounts;
  rows: PlanException[];
}

/** What approving or rejecting an exception writes (AC-D6). */
export interface PlanExceptionDecisionInput {
  exception_id: string;
  status: Exclude<PlanExceptionStatus, 'open'>;
  /** Required when approving: which of the proposed actions was taken. */
  action_code: PlanExceptionActionCode | null;
  /** Required when rejecting. */
  reason: string | null;
  /** Split only: the part that moves. Must be less than the exception's quantity (AC-D11b). */
  split_qty: number | null;
}

/** What the server echoes back so the row updates without a refetch. */
export interface PlanExceptionDecisionResult {
  exception_id: string;
  status: PlanExceptionStatus;
  decided_by: string;
  decided_at: string;
  decided_action: PlanExceptionActionCode | null;
  decision_reason: string | null;
}
