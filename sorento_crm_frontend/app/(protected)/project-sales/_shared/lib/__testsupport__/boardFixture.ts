/**
 * TEST SUPPORT ONLY. Builds a realistic planning board in the shape seam B returns.
 *
 * This is the Phase 1 board engine, kept after the mock was deleted because the component tests
 * genuinely reuse it: hand-writing a 300-cell board per test would be unreadable, and a board
 * assembled by hand drifts from the real shape in exactly the ways a test is supposed to catch.
 *
 * It is NOT imported by any production module, and must not be. The server owns bucketing,
 * ranking and allocation now; a second implementation on this side is the defect that
 * `app/services/scm/priority.py` exists to warn about.
 */
import type {
  BoardCell,
  BoardCellLocation,
  BoardContribution,
  BoardDateBucket,
  BoardGranularity,
  BoardOrderStanding,
  BoardPolicy,
  BoardProductRow,
  BoardRankFactor,
  BoardSource,
  PlanningBoard,
} from '../../types/fulfilmentPlanning.types';
import { fromMinor, toMinor } from '../supplyComposition';
import { standingsFor } from '../fulfilmentBoard';
export { standingsFor };

/**
 * Building the multi-order planning board out of raw demand lines (PLAN section 13).
 *
 * Pure, and separate from every component, because the three things worth arguing about here
 * are arithmetic rather than layout: which column a line lands in (13.3), what order competing
 * lines are served in (13.5), and whether an order is fully decided yet (13.4). Each one is an
 * acceptance criterion, and none of them needs a table mounted to be checked.
 *
 * `today` is always passed in, never read from the clock. 37 per cent of the book is already
 * past its required date, so a board that quietly disagreed with itself between two renders
 * would be disagreeing about which third of its columns are tinted.
 */


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
  /** `sales_orders.order_date`, the document this row IS. Feeds `document_age` (13.5). */
  order_date?: string | null;
  /** `customers.payment_terms_days`. The only credit signal with real coverage (13.5). */
  payment_terms_days?: number | null;
  /** Always 'project' on this board, so it weighs but never discriminates. */
  demand_class?: string | null;
}

/**
 * The live `scm.priority_policy` row, as seeded.
 *
 * Reproduced here so the mock ranks by the real thing rather than by an invention, and so the
 * blocker in PLAN 13.5 is visible rather than hidden: this policy weights ONLY
 * `po_document_sequence`, which no sales-order line can have, so under it every board row scores
 * 0.0 and the board cannot rank at all.
 */
export const LIVE_POLICY: BoardPolicy = {
  name: "Today's rule (PO document sequence)",
  factors: {
    po_document_sequence: 1.0,
    demand_class: 0.0,
    need_by_date: 0.0,
    document_age: 0.0,
  },
  demand_class_weights: { project: 1.0, retail: 0.4 },
  is_preview: false,
  discriminates_nothing: true,
};

/**
 * The what-if the board offers instead, so a planner can see what a fair weighting would do
 * before anybody switches it on (13.5, recommendation 3 then 2).
 *
 * Weighted on the three factors a sales-order demand row can actually carry. `demand_class` is
 * left at zero on purpose: every row on this board is project-class, so weighting it would add a
 * constant to every score and separate nothing.
 */
export const PREVIEW_POLICY: BoardPolicy = {
  name: 'Fulfilment board preview (delivery date, document date, customer credit)',
  factors: {
    po_document_sequence: 0.0,
    demand_class: 0.0,
    need_by_date: 3.0,
    document_age: 1.0,
    customer_credit: 1.0,
  },
  demand_class_weights: { project: 1.0, retail: 0.4 },
  is_preview: true,
  discriminates_nothing: false,
};

