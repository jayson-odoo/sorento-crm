/**
 * SCM S4 - PO creation worklist types (UAC Group E2, plus AC-C2 and AC-C7).
 *
 * **Joey executes, she does not decide.** Mr Loo has already chosen a quantity and a
 * supplier on the Summary Order Report, so this screen is a worklist over those
 * decisions - never a second decision point. Nothing here offers Accept or Reject.
 * What it adds is what somebody keying a purchase order needs and the report does
 * not carry: when the stock is needed, when the order therefore has to be placed,
 * whether that date has already passed, and whether the PO has been keyed into
 * AutoCount yet.
 *
 * Three rules are baked into the shapes below.
 *
 *   - **No ids.** Product code, supplier code, a human name. `run_id` is the one
 *     opaque value and it is never rendered.
 *   - **A decision to buy NOTHING is a row** (AC-E2.5). A chosen quantity of zero is
 *     the "use the pool" answer, and it appears saying no PO is needed rather than
 *     being filtered out, so the worklist reconciles one-for-one against the
 *     decisions. A missing row is indistinguishable from a decision nobody made.
 *   - **A missing date is named, never filled in.** `need_by` comes from the frozen
 *     dated shortfall, and a product with no uncovered committed order genuinely has
 *     no need-by date - which is most of the book today. Sending today's date, or the
 *     place-by date computed from a guess, would manufacture urgency. Null, and the
 *     screen says so.
 */

/**
 * Whether the purchase order has been keyed into AutoCount (AC-E2.2).
 *
 * Manual, because no integration exists and nothing can detect it: the person doing
 * the keying sets it. Three values is the stated minimum, and `keying` is what stops
 * two people keying the same PO.
 */
export type KeyedStatus = 'not_keyed' | 'keying' | 'keyed';

export const KEYED_STATUS_LABELS: Record<KeyedStatus, string> = {
  not_keyed: 'Not keyed',
  keying: 'Keying',
  keyed: 'Keyed',
};

/** One decided product, ready to be keyed. */
export interface PoWorklistRow {
  product_code: string;
  product_name: string | null;
  uom: string | null;

  /** What Mr Loo decided (AC-E2.1). Zero means use the pool: no PO is needed. */
  chosen_qty: number;
  /** The engine's figure, kept beside the decision so a difference stays visible. */
  suggested_qty: number;
  /** Null only on a use-pool row, which needs no supplier. */
  chosen_supplier_code: string | null;
  chosen_supplier_name: string | null;
  /** Human name of whoever decided, never a user id. */
  decided_by: string;
  /** Naive Malaysia wall-clock ISO timestamp of the decision. */
  decided_at: string;

  /**
   * ISO date the stock is first short (AC-C1), off the frozen report row. Null when
   * nothing committed is uncovered, which is most of the book: the buy is a policy
   * replenishment rather than a response to an order that will otherwise miss.
   */
  need_by: string | null;
  /**
   * `need_by` minus the resolved lead time (AC-C2). Null whenever `need_by` is null
   * OR the lead time is unknown - a place-by date derived from a guessed lead time is
   * worse than none, because it is acted on.
   */
  place_by: string | null;
  /** Lead time the place-by date was derived from, so the arithmetic can be checked. */
  lead_time_days: number | null;
  /**
   * True when `place_by` is already in the past (AC-C2). Flagged rather than silently
   * recommended: an order that had to be placed three weeks ago is a different job
   * from one due next month.
   */
  is_late: boolean;

  /** Last purchase cost for this item and supplier, ex-works (AC-C7). */
  last_po_cost: number | null;
  last_po_currency: string | null;
  /** Chosen quantity times the last cost, in `last_po_currency`. Null if either is. */
  cash_committed: number | null;

  keyed_status: KeyedStatus;
  /** Human name of whoever last set the keyed status. Null while never set. */
  keyed_by: string | null;
  keyed_at: string | null;
}

/** The worklist for one run. */
export interface PoWorklist {
  /** Opaque run key. Never rendered. */
  run_id: string;
  /** ISO date the decisions were frozen against. Null when the run froze no rows. */
  as_of: string | null;
  rows: PoWorklistRow[];
}

/** What setting the keyed status writes. */
export interface KeyedStatusInput {
  run_id: string;
  keyed_status: KeyedStatus;
}

/** What the server echoes back, so the row updates without a refetch. */
export interface KeyedStatusResult {
  product_code: string;
  keyed_status: KeyedStatus;
  keyed_by: string;
  keyed_at: string;
}
