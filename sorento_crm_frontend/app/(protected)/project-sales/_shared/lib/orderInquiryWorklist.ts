/**
 * Reading a row on purchasing's cross-project order inquiry.
 *
 * Pure, and deliberately outside the grid: where a row LINKS is the thing that decides
 * whether the screen is usable at all (an adopted order has no project, so the project
 * route cannot reach it), and the month vocabulary has to match the tab names on the
 * spreadsheet purchasing already works from. Both are worth asserting without mounting a
 * table.
 */
import type {
  OrderInquiryLink,
  OrderInquiryWorklistRow,
} from '../types/orderInquiry.types';

/**
 * The sheet's own spelling of a month, not the browser's: their tabs read `JAN 26`,
 * `JUNE 26`, `JULY 26`, `SEPT 26`. The backend labels every month it returns, so this is
 * only the fallback for a month the summary did not name.
 */
const MONTH_WORD = [
  'JAN',
  'FEB',
  'MAR',
  'APR',
  'MAY',
  'JUNE',
  'JULY',
  'AUG',
  'SEPT',
  'OCT',
  'NOV',
  'DEC',
];

/** `2026-01` to `JAN 26`. Anything that is not a month answers null rather than guessing. */
export function deliveryMonthLabel(month?: string | null): string | null {
  if (!month) return null;
  const match = /^(\d{4})-(\d{2})$/.exec(month.trim());
  if (!match) return null;
  const index = Number(match[2]) - 1;
  if (index < 0 || index > 11) return null;
  return `${MONTH_WORD[index]} ${match[1].slice(2)}`;
}

/**
 * Where the row's sales-order column links to.
 *
 * The CORE sales order wins whenever the row can reach both, for the same reason it does
 * on the planning worklist: it is the document the number on screen belongs to, and the
 * project mirror is a mirror of it rather than a second subject. An adopted row has no
 * project at all, so the project route could never reach it. A row with neither renders
 * as plain text - a link that answers 404 is worse than no link.
 */
export function orderInquiryRowHref(row: OrderInquiryWorklistRow): string | null {
  if (row.core_sales_order_id) return `/scm/sales-orders/${row.core_sales_order_id}`;
  if (row.project_id && row.project_sales_order_id) {
    return `/project-sales/${row.project_id}/sales-orders/${row.project_sales_order_id}`;
  }
  return null;
}

/**
 * S6 (`PLAN-board-oi-mechanical-22sep.md`, AC-B6-1): the "SO line" column's own text -
 * `SO402757 · L5` when the row carries a line number, the bare SO number otherwise (a
 * row with no line to name still deserves its SO number rather than a blank cell). `line_no`
 * is the field the backend has not sent yet (documented at the top of
 * `services/orderInquiryService.ts`, S6 BE half); absent today on every row.
 */
export function orderInquirySoLineLabel(
  row: Pick<OrderInquiryWorklistRow, 'so_number' | 'line_no'>,
): string {
  const so = row.so_number ?? 'Not numbered';
  return row.line_no ? `${so} · L${row.line_no}` : so;
}

/**
 * S6 (AC-B6-1): the "SO line" column's own href, landing on the exact line
 * (`?tab=lines&line=<core_line_id>`). `null` when either id the link needs is missing -
 * `core_sales_order_id` (already on the row) or `core_line_id` (the field the backend has
 * not sent yet) - so the cell falls back to plain text rather than a link that lands
 * nowhere in particular, the same rule `orderInquiryRowHref` already follows.
 */
export function orderInquirySoLineHref(
  row: Pick<OrderInquiryWorklistRow, 'core_sales_order_id' | 'core_line_id'>,
): string | null {
  if (!row.core_sales_order_id || !row.core_line_id) return null;
  return `/scm/sales-orders/${row.core_sales_order_id}?tab=lines&line=${row.core_line_id}`;
}

/** A quantity as a person reads it: `600`, never `600.0000`. */
export function formatInquiryQty(qty?: string | null): string {
  if (qty === null || qty === undefined) return '';
  const text = String(qty).trim();
  if (text === '') return '';
  if (!/^-?\d+(\.\d+)?$/.test(text)) return text;
  return text.includes('.') ? text.replace(/\.?0+$/, '') : text;
}

/**
 * Why "Taken from PO" / "Remaining" should NOT print a figure for this row's own verb
 * (the captain, 21 Aug: an ADVANCE row read "Taken from PO 432 / Remaining 0" - both real
 * `ORDER`-sibling totals on the same SO line, correctly summed, but sitting beside an
 * unactioned date change they read as "fully handled"). Both aggregates are scoped to
 * `verb = 'ORDER'` siblings only
 * (`OrderInquiryWorklistService._quantity_flow_by_so_line`), so any other verb's row is
 * shown what that scoping actually means for it, rather than a number that looks like an
 * answer about ITSELF. `null` for an `ORDER` row - it IS what the aggregate is about, so
 * the figure stands.
 */
