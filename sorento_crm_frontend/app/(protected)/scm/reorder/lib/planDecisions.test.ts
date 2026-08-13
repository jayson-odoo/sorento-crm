/**
 * Decide first, then check the budget.
 *
 * The rule these tests exist to hold is that an undecided line is not a decision. The screen
 * this replaces treated a within-budget row as implicitly fundable, so a plan the buyer had
 * not finished reading looked like one they had agreed to.
 */
import { describe, it, expect } from 'vitest';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, toPlanLines, countByStatus, type PlanLine } from './planLine';
import {
  budgetVerdict,
  decidedCost,
  decidedQty,
  planTotals,
  proposeCuts,
  type PlanDecision,
  type PlanDecisionMap,
} from './planDecisions';

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product 1',
    abc_class: null, xyz_class: null, warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    product_id: 'p1', warehouse_id: 'w1', is_network: false, allocation: null,
    order_qty: 10, recommended_qty: 10, reorder_point: 0, min_qty: null, max_qty: null,
    order_up_to: 0, net_position: -10, days_of_cover: null, reason: 'reorder_point',
    reason_label: '', confidence: 'low', sample_size: 0,
    supplier: { supplier_code: 'S1', supplier_name: 'S1', unit_cost: 10,
                lead_time_days: 30, composite_score: 0, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 0, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 0, review_days: 0,
    moq: null, order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 10, cash_impact: 100, rank: 1, rank_score: 0, funding_status: null,
    days_to_stockout: null, rank_factors: [],
    on_hand: 0, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 10,
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));
const decisions = (m: Record<string, PlanDecision>) =>
  m as PlanDecisionMap;

describe('planLine - the classification is a field, not a place', () => {
  it('labels each source as itself', () => {
    expect(line().status).toBe('buy');
    expect(line({ type: 'covered' }).status).toBe('covered_by_stock');
    expect(line({ type: 'disposition' }).status).toBe('allocation');
    expect(line({ type: 'needs_level' }).status).toBe('needs_level');
  });

  it('calls an unpriceable buy what it is, without moving it out of the list', () => {
    expect(line({ unit_cost: null, cash_impact: null }).status).toBe('no_price');
  });

  it('never lets an allocation reach a purchase order', () => {
    expect(line({ type: 'disposition' }).purchasable).toBe(false);
    expect(line().purchasable).toBe(true);
  });

  it('has no budget position among its statuses, because nothing is decided yet', () => {
    // The two the old screen led with - Within budget, Over budget - are not knowable here
    // and must not exist as classifications of a line.
    expect(Object.keys(countByStatus([line()])).sort()).toEqual([
      'allocation', 'buy', 'covered_by_stock', 'exception', 'needs_level', 'no_price',
    ]);
  });
});

describe('toPlanLines - one list', () => {
  it('merges every source into one ranked list', () => {
    const lines = toPlanLines(
      [rec({ id: 'b', rank: 5 })],
      [rec({ id: 'c', type: 'covered', rank: 2 })],
      [rec({ id: 'd', type: 'disposition', rank: 9 })],
    );
    expect(lines.map((l) => l.id)).toEqual(['c', 'b', 'd']);
  });

  it('keeps one row per recommendation when sources overlap', () => {
    expect(toPlanLines([rec({ id: 'x' })], [rec({ id: 'x' })])).toHaveLength(1);
  });

  it('sorts an unranked line last, not first', () => {
    // Every covered and disposition line on the live run is unranked (3,228 of 4,229). If an
    // unranked line read as rank 0 they would all sit above the top-priority buy.
    const lines = toPlanLines([
      rec({ id: 'a', rank: null as unknown as number }),
      rec({ id: 'b', rank: 3 }),
    ]);
    expect(lines.map((l) => l.id)).toEqual(['b', 'a']);
    expect(lines.find((l) => l.id === 'a')?.rankOrder).toBeNull();
  });
});

describe('planTotals - silence is not consent', () => {
  it('counts an untouched line as undecided, never as a buy', () => {
    const t = planTotals([line({ id: 'a' }), line({ id: 'b' })], decisions({}));
    expect(t).toMatchObject({ undecided: 2, decided: 0, buying: 0, units: 0, cost: 0 });
  });

  it('adds up only what was actually decided', () => {
    const lines = [line({ id: 'a' }), line({ id: 'b' }), line({ id: 'c' })];
    const t = planTotals(lines, decisions({ a: { buy: 10 }, b: { stock: { qty: 5, sources: [{ warehouse_id: 'w2', warehouse_code: 'W2', qty: 5 }] } } }));
    expect(t).toMatchObject({ decided: 2, undecided: 1, buying: 1, usingStock: 1, units: 10, cost: 100 });
  });

  it('honours an edited quantity', () => {
    const t = planTotals([line({ id: 'a' })], decisions({ a: { buy: 4 } }));
    expect(t.units).toBe(4);
    expect(t.cost).toBe(40);
  });

  it('spends nothing on a use-stock or a skip', () => {
    const lines = [line({ id: 'a' }), line({ id: 'b' })];
    const t = planTotals(lines, decisions({ a: { stock: { qty: 5, sources: [{ warehouse_id: 'w2', warehouse_code: 'W2', qty: 5 }] } }, b: { skip: true } }));
    expect(t.cost).toBe(0);
    expect(t.units).toBe(0);
  });

  it('counts an unpriced buy separately and never sums it as zero', () => {
    const lines = [line({ id: 'a' }), line({ id: 'b', unit_cost: null, cash_impact: null })];
    const t = planTotals(lines, decisions({ a: { buy: 10 }, b: { buy: 10 } }));
    expect(t.cost).toBe(100);
    expect(t.unpriced).toBe(1);
    expect(t.buying).toBe(2);
  });

  it('spends nothing on an allocation even if it is somehow decided as a buy', () => {
    // A stock allocation is a movement of stock we already own. Reaching a purchase order it
    // would be money spent twice, so the model refuses it rather than trusting every call
    // site not to offer the choice.
    const alloc = line({ id: 'a', type: 'disposition' });
    expect(alloc.purchasable).toBe(false);
    expect(decidedQty(alloc, { buy: 10 })).toBe(0);
    expect(decidedCost(alloc, { buy: 10 })).toBe(0);
    expect(planTotals([alloc], decisions({ a: { buy: 10 } }))).toMatchObject({
      cost: 0, units: 0, unpriced: 0,
    });
  });
});