export const NO_DATE_BUCKET = 'no_date';

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
 * EVERY dated line buckets by its own required date, past or future (the captain: "don't put
 * overdue together, still split by the date"). A past date is not a category, it is a date,
 * and the aggregate column that used to swallow them threw away the only thing that says how
 * late a line is - one selection collapsed 160 of 160 lines into a single column. The past is
 * tinted instead, which costs columns and keeps the information.
 *
 * A line with no date gets its own column rather than being guessed into one, for the same
 * reason no warehouse is ever guessed (section 11, question 2).
 *
 * `today` is kept in the signature because `is_past` is measured against it; it no longer
 * decides which bucket anything lands in.
 */
export function bucketKeyFor(
  requiredDate: string | null | undefined,
  _today: string,
  granularity: BoardGranularity,
): string {
  if (!requiredDate) return NO_DATE_BUCKET;
  if (granularity === 'month') return monthStart(requiredDate);
  // Day granularity keys on the date itself; the 30-day window that keeps 349 of them off one
  // screen is applied when the columns are ORDERED, never when they are assigned, so nothing is
  // filtered out of the plan by a display choice.
  if (granularity === 'day') return requiredDate;
  return weekStart(requiredDate);
}

function bucketLabel(key: string, granularity: BoardGranularity): string {
  if (key === NO_DATE_BUCKET) return 'No date';
  const [year, month, day] = key.split('-');
  const MONTHS = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  const monthName = MONTHS[Number(month) - 1] ?? month;
  if (granularity === 'month') return `${monthName} ${year}`;
  if (granularity === 'day') return `${Number(day)} ${monthName} ${year}`;
  return `w/c ${Number(day)} ${monthName} ${year}`;
}

/**
 * `SUM(w*v) / SUM(w present)` over the PRESENT factors only.
 *
 * Lifted deliberately from the reorder engine's `cash_ranking.rank_score`, including the rule
 * that carries the whole design: a factor with NO VALUE is dropped from the numerator AND the
 * denominator, never scored as zero. An unknown is not a bad score. Returns 0.0 when nothing is
 * present, which is exactly what the live policy produces on this board (see `LIVE_POLICY`).
 */
export function rankScore(factors: BoardRankFactor[]): number {
  let numerator = 0;
  let denominator = 0;
  for (const factor of factors) {
    if (!factor.present || factor.value === null) continue;
    numerator += factor.weight * factor.value;
    denominator += factor.weight;
  }
  return denominator > 0 ? numerator / denominator : 0;
}

/** Sooner (or smaller) is higher, normalized across the set present. Absent stays absent. */
function normalizeAscending(values: (number | null)[]): (number | null)[] {
  const present = values.filter((value): value is number => value !== null);
  if (present.length === 0) return values.map(() => null);
  const low = Math.min(...present);
  const high = Math.max(...present);
  const span = high - low || 1;
  return values.map((value) => (value === null ? null : 1 - (value - low) / span));
}

const DAY = 86_400_000;
const dayNumber = (iso: string) => Math.round(Date.parse(`${iso}T00:00:00Z`) / DAY);

/**
 * The factors behind every contributor in one cell, per PLAN 13.5.
 *
 * Values are normalized ACROSS THE CANDIDATE SET, the way the reorder engine's `date_values`
 * does: a rank only ever means "against the others competing for this stock", and a score
 * normalized against the whole book would be dominated by orders that are not in the fight.
 *
 *   need_by_date     sooner is higher      <- the captain's "delivery date"
 *   document_age     older is higher       <- the captain's "document date" (the SO's own)
 *   customer_credit  shorter terms higher  <- the only credit signal with coverage
 *   demand_class     the policy's weight for the row's class (constant on this board)
 *   po_document_sequence  ALWAYS ABSENT: a sales-order line has no purchase order
 */
function factorsForCell(
  contributions: BoardContribution[],
  lines: Map<string, BoardDemandLine>,
  policy: BoardPolicy,
): void {
  const meta = contributions.map((entry) => lines.get(entry.key));
  const needBy = normalizeAscending(
    contributions.map((entry) => (entry.required_date ? dayNumber(entry.required_date) : null)),
  );
  // Older document is higher, and `normalizeAscending` already gives 1.0 to the SMALLEST value,
  // which for a date is the earliest one. So the raw day number is fed straight in: negating it
  // (the first attempt) handed the top score to the NEWEST document, the exact opposite of what
  // "document age" means, and the ranking read plausibly while being backwards.
  const age = normalizeAscending(
    meta.map((entry) => (entry?.order_date ? dayNumber(entry.order_date) : null)),
  );
  const credit = normalizeAscending(
    meta.map((entry) =>
      entry?.payment_terms_days === null || entry?.payment_terms_days === undefined
        ? null
        : entry.payment_terms_days,
    ),
  );

  contributions.forEach((contribution, index) => {
    const demandClass = meta[index]?.demand_class ?? 'project';
    const classWeight = policy.demand_class_weights[demandClass];
    const values: Record<string, number | null> = {
      po_document_sequence: null,
      demand_class: classWeight === undefined ? null : classWeight,
      need_by_date: needBy[index],
      document_age: age[index],
      customer_credit: credit[index],
    };
    contribution.rank_factors = Object.keys(policy.factors)
      .concat(Object.keys(values).filter((key) => !(key in policy.factors)))
      .filter((key, position, all) => all.indexOf(key) === position)
      .map((key) => {
        const value = values[key] ?? null;
        return {
          key,
          weight: Number(policy.factors[key] ?? 0),
          value,
          present: value !== null,
        };
      });
    contribution.rank_score = rankScore(contribution.rank_factors);
  });
}

/**
 * The order competing lines are served in, and it is TOTAL.
 *
 * Highest rank first (13.5). Ties break on the sales-order number and then the line number, so
 * two contributors can never compare equal: a non-total rule gives a different answer on each
 * refresh, and "why did this order lose today" becomes unanswerable.
 *
 * Under a policy that can score nothing - which is the live one - every score is 0.0 and this
 * degrades to sales-order order. That is a flat ranking rather than a wrong one, and the board
 * says so on screen rather than hiding it behind an arbitrary sort.
 */
export function compareContributions(
  left: Pick<BoardContribution, 'rank_score' | 'so_number' | 'line_no'>,
  right: Pick<BoardContribution, 'rank_score' | 'so_number' | 'line_no'>,
): number {
  if (left.rank_score !== right.rank_score) return right.rank_score - left.rank_score;
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
    // Contested means the stock this line would otherwise have had was actually TAKEN, either
    // by a higher-ranked line in this same cell or by an earlier bucket that drew the pool down
    // first. Both are "somebody got there before you"; the screen therefore says exactly that
    // rather than naming a cause it cannot always know. A line at a location that never held
    // any stock is NOT contested, it is simply a Buy.
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
export const DAY_WINDOW_COLUMNS = 30;

export function buildBoard(
  lines: BoardDemandLine[],
  options: {
    today: string;
    granularity?: BoardGranularity;
    freeStock?: FreeStock;
    policy?: BoardPolicy;
    /** First day of the day-granularity window. Defaults to the earliest future date owed. */
    dayWindowStart?: string;
  },
): PlanningBoard {
  const granularity = options.granularity ?? 'week';
  const policy = options.policy ?? LIVE_POLICY;
  const { today } = options;

  const contributionsByCell = new Map<string, BoardContribution[]>();
  const lineByKey = new Map<string, BoardDemandLine>();
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
      // The LINE's own lateness, which is not its bucket's: a line due yesterday is late while
      // the week holding it still has days to come. An undated line is never late - nobody
      // said when it was due.
      is_past: Boolean(line.required_date && line.required_date < today),
      fulfilment_location: location,
      unplannable: !location,
      priority: line.priority ?? null,
      sources: [],
      contested: false,
      rank_score: 0,
      rank_factors: [],
    };
    const bucket = contributionsByCell.get(cellKey);
    if (bucket) bucket.push(contribution);
    else contributionsByCell.set(cellKey, [contribution]);
    lineByKey.set(contribution.key, line);
  }

  // One running pool for the whole board, drawn down in the order the buckets are served, so
  // stock promised to an earlier-dated line is not promised again to a later one.
  const remaining: Record<string, number> = {};
  for (const [key, qty] of Object.entries(options.freeStock ?? {})) {
    remaining[key] = toMinor(qty);
  }
  const consumed: Record<string, number> = {};

  const dateBuckets = orderBuckets(
    [...bucketKeys],
    granularity,
    today,
    options.dayWindowStart,
  );
  const shown = new Set(dateBuckets.map((bucket) => bucket.key));
  const cells: BoardCell[] = [];

  // ALLOCATION RUNS OVER EVERY BUCKET IN THE SELECTION, in date order, and the window is
  // applied afterwards purely to decide which cells are emitted. Allocating only the displayed
  // buckets made `contested` window-COMPUTED rather than window-scoped: a line outside the day
  // window got no proposal at all, so it could not be contested even in principle, and the same
  // line read Reserve on week and had no verdict on day.
  const allBuckets = [...bucketKeys]
    .filter((key) => key !== NO_DATE_BUCKET)
    .sort()
    .concat(bucketKeys.has(NO_DATE_BUCKET) ? [NO_DATE_BUCKET] : []);

  for (const bucketKey of allBuckets) {
    for (const item of [...productSet].sort()) {
      const contributions = contributionsByCell.get(`${item}|${bucketKey}`);
      if (!contributions || contributions.length === 0) continue;
      // Score first, then serve down the ranking: the order stock is given out in IS the
      // ranking, so computing it after the sort would be describing a decision already taken.
      factorsForCell(contributions, lineByKey, policy);
      contributions.sort(compareContributions);
      allocate(contributions, remaining, consumed);
      if (!shown.has(bucketKey)) continue;
      cells.push({
        item_code: item,
        bucket_key: bucketKey,
        total_qty: fromMinor(
          contributions.reduce((total, entry) => total + toMinor(entry.qty), 0),
        ),
        locations: locationsOf(contributions),
        contributions,
        unplannable_count: contributions.filter((entry) => entry.unplannable).length,
        contested_count: contributions.filter((entry) => entry.contested).length,
        past_count: contributions.filter((entry) => entry.is_past).length,
      });
    }
  }

  const productRows: BoardProductRow[] = [...productSet]
    .sort()
    .map((item_code) => ({ item_code }));

  const everyContribution = [...contributionsByCell.values()].flat();

  return {
    granularity,
    policy,
    as_of: today,
    // Counted over the whole SELECTION, never over `cells`: these are the numbers a window must
    // not be able to move, and the day window is what proved it.
    line_count: everyContribution.length,
    past_line_count: everyContribution.filter((entry) => entry.is_past).length,
    unplannable_line_count: everyContribution.filter((entry) => entry.unplannable).length,
    contested_line_count: everyContribution.filter((entry) => entry.contested).length,
    dateBuckets,
    productRows,
    cells,
    orders: ordersFor(everyContribution),
  };
}