const NON_ORDER_FLOW_LABEL: Record<string, string> = {
  ADVANCE: 'Date change',
  DELAY: 'Date change',
  CHANGE_SO: 'SO changed',
  CANCEL_BALANCE: 'Balance cancelled',
  PRE_ORDERED_DO_NOT_ORDER: 'Pre-ordered',
  ALREADY_INBOUND: 'Already inbound',
  RELEASE: 'Released',
};

/**
 * The verbs the two aggregates ARE about. `ORDER_BACK` joined `ORDER` when section 3.I
 * made it linkable and `scm.committed_v` started netting it the same way: it is demand
 * until it is linked, so a figure about "what still flows to reorder planning" that left
 * it out would be a different number from the one the plan reads.
 */
const FLOW_VERBS = ['ORDER', 'ORDER_BACK'];

export function flowExclusionLabel(verb: string): string | null {
  if (FLOW_VERBS.includes(verb)) return null;
  return NON_ORDER_FLOW_LABEL[verb] ?? 'Not an ORDER row';
}

/**
 * S3 (`PLAN-board-oi-mechanical-22sep.md`, AC-B3-1..7): the verbs Taken / Remaining are
 * ever a real figure for - a BUY row, one that can carry a link of its own. Deliberately a
 * different list from `FLOW_VERBS` above: that pair is scoped to `ORDER` siblings on the
 * same SO LINE (a different question, kept as-is), while Taken/Remaining read THIS row's
 * own `linked_qty` and so include `RESERVE_AND_ORDER` too - it still buys and still links.
 */
const TAKEN_REMAINING_VERBS = ['ORDER', 'ORDER_BACK', 'RESERVE_AND_ORDER'];

export function isInquiryBuyRow(verb: string): boolean {
  return TAKEN_REMAINING_VERBS.includes(verb);
}

/**
 * Taken: this row's own links, summed - `linked_qty` already IS that sum (the REAL links
 * only, never the synthetic "via PO" entries, per `OrderInquiryRow.linked_qty`'s own doc
 * comment). `-` on a notice row (AC-B3-3): an ADVANCE/DELAY/CHANGE_SO/... row never carries
 * a link of its own, and a `0` there would read as "nothing was taken" rather than "this
 * question does not apply to this row".
 */
export function inquiryRowTaken(
  row: Pick<OrderInquiryWorklistRow, 'verb' | 'linked_qty'>,
): string {
  if (!isInquiryBuyRow(row.verb)) return '-';
  return formatInquiryQty(row.linked_qty ?? '0');
}

/**
 * Remaining: Qty minus Taken minus bundled, never negative (AC-B3-2). `-` on a notice row
 * (AC-B3-3, same reason as Taken above); `0` on a row itself `cancelled` or whose sales-
 * order LINE is cancelled (AC-B3-4, `line_cancelled`) - that quantity is called off, not
 * still owed.
 */
export function inquiryRowRemaining(
  row: Pick<
    OrderInquiryWorklistRow,
    'verb' | 'qty' | 'linked_qty' | 'bundled_qty' | 'state' | 'line_cancelled'
  >,
): string {
  if (!isInquiryBuyRow(row.verb)) return '-';
  if (row.state === 'cancelled' || row.line_cancelled) return '0';
  const remaining =
    Number(row.qty ?? '0') - Number(row.linked_qty ?? '0') - Number(row.bundled_qty ?? '0');
  return formatInquiryQty(String(Math.max(remaining, 0)));
}

/**
 * Whether this row counts toward a Qty / Taken / Remaining FOOTER sum (AC-B3-4, AC-B3-5): a
 * buy row, neither cancelled itself nor on a cancelled sales-order line. Named once so the
 * footer and `inquiryRowRemaining`'s own `0` can never disagree about which rows are in it.
 */
export function inquiryRowCountsForFooter(
  row: Pick<OrderInquiryWorklistRow, 'verb' | 'state' | 'line_cancelled'>,
): boolean {
  return isInquiryBuyRow(row.verb) && row.state !== 'cancelled' && !row.line_cancelled;
}

/**
 * The three footer sums over the rows Taken/Remaining actually apply to (AC-B3-5): Qty and
 * Taken are each a plain sum, and Remaining is the FOOTER's own subtraction - Qty footer
 * minus Taken footer minus the bundled total - rather than a sum of each row's own already-
 * clamped Remaining, which is the exact wording the UAC states it by.
 */
export function inquiryFooterTotals(
  rows: Pick<
    OrderInquiryWorklistRow,
    'verb' | 'state' | 'line_cancelled' | 'qty' | 'linked_qty' | 'bundled_qty'
  >[],
): { qty: number; taken: number; remaining: number } {
  const counted = rows.filter(inquiryRowCountsForFooter);
  const qty = counted.reduce((total, row) => total + Number(row.qty ?? '0'), 0);
  const taken = counted.reduce((total, row) => total + Number(row.linked_qty ?? '0'), 0);
  const bundled = counted.reduce((total, row) => total + Number(row.bundled_qty ?? '0'), 0);
  return { qty, taken, remaining: Math.max(qty - taken - bundled, 0) };
}