describe('decidedQty', () => {
  it('is zero for anything that is not a buy', () => {
    expect(decidedQty(line(), { stock: { qty: 5, sources: [{ warehouse_id: 'w2', warehouse_code: 'W2', qty: 5 }] } })).toBe(0);
    expect(decidedQty(line(), { skip: true })).toBe(0);
    expect(decidedQty(line(), undefined)).toBe(0);
  });

  it('falls back to the suggested quantity', () => {
    expect(decidedQty(line(), { buy: 10 })).toBe(10);
  });
});

describe('budgetVerdict - the budget is a question asked at the end', () => {
  it('gives no verdict until a budget is entered', () => {
    const t = planTotals([line()], decisions({ r1: { buy: 10 } }));
    const v = budgetVerdict(t, null);
    expect(v.budget).toBeNull();
    expect(v.remaining).toBeNull();
    expect(v.over).toBe(false);
  });

  it('does NOT treat no budget as a budget of zero', () => {
    const t = planTotals([line()], decisions({ r1: { buy: 10 } }));
    expect(budgetVerdict(t, null).over).toBe(false);
  });

  it('reports what is left when the decisions fit', () => {
    const t = planTotals([line()], decisions({ r1: { buy: 10 } }));
    expect(budgetVerdict(t, 500)).toMatchObject({ over: false, remaining: 400 });
  });

  it('reports the overrun when they do not', () => {
    const t = planTotals([line()], decisions({ r1: { buy: 10 } }));
    expect(budgetVerdict(t, 60)).toMatchObject({ over: true, remaining: -40 });
  });

  it('carries the unpriced count, so the verdict states its own incompleteness', () => {
    const lines = [line({ id: 'a' }), line({ id: 'b', unit_cost: null, cash_impact: null })];
    const t = planTotals(lines, decisions({ a: { buy: 10 }, b: { buy: 10 } }));
    expect(budgetVerdict(t, 500).unpriced).toBe(1);
  });
});

describe('proposeCuts - the allocator advises at the end instead of deciding at the start', () => {
  const three = [
    line({ id: 'a', rank: 1, cash_impact: 100, unit_cost: 10 }),
    line({ id: 'b', rank: 2, cash_impact: 100, unit_cost: 10 }),
    line({ id: 'c', rank: 3, cash_impact: 100, unit_cost: 10 }),
  ];
  const allBuys = decisions({ a: { buy: 10 }, b: { buy: 10 }, c: { buy: 10 } });

  it('proposes nothing when the decisions fit', () => {
    expect(proposeCuts(three, allBuys, 300)).toEqual([]);
  });

  it('proposes nothing when no budget has been entered', () => {
    expect(proposeCuts(three, allBuys, null)).toEqual([]);
  });

  it('cuts the worst-ranked first, and only as far as it must', () => {
    expect(proposeCuts(three, allBuys, 250).map((l) => l.id)).toEqual(['c']);
    expect(proposeCuts(three, allBuys, 150).map((l) => l.id)).toEqual(['c', 'b']);
  });

  it('never proposes cutting a line it cannot price', () => {
    // Dropping it would save an amount nobody can state, so it cannot be justified as
    // closing the gap.
    const withUnpriced = [
      ...three,
      line({ id: 'z', rank: 99, unit_cost: null, cash_impact: null }),
    ];
    const d = decisions({ ...allBuys, z: { buy: 10 } } as never);
    expect(proposeCuts(withUnpriced, d, 250).map((l) => l.id)).toEqual(['c']);
  });

  it('leaves lines the buyer did not decide to buy alone', () => {
    const d = decisions({ a: { buy: 10 }, b: { stock: { qty: 5, sources: [{ warehouse_id: 'w2', warehouse_code: 'W2', qty: 5 }] } }, c: { skip: true } });
    expect(proposeCuts(three, d, 50).map((l) => l.id)).toEqual(['a']);
  });
});

describe('the use_po decision (S15)', () => {
  it('orders nothing, costs nothing, and is counted', () => {
    const l = line();
    const d = { po: 200 };

    expect(decidedQty(l, d)).toBe(0);
    expect(decidedCost(l, d)).toBe(0);
    expect(planTotals([l], { [l.id]: d })).toMatchObject({
      decided: 1, usingPo: 1, buying: 0, units: 0, cost: 0,
    });
  });
});
