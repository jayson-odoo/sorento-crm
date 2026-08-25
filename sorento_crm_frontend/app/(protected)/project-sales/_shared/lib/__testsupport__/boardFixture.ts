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
  BoardAheadLine,
  BoardCell,
  BoardCellLocation,
  BoardContribution,
  BoardDateBucket,
  BoardGranularity,
  BoardLineDecision,
  BoardLineOrderInquiry,
  BoardOrderStanding,
  BoardPolicy,
  BoardProductRow,
  BoardRankFactor,
  BoardSource,
  BoardTrailStep,
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
  /** The product's own name, which the board's search matches as well as the code. */
  product_name?: string | null;
  qty: string;
  /** What the sales order ordered on the line. A server fact, never derived here. */
  qty_ordered?: string | null;
  /** What has already been delivered on the line. Ordered - delivered = outstanding. */
  qty_delivered?: string | null;
  /** The mirror line the confirmation names. Addressing only. */
  project_line_id?: string | null;
  required_date?: string | null;
  /** The core line's own warehouse code. Empty or null means the source record is silent. */
  fulfilment_location?: string | null;
  priority?: 'high' | 'medium' | 'low' | null;
  /**
   * What the ENGINE proposed for this line at the moment it was decided (AC-D1), frozen in
   * the decision's snapshot. Only meaningful beside `decision`; an undecided line's
   * suggestion is its live proposal and is built below.
   *
   * Absent on a covered line means the revision predates the field: "not recorded".
   */
  proposed_components?: BoardSource[];
  /** `sales_orders.order_date`, the document this row IS. Feeds `document_age` (13.5). */
  order_date?: string | null;
  /** `customers.payment_terms_days`. The only credit signal with real coverage (13.5). */
  payment_terms_days?: number | null;
  /** Always 'project' on this board, so it weighs but never discriminates. */
  demand_class?: string | null;
  /**
   * An ACTIVE decision already covers this line, and this is what it froze (13.4).
   *
   * Such a line is NOT run through the allocation below, exactly as the server does not run it
   * through the ladder: it states the frozen composition, carries no trail, is never contested
   * and says nothing about a queue it is not in.
   */
  decision?: BoardLineDecision | null;
  /**
   * The order inquiry purchasing was given for this line, and how far they got with it.
   *
   * Absent on most of the board, exactly as it is on the server: an inquiry exists only once
   * somebody has confirmed supply, so `null` is the ordinary case rather than a gap.
   */
  order_inquiry?: BoardLineOrderInquiry | null;
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
  return `${Number(day)} ${monthName} ${year}`;
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
  // What each pile held when this cell was reached, and what the lines served before this one
  // still want out of it - the fair share the server states per contribution (PLAN 13.7). The
  // server queues the whole book; this queues the cell, which is as much as a fixture can see.
  const opening: Record<string, number> = {};
  const ahead: Record<string, { lines: number; qty: number }> = {};
  // WHO is in each queue, in the order they were served, so a rung can name them the way the
  // server does rather than only counting them.
  const queued: Record<string, BoardContribution[]> = {};
  for (const contribution of contributions) {
    if (contribution.unplannable || contribution.covered) continue;
    const stockKey = `${contribution.item_code}|${contribution.fulfilment_location}`;
    if (!(stockKey in opening)) opening[stockKey] = remaining[stockKey] ?? 0;
  }

  for (const contribution of contributions) {
    // A line an active decision covers is not planned again, and draws nothing down: its
    // claim on the pile is already expressed as a hold, which is why the server's own queue
    // leaves it out too.
    if (contribution.covered) {
      applyFrozen(contribution);
      continue;
    }
    if (contribution.unplannable) {
      contribution.sources = [
        {
          kind: 'unplannable',
          qty: contribution.qty,
          location: null,
          reason: 'No fulfilment location on the sales order line, so nothing can be sourced for it.',
        },
      ];
      // No ladder was walked for it, so it carries no trail - never an invented empty one -
      // and no flags: it was judged against nothing.
      contribution.trail = [];
      contribution.item_flags = null;
      continue;
    }
    const location = contribution.fulfilment_location as string;
    const stockKey = `${contribution.item_code}|${location}`;
    const need = toMinor(contribution.qty);
    const queue = ahead[stockKey] ?? { lines: 0, qty: 0 };
    contribution.so_qty_ahead = fromMinor(queue.qty);
    contribution.lines_ahead = queue.lines;
    // Never negative: a pile the queue has already over-claimed has nothing left, which is not
    // the same as owing the queue something.
    contribution.available_to_this_line = fromMinor(
      Math.max((opening[stockKey] ?? 0) - queue.qty, 0),
    );
    ahead[stockKey] = { lines: queue.lines + 1, qty: queue.qty + need };
    const free = remaining[stockKey] ?? 0;
    const reserved = Math.min(free, need);
    remaining[stockKey] = free - reserved;
    const buy = need - reserved;

    const sources: BoardSource[] = [];
    if (reserved > 0) {
      sources.push({
        kind: 'reserve',
        // THE RUNG IS PART OF WHAT THE ENGINE SENDS, and the whole vocabulary is keyed on it
        // (`supplyVocabulary.rowOf`). This fixture draws from the LINE'S OWN location, which
        // ladder v3 reaches on the group-take rung.
        rung: 'group_take',
        qty: fromMinor(reserved),
        location,
        warehouse_id: `wh-${location}`,
        reason: `Free unclaimed stock at ${location} covers this much by the delivery date.`,
      });
    }
    if (buy > 0) {
      sources.push({
        kind: 'buy',
        rung: 'buy',
        qty: fromMinor(buy),
        location: null,
        reason:
          reserved > 0
            ? `Free stock at ${location} ran out on this line; the residual is bought.`
            : `Nothing free at ${location} by the delivery date, so the whole quantity is bought.`,
      });
    }
    contribution.sources = sources;
    // An undecided line's suggestion IS its live proposal, sent under the key the decision
    // strip reads for every line (AC-D2). The server sends the same list twice for exactly
    // this reason: one key, both states.
    contribution.proposed = { components: sources };
    // The item facts the ladder judged the line on, said rather than implied. This fixture models
    // an ordinary item: classified, not dealer hot-selling, not discontinued. A test that wants a
    // flagged item overrides these on the contribution, as it does the trail's steps.
    contribution.item_flags = {
      dealer_hot_selling: false,
      dealer_hot_selling_where: [],
      project_hot_selling: false,
      project_hot_selling_where: [],
      dealer_classified: false,
      project_classified: false,
      discontinued: false,
      retail_classification_available: true,
    };
    contribution.trail = trailFor({
      location,
      opening: opening[stockKey] ?? 0,
      ahead: queue,
      aheadLines: queued[stockKey] ?? [],
      mine: contribution,
      offered: toMinor(contribution.available_to_this_line),
      reserved,
      need,
      buy,
    });
    queued[stockKey] = [...(queued[stockKey] ?? []), contribution];
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
 * A covered line, as the server sends one: the FROZEN composition and nothing else.
 *
 * No trail (no ladder was walked), never contested (a decided line is not competing), and no
 * share of the queue - `undefined` rather than `'0'`, because "0 left for this line" is a claim
 * about a contest this line is not in.
 */
function applyFrozen(contribution: BoardContribution): void {
  const decision = contribution.decision as BoardLineDecision;
  const sources: BoardSource[] = [];
  for (const row of decision.reserve ?? []) {
    sources.push({
      kind: 'reserve',
      // Whatever the decision states, and nothing invented. A revision frozen since AC-D1
      // carries the rung on every component; one frozen before it carries none, and the FE
      // still reads that back off the ownership group (`supplyVocabulary.fallbackRung`) -
      // which is the path AC-A2 failed on, so both cases have to stay reachable here.
      rung: row.rung ?? null,
      qty: row.qty,
      location: row.location ?? null,
      warehouse_id: row.warehouse_id,
      reason: `Reserved at ${row.location} in revision ${decision.revision_no}.`,
    });
  }
  if (toMinor(decision.timely_spo_qty) > 0) {
    sources.push({
      kind: 'timely_spo',
      qty: decision.timely_spo_qty,
      location: contribution.fulfilment_location ?? null,
      warehouse_id: contribution.fulfilment_warehouse_id,
      reason: `Incoming supply, as confirmed in revision ${decision.revision_no}.`,
    });
  }
  for (const row of decision.borrow ?? []) {
    sources.push({
      kind: 'borrow',
      // The frozen BORROW row is the ONE the board does pass a rung through on (see
      // `_frozen_decision`), so the fixture passes through whatever the decision states.
      rung: row.rung ?? null,
      qty: row.qty,
      location: row.location ?? null,
      warehouse_id: row.warehouse_id,
      reason: `Borrowed from ${row.location} in revision ${decision.revision_no}. ${row.reason}`,
    });
  }
  if (toMinor(decision.buy_qty) > 0) {
    sources.push({
      kind: 'buy',
      qty: decision.buy_qty,
      location: null,
      reason: `Bought, as confirmed in revision ${decision.revision_no}.`,
    });
  }
  contribution.sources = sources;
  // What the ENGINE had said, frozen beside the decision (AC-D1). Absent on a revision
  // written before that field existed, which the screen reads as "not recorded" - the
  // fixture leaves it undefined for exactly that case rather than inventing one.
  contribution.proposed = contribution.proposed ?? null;
  contribution.trail = [];
  contribution.item_flags = null;
  contribution.contested = false;
  contribution.qty_proposed_reserve = fromMinor(
    (decision.reserve ?? []).reduce((total, row) => total + toMinor(row.qty), 0),
  );
  contribution.qty_proposed_incoming = decision.timely_spo_qty;
  contribution.qty_proposed_buy = decision.buy_qty;
}

/**
 * The ladder as the server states it, ladder v2's own order (section E of
 * `PLAN-demo-followups-19aug-ladder-v2.md`, S4 of the 19 August review): the read-only own
 * location, then Incoming, Pool, Group take, Group borrow, Cross-group borrow, Buy. The
 * own-location Reserve rung is GONE AS A SOURCE (rule 7) but stays as a read-only first
 * rung, because it is the one place the queue ahead of THIS line at ITS OWN pile is named -
 * `BoardTrailPopover`'s `QueueLink` opens exactly `fulfilment_warehouse_id`, which is this
 * rung's own location and nowhere else's.
 *
 * This fixture only ever models one pool and one cross-group donor, so `group_take` and
 * `group_borrow` are always empty - which is exactly the case worth having in the tests,
 * because "checked and had nothing" is the reading the screen must not silently drop.
 */
function trailFor(input: {
  location: string;
  opening: number;
  ahead: { lines: number; qty: number };
  /** The contributions actually served before this one at the same pile, in queue order. */
  aheadLines: BoardContribution[];
  mine: BoardContribution;
  offered: number;
  reserved: number;
  need: number;
  buy: number;
}): BoardTrailStep[] {
  const steps: BoardTrailStep[] = [];
  let remaining = input.need;

  const add = (
    kind: BoardTrailStep['kind'],
    fields: Omit<
      Partial<BoardTrailStep>,
      'step' | 'kind' | 'offered' | 'taken' | 'remaining_after'
    > & { offered: number; taken: number },
  ) => {
    const wanted = remaining;
    remaining = Math.max(remaining - fields.taken, 0);
    const outcome: BoardTrailStep['outcome'] =
      fields.outcome ??
      (fields.taken > 0
        ? 'took'
        : wanted <= 0
          ? 'none_needed'
          : 'nothing_left');
    steps.push({
      ...fields,
      step: steps.length + 1,
      kind,
      offered: fromMinor(fields.offered),
      taken: fromMinor(fields.taken),
      remaining_after: fromMinor(remaining),
      outcome,
    });
  };

  const named = input.aheadLines.slice(0, 3).map((other) => aheadLineOf(other, input.mine));
  const byFactor: Record<string, number> = {};
  for (const other of input.aheadLines) {
    const key = leadingFactorOf(other, input.mine);
    byFactor[key] = (byFactor[key] ?? 0) + 1;
  }
  // 0. Read-only: this line's own location. Never taken (rule 7), but the ONE rung that
  // names the queue ahead of it, exactly as the real backend's `reserve_own` rung does.
  add('reserve_own', {
    location: input.location,
    warehouse_id: `wh-${input.location}`,
    opening: fromMinor(input.opening),
    ahead_qty: fromMinor(input.ahead.qty),
    ahead_lines: input.ahead.lines,
    ahead: named,
    ahead_more: Math.max(input.aheadLines.length - named.length, 0),
    ahead_by_factor: byFactor,
    offered: input.offered,
    taken: 0,
    outcome: 'not_eligible',
    why:
      input.ahead.lines > 0
        ? `${fromMinor(input.offered)} left at ${input.location} after ${fromMinor(input.ahead.qty)} outstanding to ${input.ahead.lines} line${input.ahead.lines === 1 ? '' : 's'} ranked ahead of this line. Never reserved: stock at ${input.location} is committed to whichever sales order is queued for it - borrow from another sales order instead.`
        : `${fromMinor(input.offered)} at ${input.location}, nothing ranked ahead of this line there. Never reserved: stock at ${input.location} is committed to whichever sales order is queued for it - borrow from another sales order instead.`,
  });
  add('incoming', {
    location: input.location,
    warehouse_id: `wh-${input.location}`,
    opening: '0',
    offered: 0,
    taken: 0,
    why: 'No supplier PO arrives by 3 Sep 2026.',
  });
  add('pool', {
    location: input.location,
    warehouse_id: `wh-${input.location}`,
    opening: fromMinor(input.opening),
    offered: input.offered,
    taken: input.reserved,
    why:
      input.reserved > 0
        ? `${input.location} offers ${fromMinor(input.offered)}; this line takes ${fromMinor(input.reserved)}.`
        : input.offered > 0
          ? `${input.location} offers ${fromMinor(input.offered)}, but nothing is left for this line.`
          : `No shared pool for this product.`,
  });
  add('group_take', {
    offered: 0,
    taken: 0,
    note: 'no ownership group',
    why: 'This location carries no ownership group, so there are no siblings to take from.',
  });
  add('group_borrow', {
    offered: 0,
    taken: 0,
    why: 'No other sales order in this ownership group is ranked below this line.',
  });
  add('cross_group_borrow', {
    opening: '0',
    offered: 0,
    taken: 0,
    why: 'No other location holds this product free.',
  });
  add('buy', {
    offered: input.buy,
    taken: input.buy,
    why:
      input.buy > 0
        ? 'Nothing left to take, so the remainder is bought.'
        : 'Fully covered before this rung.',
  });
  return steps;
}

/** One queued line as the server names it, against the line that is asking. */
function aheadLineOf(other: BoardContribution, mine: BoardContribution): BoardAheadLine {
  return {
    so_number: other.so_number,
    line_no: other.line_no,
    qty: other.qty,
    required_date: other.required_date ?? null,
    rank_score: other.rank_score,
    leading_factor: leadingFactorOf(other, mine),
    same_order: other.sales_order_id === mine.sales_order_id,
  };
}

/**
 * Which factor put `other` in front of `mine`: the largest weighted difference, exactly as the
 * server computes it. Equal scores mean the policy separated nothing, so the tie-break is named
 * instead of a factor the two lines do not differ on.
 */
function leadingFactorOf(other: BoardContribution, mine: BoardContribution): string {
  const tie = other.sales_order_id === mine.sales_order_id ? 'line_order' : 'tie_break';
  if (other.rank_score === mine.rank_score) return tie;
  const ours = new Map(
    (mine.rank_factors ?? [])
      .filter((factor) => factor.present && factor.value !== null)
      .map((factor) => [factor.key, factor.value as number]),
  );
  let best: string | null = null;
  let bestDiff = 0;
  for (const factor of other.rank_factors ?? []) {
    if (!factor.present || factor.value === null || factor.weight <= 0) continue;
    const mineValue = ours.get(factor.key);
    if (mineValue === undefined) continue;
    const diff = factor.weight * (factor.value - mineValue);
    if (diff > bestDiff) {
      best = factor.key;
      bestDiff = diff;
    }
  }
  return best ?? tie;
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
      // Addressing only, and only so the pile queue can be asked for: the queue is keyed by the
      // core line at its (product, location).
      line_id: `core-${line.sales_order_id}-${line.line_no}`,
      product_id: `prod-${line.item_code}`,
      so_number: line.so_number,
      customer_name: line.customer_name ?? null,
      project_label: line.project_label ?? null,
      line_no: line.line_no,
      item_code: line.item_code,
      qty: line.qty,
      qty_ordered: line.qty_ordered ?? null,
      qty_delivered: line.qty_delivered ?? null,
      qty_outstanding: line.qty,
      project_line_id: line.project_line_id ?? `pl-${line.sales_order_id}-${line.line_no}`,
      required_date: line.required_date ?? null,
      // The LINE's own lateness, which is not its bucket's: a line due yesterday is late while
      // the week holding it still has days to come. An undated line is never late - nobody
      // said when it was due.
      is_past: Boolean(line.required_date && line.required_date < today),
      fulfilment_location: location,
      fulfilment_warehouse_id: location ? `wh-${location}` : null,
      unplannable: !location,
      priority: line.priority ?? null,
      sources: [],
      contested: false,
      rank_score: 0,
      rank_factors: [],
      covered: Boolean(line.decision),
      decision: line.decision ?? null,
      // What the engine suggested when this line was decided (AC-D1). A test states it only
      // when the difference between suggested and decided is what it is about.
      proposed: line.proposed_components
        ? { components: line.proposed_components }
        : undefined,
      order_inquiry: line.order_inquiry ?? null,
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

  const nameByItem = new Map<string, string | null>();
  for (const line of lines) {
    if (line.product_name) nameByItem.set(line.item_code, line.product_name);
  }
  const productRows: BoardProductRow[] = [...productSet]
    .sort()
    .map((item_code) => ({ item_code, description: nameByItem.get(item_code) ?? null }));

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
    // Unwindowed, exactly like `cells` deliberately is NOT: `everyContribution` already carries
    // every bucket in the selection, allocated above BEFORE the window narrowed which cells are
    // emitted (see the comment on `allBuckets`) - the same thing the real board's top-level
    // `contributions` states for the reason a day window must not change what Approve all or
    // the List view act on.
    contributions: everyContribution,
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
      project_sales_order_id: `pso-${contribution.sales_order_id}`,
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