/**
 * How many days late this document is for this row (AC-D17).
 *
 * The server derives it from the row's delivery date and the document's expected date and
 * sends `late_days` beside `late`, so this reads it rather than computing a second answer
 * from the same two dates - the two could then differ, and the one on screen would be the
 * one nobody could reproduce.
 */
export function lateDaysOf(
  /** Structural, so the sales-order detail's own link shape reads here too. */
  link: { late?: boolean; late_days?: number | null; expected_date?: string | null },
): number | null {
  return typeof link.late_days === 'number' && link.late_days > 0 ? link.late_days : null;
}

/**
 * "Outstanding PO/SPO"'s coverage headline: `8 of 8`.
 *
 * A row with no links returns `null`, and the cell reads a plain dash (S5, AC-D4) rather
 * than printing "0 of 8" at somebody.
 *
 * Slice A (8 Sep 2026, nit S7 on review of `PLAN-scm-oi-reserving-feedback-8sep.md`):
 * this used to also group the row's links into a per-document `documents` array
 * (location, quantity, lateness), which the worklist cell printed inline. The cell no
 * longer prints anything per document - the new `OrderInquiryBackingDocumentsDialog`
 * reads `row.links` directly instead, at LINE granularity, which is a better fit for
 * "every backing document" (AC-A5) than this grouping ever was: two links on the same
 * document at different locations are two lines to key into AutoCount, and grouping them
 * into one entry with a concatenated `parts` string threw that apart. Lateness left with
 * it (AC-A3: nothing here says "late" any more). `lateDaysOf` itself stays - the sales
 * order detail's own link display (`SoLineLinksBody`) still reads it.
 */
export function linkedSummary(
  qty: string | null | undefined,
  linkedQty: string | null | undefined,
  links: OrderInquiryLink[] | null | undefined,
): { headline: string } | null {
  const list = links ?? [];
  if (list.length === 0) return null;
  return {
    headline: `${formatInquiryQty(linkedQty ?? '0')} of ${formatInquiryQty(qty ?? '0')}`,
  };
}

/**
 * The word (or count) a bundled cell names for what it rides with (UAC D10, plan
 * ruling 5, 9 Sep owner): "the UI never says host". One item names its own code;
 * two or more read `N items`, and the lightbox is where the codes themselves live.
 */
export function bundledItemsLabel(itemCodes: string[]): string {
  if (itemCodes.length <= 1) return itemCodes[0] ?? '';
  return `${itemCodes.length} items`;
}

/**
 * "Outstanding PO/SPO"'s headline for a bundled row (UAC D1-D3, D10; plan section 3.4).
 *
 * A row entirely covered by the bundle (`remainder <= 0`) reads `Included with <label>`
 * plus the ANCHOR's own coverage in the muted tail - `1 of 1`, or `Not found (new
 * order)` when nobody has placed anything for it yet. A row that is part bundled, part
 * ala carte reads `<bundled> with <label> · <own linked> of <ala carte remainder>` -
 * the remainder is `qty - bundled_qty`, not `qty`, because the ala carte portion is
 * everything the bundle does NOT cover.
 *
 * `null` when the row carries no bundle at all, so a caller falls back to
 * `linkedSummary` exactly as before - today's un-bundled rows are unaffected.
 *
 * The anchor's own coverage (`anchor_headline`) is resolved SERVER-SIDE (review round
 * 1 item 8) and read straight off `bundled_with` - never recomputed here by scanning
 * a page's own loaded rows for a match, which was only ever right when the anchor
 * happened to be on the SAME page as this row.
 */
export function bundledHeadline(
  row: Pick<OrderInquiryWorklistRow, 'qty' | 'linked_qty' | 'bundled_qty' | 'bundled_with'>,
): string | null {
  const bundled = row.bundled_with;
  if (!bundled) return null;
  const bundledQty = Number(row.bundled_qty ?? '0');
  if (!Number.isFinite(bundledQty) || bundledQty <= 0) return null;
  const label = bundledItemsLabel(bundled.item_codes.length ? bundled.item_codes : [bundled.item_code]);
  const qty = Number(row.qty ?? '0');
  const remainder = qty - bundledQty;
  if (remainder <= 0) {
    // S5, AC-D4: "Not found (new order)" renders nowhere any more.
    const tail = bundled.anchor_headline ?? 'Nothing linked yet';
    return `Included with ${label} · ${tail}`;
  }
  const ownLinked = formatInquiryQty(row.linked_qty ?? '0');
  return `${formatInquiryQty(String(bundledQty))} with ${label} · ${ownLinked} of ${formatInquiryQty(
    String(remainder),
  )}`;
}
