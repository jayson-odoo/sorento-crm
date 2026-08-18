/**
 * Building the multi-order planning board out of raw demand lines (PLAN section 13).
 *
 * Pure, and separate from every component, because the three things worth arguing about here
 * are arithmetic rather than layout: which column a line lands in (13.3), what order competing
 * lines are served in (13.5), and whether an order is fully decided yet (13.4). Each one is an
 * acceptance criterion, and none of them needs a table mounted to be checked.
 *
 * `today` is always passed in, never read from the clock. "Overdue" is 37 per cent of the book,
 * so a board that quietly disagreed with itself between two renders would be disagreeing about
 * the biggest column on screen.
 */
import type {
  BoardCell,
  BoardCellLocation,
  BoardContribution,
  BoardDateBucket,
  BoardDraft,
  BoardGranularity,
  BoardOrderStanding,
  BoardProductRow,
  BoardSource,
  PlanningBoard,
} from '../types/fulfilmentPlanning.types';
import { fromMinor, toMinor } from './supplyComposition';

/** One still-owed core sales-order line, which is all the board is ever built from. */
export interface BoardDemandLine {
  sales_order_id: string;
  so_number: string;
  customer_name?: string | null;
  project_label?: string | null;
  line_no: number;
  item_code: string;
  qty: string;
  required_date?: string | null;
  /** The core line's own warehouse code. Empty or null means the source record is silent. */
  fulfilment_location?: string | null;
  priority?: 'high' | 'medium' | 'low' | null;
}

export const OVERDUE_BUCKET = 'overdue';
export const NO_DATE_BUCKET = 'no_date';

const PRIORITY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 };