/**
 * One standing per order, over every contributing line of the selection.
 *
 * `decided_count` is 0 here exactly as the server sends it (deviation 4): the verdicts are the
 * client's, and `standingsFor` overlays them.
 */
function ordersFor(contributions: BoardContribution[]): BoardOrderStanding[] {
  const byOrder = new Map<string, BoardOrderStanding>();
  for (const contribution of contributions) {
    const standing = byOrder.get(contribution.sales_order_id) ?? {
      sales_order_id: contribution.sales_order_id,
      so_number: contribution.so_number,
      customer_name: contribution.customer_name ?? null,
      line_count: 0,
      decided_count: 0,
      unplannable_count: 0,
    };
    standing.line_count += 1;
    if (contribution.unplannable) standing.unplannable_count += 1;
    byOrder.set(contribution.sales_order_id, standing);
  }
  return [...byOrder.values()].sort((left, right) =>
    left.so_number.localeCompare(right.so_number),
  );
}

/**
 * Dated columns in ascending order, past included, and No date pinned last (13.3, as amended
 * by the captain): a date is a date however far back, and No date is the only answer with no
 * place on a timeline.
 *
 * At day granularity the dated columns are a 30-day WINDOW rather than one column per distinct
 * date, because the book carries 349 of them. Days inside the window with nothing owed are still
 * rendered: a calendar that hides its empty days is not a calendar, and the gap is the
 * information. Demand outside the window is never dropped from the plan; it is reached by moving
 * the window.
 */
