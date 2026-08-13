/**
 * ONE row model for every line of a plan.
 *
 * > "it should be just a list of products, whether it is covered by stock, within budget,
 * >  over budget, no price yet, needs a level, stock allocations, ALL should be in 1 table,
 * >  1 list, 1 data grid table ... I need to decide first, before you tell me within budget
 * >  or out of budget"
 *
 * The screen used to answer one question - what do we do about this product at this location -
 * in six separate boxes. Two of those boxes (Within budget, Over budget) were a verdict
 * reached before the buyer had decided anything, using a budget figure they had not entered.
 *
 * So the classification stops being a PLACE the row lives and becomes a `status` FIELD on it.
 * The budget stops being an input to the list and becomes a check applied afterwards, over the
 * lines the buyer actually decided to buy (see `planDecisions`).
 *
 * ## Why this is a pure frontend change
 *
 * All four sources were already the same record. `buy`, `covered`, `needs_level` and
 * `disposition` are values of `rec_type` on `scm.reorder_recommendation`, every one of them is
 * fetched as a `ReorderRecommendation`, and every fetch already pages past the endpoint's
 * 1,000-row cap and keeps the whole set. The six bands were one dataset being split four ways
 * on arrival. Putting it back together deletes code; it does not need an endpoint.
 */
import { m8CashImpact, recToPlanRow, type M8PlanRow } from './planRow';
import type { ReorderRecommendation } from '../types/reorder.types';

/**
 * What the PLAN found for this line. Not a verdict on what the buyer should do, and
 * deliberately not a budget position: `within` and `over` are absent by design, because they
 * are not knowable until the buyer has decided and a budget has been entered.
 */
export type PlanLineStatus =
  | 'buy'
  | 'covered_by_stock'
  | 'needs_level'
  | 'no_price'
  | 'allocation'
  | 'exception';

export const PLAN_LINE_STATUS_LABEL: Record<PlanLineStatus, string> = {
  buy: 'Buy',
  covered_by_stock: 'Covered by stock',
  needs_level: 'Needs a level',
  no_price: 'No price',
  allocation: 'Allocation',
  exception: 'Exception',
};

/** Order the filter chips and the default sort read in: the work first, the rest after. */
export const PLAN_LINE_STATUS_ORDER: PlanLineStatus[] = [
  'buy',
  'no_price',
  'needs_level',
  'covered_by_stock',
  'allocation',
  'exception',
];

export interface PlanLine extends M8PlanRow {
  status: PlanLineStatus;
  /** True when this line can become a purchase-order line. Allocations never can. */
  purchasable: boolean;
  /**
   * The engine's rank, or null when it never ranked this line.
   *
   * Kept separate from `M8PlanRow.rank`, which flattens null to 0. That flattening is
   * harmless while each kind of line lives in its own table and fatal the moment they share
   * one: on the live run EVERY covered and disposition line is unranked (3,228 of 4,229), so
   * a rank of 0 would float all of them above the highest-priority buy and the purchasing
   * work would start below three thousand rows of stock movements.
   */
  rankOrder: number | null;
}

/**
 * `no_price` is a property of the line, not a separate source.
 *
 * It sits ahead of `buy` because it is the more specific fact: a buy we cannot cost behaves
 * differently at the budget step, where it has to be reported rather than summed. Both causes
 * land here - no supplier cost at all, and a cost in a currency with no exchange rate - since
 * both leave the same hole in the total (see S10e).
 */
function statusOf(rec: ReorderRecommendation, row: M8PlanRow): PlanLineStatus {
  switch (rec.type) {
    case 'disposition':
      return 'allocation';
    case 'covered':
      return 'covered_by_stock';
    case 'needs_level':
      return 'needs_level';
    // Plan exceptions have their own review flow and are not fetched into this grid. Mapped
    // explicitly all the same, so that if they ever are, they arrive labelled as themselves
    // rather than silently counted as a purchase.
    case 'exception':
      return 'exception';
    case 'buy':
    default:
      return m8CashImpact(row) === null ? 'no_price' : 'buy';
  }
}

export function recToPlanLine(rec: ReorderRecommendation): PlanLine {
  const row = recToPlanRow(rec);
  const status = statusOf(rec, row);
  return {
    ...row,
    status,
    // An allocation is stock to move, not stock to order. It carries a decision so the buyer
    // can act on it in the same pass, but it must never reach a purchase order.
    purchasable: status !== 'allocation',
    rankOrder: rec.rank ?? null,
  };
}

/**
 * Every line of a plan, in one list, ranked.
 *
 * Ranked across the WHOLE plan rather than within each former band: the buyer works down one
 * list now, so a covered line and a buy line have to be comparable in the same ordering.
 * Lines the engine never ranked sort last rather than first, which is what an unranked
 * `null` would otherwise do.
 */
export function toPlanLines(...groups: (ReorderRecommendation[] | undefined)[]): PlanLine[] {
  const seen = new Set<string>();
  const out: PlanLine[] = [];
  for (const group of groups) {
    for (const rec of group ?? []) {
      if (seen.has(rec.id)) continue;
      seen.add(rec.id);
      out.push(recToPlanLine(rec));
    }
  }
  const UNRANKED = Number.MAX_SAFE_INTEGER;
  return out.sort((a, b) => (a.rankOrder ?? UNRANKED) - (b.rankOrder ?? UNRANKED));
}

export function countByStatus(lines: PlanLine[]): Record<PlanLineStatus, number> {
  const counts = {
    buy: 0, covered_by_stock: 0, needs_level: 0, no_price: 0, allocation: 0, exception: 0,
  } as Record<PlanLineStatus, number>;
  for (const l of lines) counts[l.status] += 1;
  return counts;
}