/** Monday of the ISO week containing `iso`, as a date-only string. */
export function weekStart(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`);
  // getUTCDay is 0 for Sunday; shift so Monday is 0 and the week runs Mon..Sun.
  const offset = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - offset);
  return date.toISOString().slice(0, 10);
}

export function monthStart(iso: string): string {
  return `${iso.slice(0, 7)}-01`;
}

/**
 * Which column a line belongs in.
 *
 * Overdue swallows every past date whatever it is: they are all equally late, and spreading
 * three years of history across the axis would push the columns anyone can still act on off
 * the right-hand edge. A line with no date gets its own column rather than being guessed into
 * one, for the same reason no warehouse is ever guessed (section 11, question 2).
 */
export function bucketKeyFor(
  requiredDate: string | null | undefined,
  today: string,
  granularity: BoardGranularity,
): string {
  if (!requiredDate) return NO_DATE_BUCKET;
  if (requiredDate < today) return OVERDUE_BUCKET;
  return granularity === 'month' ? monthStart(requiredDate) : weekStart(requiredDate);
}

function bucketLabel(key: string, granularity: BoardGranularity): string {
  if (key === OVERDUE_BUCKET) return 'Overdue';
  if (key === NO_DATE_BUCKET) return 'No date';
  const [year, month, day] = key.split('-');
  const MONTHS = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  const monthName = MONTHS[Number(month) - 1] ?? month;
  return granularity === 'month'
    ? `${monthName} ${year}`
    : `w/c ${Number(day)} ${monthName} ${year}`;
}

/**
 * The order competing lines are served in (13.5), and it is TOTAL.
 *
 * 1. Earliest required date, because the work that is due soonest gets the stock. An undated
 *    line sorts last: nothing about it says it is urgent.
 * 2. Then a stated priority. Measured at 14 rows in 90,548, so it is a real override where
 *    somebody bothered and decides nothing at all for everyone else - which is exactly why it
 *    is the tie-break and not the key.
 * 3. Then the sales-order number, so two lines can never compare equal. A non-total rule gives
 *    a different answer on each refresh, and "why did this order lose today" becomes
 *    unanswerable.
 */
export function compareContributions(
  left: Pick<BoardContribution, 'required_date' | 'priority' | 'so_number' | 'line_no'>,
  right: Pick<BoardContribution, 'required_date' | 'priority' | 'so_number' | 'line_no'>,
): number {
  const leftDate = left.required_date ?? null;
  const rightDate = right.required_date ?? null;
  if (leftDate !== rightDate) {
    if (leftDate === null) return 1;
    if (rightDate === null) return -1;
    return leftDate < rightDate ? -1 : 1;
  }
  const leftRank = PRIORITY_RANK[left.priority ?? ''] ?? 3;
  const rightRank = PRIORITY_RANK[right.priority ?? ''] ?? 3;
  if (leftRank !== rightRank) return leftRank - rightRank;
  const byOrder = left.so_number.localeCompare(right.so_number);
  return byOrder !== 0 ? byOrder : left.line_no - right.line_no;
}

/** Free stock available to the board, keyed `${item_code}|${location}`. */
export type FreeStock = Record<string, string>;

/**
 * Serve one cell's contributions from free stock in priority order, and say who lost.
 *
 * Deliberately NOT pro-rata. Splitting 100 units across five lines needing 100 each produces
 * five short deliveries instead of one complete one and four honest Buys, and short-shipping
 * everybody is the worst outcome available.
 *
 * `remaining` is mutated across cells by the caller so the same free stock cannot be promised
 * twice on two different dates - which is the whole defect this board exists to surface.
 */
function allocate(
  contributions: BoardContribution[],
  remaining: Record<string, number>,
  /** How much has actually been taken at each `${item}|${location}` so far, board-wide. */
  consumed: Record<string, number>,
): void {
  for (const contribution of contributions) {
    if (contribution.unplannable) {
      contribution.sources = [
        {
          kind: 'unplannable',
          qty: contribution.qty,
          location: null,
          reason: 'No fulfilment location on the sales order line, so nothing can be sourced for it.',
        },
      ];
      continue;
    }
    const location = contribution.fulfilment_location as string;
    const stockKey = `${contribution.item_code}|${location}`;
    const need = toMinor(contribution.qty);
    const free = remaining[stockKey] ?? 0;
    const reserved = Math.min(free, need);
    remaining[stockKey] = free - reserved;
    const buy = need - reserved;

    const sources: BoardSource[] = [];
    if (reserved > 0) {
      sources.push({
        kind: 'reserve',
        qty: fromMinor(reserved),
        location,
        reason: `Free unclaimed stock at ${location} covers this much by the required date.`,
      });
    }
    if (buy > 0) {
      sources.push({
        kind: 'buy',
        qty: fromMinor(buy),
        location: null,
        reason:
          reserved > 0
            ? `Free stock at ${location} ran out on this line; the residual is bought.`
            : `Nothing free at ${location} by the required date, so the whole quantity is bought.`,
      });
    }
    contribution.sources = sources;
    // Contested means somebody earlier in the rule actually TOOK the stock this line would
    // otherwise have had. A line at a location that never held any is not contested, it is
    // simply a Buy; calling both the same thing would make the flag mean nothing.
    contribution.contested = buy > 0 && (consumed[stockKey] ?? 0) > 0;
    consumed[stockKey] = (consumed[stockKey] ?? 0) + reserved;
  }
}

/**
 * The whole board: buckets across, products down, one cell per pair that anybody owes.
 *
 * A pair nobody owes produces NO cell, and the grid renders that as blank. A blank cell is not
 * a zero - it means no selected order owes this product by this date - which is the same rule
 * the delivery-schedule matrix states about its own blanks.
 */
export function buildBoard(
  lines: BoardDemandLine[],
  options: { today: string; granularity?: BoardGranularity; freeStock?: FreeStock },
): PlanningBoard {
  const granularity = options.granularity ?? 'week';
  const { today } = options;

  const contributionsByCell = new Map<string, BoardContribution[]>();
  const bucketKeys = new Set<string>();
  const productSet = new Set<string>();

  for (const line of lines) {
    const bucketKey = bucketKeyFor(line.required_date, today, granularity);
    const location = line.fulfilment_location || null;
    const cellKey = `${line.item_code}|${bucketKey}`;
    bucketKeys.add(bucketKey);
    productSet.add(line.item_code);
    const contribution: BoardContribution = {
      key: `${line.sales_order_id}|${line.line_no}|${line.item_code}|${bucketKey}`,
      sales_order_id: line.sales_order_id,
      so_number: line.so_number,
      customer_name: line.customer_name ?? null,
      project_label: line.project_label ?? null,
      line_no: line.line_no,
      item_code: line.item_code,
      qty: line.qty,
      required_date: line.required_date ?? null,
      fulfilment_location: location,
      unplannable: !location,
      priority: line.priority ?? null,
      sources: [],
      contested: false,
    };
    const bucket = contributionsByCell.get(cellKey);
    if (bucket) bucket.push(contribution);
    else contributionsByCell.set(cellKey, [contribution]);
  }

  // One running pool for the whole board, drawn down in the order the buckets are served, so
  // stock promised to an overdue line is not promised again to a later one.
  const remaining: Record<string, number> = {};
  for (const [key, qty] of Object.entries(options.freeStock ?? {})) {
    remaining[key] = toMinor(qty);
  }
  const consumed: Record<string, number> = {};

  const dateBuckets = orderBuckets([...bucketKeys], granularity);
  const cells: BoardCell[] = [];

  for (const bucket of dateBuckets) {
    for (const item of [...productSet].sort()) {
      const contributions = contributionsByCell.get(`${item}|${bucket.key}`);
      if (!contributions || contributions.length === 0) continue;
      contributions.sort(compareContributions);
      allocate(contributions, remaining, consumed);
      cells.push({
        item_code: item,
        bucket_key: bucket.key,
        total_qty: fromMinor(
          contributions.reduce((total, entry) => total + toMinor(entry.qty), 0),
        ),
        locations: locationsOf(contributions),
        contributions,
        unplannable_count: contributions.filter((entry) => entry.unplannable).length,
        contested_count: contributions.filter((entry) => entry.contested).length,
      });
    }
  }

  const productRows: BoardProductRow[] = [...productSet]
    .sort()
    .map((item_code) => ({ item_code }));

  return {
    granularity,
    as_of: today,
    dateBuckets,
    productRows,
    cells,
    orders: standingsFor(lines, {}, { today, granularity }),
  };
}

/** Overdue pinned first, dated in ascending order, No date pinned last (13.3). */
function orderBuckets(keys: string[], granularity: BoardGranularity): BoardDateBucket[] {
  const dated = keys
    .filter((key) => key !== OVERDUE_BUCKET && key !== NO_DATE_BUCKET)
    .sort();
  const buckets: BoardDateBucket[] = [];
  if (keys.includes(OVERDUE_BUCKET)) {
    buckets.push({ key: OVERDUE_BUCKET, kind: 'overdue', label: 'Overdue', start: null });
  }
  for (const key of dated) {
    buckets.push({
      key,
      kind: 'dated',
      label: bucketLabel(key, granularity),
      start: key,
    });
  }
  if (keys.includes(NO_DATE_BUCKET)) {
    buckets.push({ key: NO_DATE_BUCKET, kind: 'no_date', label: 'No date', start: null });
  }
  return buckets;
}

/**
 * The cell's source strip. One entry per distinct location, biggest first, with the lines that
 * have no location gathered under a null so the strip still adds up to the cell total.
 */
function locationsOf(contributions: BoardContribution[]): BoardCellLocation[] {
  const totals = new Map<string | null, number>();
  for (const contribution of contributions) {
    const key = contribution.fulfilment_location ?? null;
    totals.set(key, (totals.get(key) ?? 0) + toMinor(contribution.qty));
  }
  return [...totals.entries()]
    .sort((left, right) => right[1] - left[1])
    .map(([location, qty]) => ({ location, qty: fromMinor(qty) }));
}

/**
 * Per order: how many of its lines in this selection carry a verdict yet.
 *
 * This is the number that makes the partial-decision reality visible (13.4). A cell holds one
 * product on one date and an order spans many lines across many dates, so approving one cell
 * almost never finishes an order, and the board has to say so rather than imply the cell
 * committed something.
 */
export function standingsFor(
  lines: BoardDemandLine[],
  draft: BoardDraft,
  options: { today?: string; granularity?: BoardGranularity } = {},
): BoardOrderStanding[] {
  const today = options.today ?? '1970-01-01';
  const granularity = options.granularity ?? 'week';
  const byOrder = new Map<string, BoardOrderStanding>();
  for (const line of lines) {
    const standing = byOrder.get(line.sales_order_id) ?? {
      sales_order_id: line.sales_order_id,
      so_number: line.so_number,
      customer_name: line.customer_name ?? null,
      line_count: 0,
      decided_count: 0,
      unplannable_count: 0,
    };
    standing.line_count += 1;
    if (!line.fulfilment_location) standing.unplannable_count += 1;
    const bucketKey = bucketKeyFor(line.required_date, today, granularity);
    const key = `${line.sales_order_id}|${line.line_no}|${line.item_code}|${bucketKey}`;
    if (draft[key]) standing.decided_count += 1;
    byOrder.set(line.sales_order_id, standing);
  }
  return [...byOrder.values()].sort((left, right) =>
    left.so_number.localeCompare(right.so_number),
  );
}

/**
 * Why this order cannot be confirmed yet, or null when it can.
 *
 * A disabled button that does not say why is the thing that makes a screen feel broken, and
 * here the reason is the entire point of the design question in 13.4.
 */
export function confirmBlockedReason(standing: BoardOrderStanding): string | null {
  if (standing.unplannable_count > 0) {
    const count = standing.unplannable_count;
    return `${count} line${count === 1 ? '' : 's'} ha${count === 1 ? 's' : 've'} no fulfilment location on the sales order.`;
  }
  if (standing.decided_count < standing.line_count) {
    return `${standing.decided_count} of ${standing.line_count} lines decided.`;
  }
  return null;
}

/**
 * Whether an amend needs a reason.
 *
 * Reducing the Reserve the rule proposed takes stock away from this line and hands it to
 * nobody in particular, so a person has to say why. Accepting the proposal unchanged does not:
 * demanding a reason for agreeing is how a mandatory field becomes a rubber stamp.
 */
export function amendNeedsReason(
  contribution: BoardContribution,
  reserveQty: string,
): boolean {
  const proposed = contribution.sources
    .filter((source) => source.kind === 'reserve')
    .reduce((total, source) => total + toMinor(source.qty), 0);
  return toMinor(reserveQty) !== proposed;
}