function orderBuckets(
  keys: string[],
  granularity: BoardGranularity,
  today: string,
  dayWindowStart?: string,
): BoardDateBucket[] {
  let dated = keys.filter((key) => key !== NO_DATE_BUCKET).sort();

  if (granularity === 'day') {
    const start = dayWindowStart ?? dated[0];
    if (start) {
      const from = dayNumber(start);
      dated = Array.from({ length: DAY_WINDOW_COLUMNS }, (_unused, offset) =>
        new Date((from + offset) * DAY).toISOString().slice(0, 10),
      );
    }
  }
  const buckets: BoardDateBucket[] = dated.map((key) => ({
    key,
    kind: 'dated' as const,
    label: bucketLabel(key, granularity),
    start: key,
    is_past: bucketEnd(key, granularity) < today,
  }));
  if (keys.includes(NO_DATE_BUCKET)) {
    buckets.push({
      key: NO_DATE_BUCKET,
      kind: 'no_date',
      label: 'No date',
      start: null,
      is_past: false,
    });
  }
  return buckets;
}

/**
 * The last day the bucket covers. A bucket counts as past only when the WHOLE of it is behind
 * `as_of`: the week that contains today still holds dates anybody can act on, so tinting it
 * would call the current week late.
 */
function bucketEnd(key: string, granularity: BoardGranularity): string {
  if (granularity === 'day') return key;
  if (granularity === 'week') {
    return new Date((dayNumber(key) + 6) * DAY).toISOString().slice(0, 10);
  }
  const [year, month] = key.split('-').map(Number);
  // Day 0 of the next month is the last day of this one.
  return new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10);
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

