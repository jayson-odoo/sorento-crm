/**
 * What the buyer decided, and what it adds up to.
 *
 * > "you don't tell me what's over or within budget, because I haven't decided which one i
 * >  want to buy, which one i want to use existing stock ... during planning, I don't even
 * >  need to specify the budget, I should check my budget at the end of decisions made for all
 * >  products"
 *
 * The old screen ran this backwards: a budget was assumed, the allocator spent it, and the
 * buyer reacted to a split they had not authorised. Here nothing is spent until a decision is
 * taken, and the budget is a question asked of the finished decisions.
 *
 * ## Undecided is a state, not a default
 *
 * The single most important rule in this file. The old screen treated a within-budget line as
 * implicitly fundable, so a plan the buyer had not finished reading looked like a plan they
 * had agreed to. A line nobody has touched is `undecided`: it is not a buy, it is not a skip,
 * it is counted and reported separately, and it never enters a total. "I have not got to it
 * yet" must never render as "there is nothing left to buy".
 */
import { m8CashImpact } from './planRow';
import type { PlanLine } from './planLine';

export type PlanDecisionKind = 'buy' | 'use_stock' | 'skip';

export interface PlanDecision {
  kind: PlanDecisionKind;
  /** Units to buy. Only meaningful for `buy`; the suggested quantity unless edited. */
  qty?: number;
  /** Why the buyer departed from the suggestion, carried onto the adjustment. */
  reason?: string;
}

export type PlanDecisionMap = Readonly<Record<string, PlanDecision | undefined>>;

/**
 * Units this line will actually order. Anything but a `buy` orders nothing.
 *
 * A line that cannot be purchased orders nothing either, whatever decision it carries. That
 * is enforced here rather than left to the UI to avoid offering the choice: a stock
 * allocation reaching a purchase order would be money spent on a movement of stock we already
 * own, and one careless call site should not be able to cause it.
 */
export function decidedQty(line: PlanLine, decision: PlanDecision | undefined): number {
  if (!line.purchasable) return 0;
  if (!decision || decision.kind !== 'buy') return 0;
  return decision.qty ?? line.order_qty;
}

/**
 * What one decided line costs, or `null` when it cannot be costed.
 *
 * Null is NOT zero and the two must never be added together: a line we cannot price still has
 * to be bought, it simply cannot be weighed against a budget (S10e). The totals below keep
 * them in separate counters for exactly this reason.
 */
export function decidedCost(line: PlanLine, decision: PlanDecision | undefined): number | null {
  const qty = decidedQty(line, decision);
  if (qty <= 0) return 0;
  const perUnit = m8CashImpact({
    order_qty: 1,
    unit_cost: line.unit_cost,
    unit_cost_base: line.unit_cost_base,
  });
  return perUnit === null ? null : perUnit * qty;
}

export interface PlanTotals {
  /** Lines the buyer has settled, whichever way. */
  decided: number;
  /** Lines still untouched. Reported so an unfinished pass cannot read as a finished one. */
  undecided: number;
  buying: number;
  usingStock: number;
  skipped: number;
  /** Units across every buy decision. */
  units: number;
  /** Money for the buy decisions we CAN price. */
  cost: number;
  /** Buy decisions with no price. Counted, never summed as zero. */
  unpriced: number;
}

/**
 * Roll the decisions up. Allocations are included in the counts, because the buyer decided
 * them too, but they can never contribute money: `purchasable` is false, so `decidedQty`
 * feeds off a `buy` they cannot be given.
 */
export function planTotals(lines: PlanLine[], decisions: PlanDecisionMap): PlanTotals {
  const t: PlanTotals = {
    decided: 0, undecided: 0, buying: 0, usingStock: 0, skipped: 0,
    units: 0, cost: 0, unpriced: 0,
  };
  for (const line of lines) {
    const d = decisions[line.id];
    if (!d) {
      t.undecided += 1;
      continue;
    }
    t.decided += 1;
    if (d.kind === 'use_stock') t.usingStock += 1;
    else if (d.kind === 'skip') t.skipped += 1;
    else {
      t.buying += 1;
      const qty = decidedQty(line, d);
      t.units += qty;
      const cost = decidedCost(line, d);
      if (cost === null) t.unpriced += 1;
      else t.cost += cost;
    }
  }
  return t;
}

export interface BudgetVerdict {
  /** Null until the buyer enters one. No budget is not a budget of zero. */
  budget: number | null;
  cost: number;
  /** Positive when there is room left, negative when the decisions overrun. */
  remaining: number | null;
  over: boolean;
  /** Buy decisions that could not be priced, so the verdict is incomplete by this much. */
  unpriced: number;
}

/**
 * Measure the finished decisions against a budget.
 *
 * Only called once the buyer asks. Until then there is no verdict to give, and `budget: null`
 * says so rather than implying the plan fits inside nothing.
 */
export function budgetVerdict(totals: PlanTotals, budget: number | null): BudgetVerdict {
  const hasBudget = budget !== null && Number.isFinite(budget);
  return {
    budget: hasBudget ? budget : null,
    cost: totals.cost,
    remaining: hasBudget ? (budget as number) - totals.cost : null,
    over: hasBudget ? totals.cost > (budget as number) : false,
    unpriced: totals.unpriced,
  };
}

/**
 * When the decisions overrun, which ones to drop.
 *
 * Worst-ranked first, dropping until the remainder fits: the same greedy ordering the plan
 * used to apply up front, moved to the end where it belongs. It is a PROPOSAL - each line is
 * accepted or overruled individually - so the allocator advises here instead of deciding.
 *
 * Unpriceable lines are never proposed for the cut. Dropping one saves an amount nobody can
 * state, so it cannot be justified as closing a gap.
 */
export function proposeCuts(
  lines: PlanLine[],
  decisions: PlanDecisionMap,
  budget: number | null,
): PlanLine[] {
  if (budget === null || !Number.isFinite(budget)) return [];
  const buys = lines
    .filter((l) => decisions[l.id]?.kind === 'buy')
    .map((l) => ({ line: l, cost: decidedCost(l, decisions[l.id]) }))
    .filter((x): x is { line: PlanLine; cost: number } => x.cost !== null && x.cost > 0);

  let total = buys.reduce((s, b) => s + b.cost, 0);
  if (total <= budget) return [];

  const UNRANKED = Number.MAX_SAFE_INTEGER;
  const worstFirst = [...buys].sort(
    (a, b) => (b.line.rank ?? UNRANKED) - (a.line.rank ?? UNRANKED),
  );
  const cuts: PlanLine[] = [];
  for (const b of worstFirst) {
    if (total <= budget) break;
    cuts.push(b.line);
    total -= b.cost;
  }
  return cuts;
}
