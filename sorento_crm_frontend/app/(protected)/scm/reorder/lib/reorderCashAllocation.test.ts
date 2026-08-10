import { describe, it, expect } from 'vitest';
import type { RankFactor, ReorderRecommendation } from '../types/reorder.types';
import {
  computeFunding,
  computeFundingM8,
  defaultBudgetFor,
  scoreFromFactors,
  sliderMaxFor,
  type M8FundingRow,
} from './reorderCashAllocation';

/** Minimal buy rec for allocator tests - only the fields the allocator reads. */
function rec(
  id: string,
  rank: number,
  cashImpact: number | null,
  daysToStockout: number | null = rank,
): ReorderRecommendation {
  return {
    id,
    type: 'buy',
    sku: id,
    product_name: id,
    abc_class: null,
    xyz_class: null,
    warehouse_code: null,
    warehouse_name: null,
    is_network: false,
    allocation: null,
    order_qty: 1,
    recommended_qty: 1,
    reorder_point: null,
    min_qty: null,
    max_qty: null,
    order_up_to: null,
    net_position: null,
    days_of_cover: null,
    reason: 'reorder_point',
    reason_label: null,
    confidence: null,
    sample_size: 0,
    supplier: null,
    alternatives: [],
    is_exception: false,
    disposition_action: null,
    transfer_flag: null,
    forecast_daily_demand: null,
    lead_time_days: null,
    lead_time_source: null,
    safety_stock: null,
    safety_stock_method: null,
    safety_stock_fallback: null,
    service_level: null,
    safety_days: null,
    review_days: null,
    moq: null,
    order_multiple: null,
    policy_type: 'reorder_point',
    supplier_selection: 'primary',
    unit_cost: cashImpact,
    cash_impact: cashImpact,
    rank,
    rank_score: 1 - rank / 100,
    funding_status: null,
    days_to_stockout: daysToStockout,
    rank_factors: [],
  };
}

describe('computeFunding - greedy skip-overflow (M4-D3)', () => {
  it('funds whole items, skips an overflowing one and continues to the next that fits', () => {
    // budget 12000; by rank: 6000 fund→rem6000, 5000 fund→rem1000, 8000 overflow→
    // deferred, 1000 fits→funded. Σ funded 12000 ≤ budget.
    const recs = [rec('a', 1, 6000), rec('b', 2, 5000), rec('c', 3, 8000), rec('d', 4, 1000)];
    const r = computeFunding(recs, 12000);
    expect(r.funded.map((x) => x.id).sort()).toEqual(['a', 'b', 'd']);
    expect(r.deferred.map((x) => x.id)).toEqual(['c']);
    expect(r.fundedCash).toBe(12000);
    expect(r.fundedCash).toBeLessThanOrEqual(12000);
    expect(r.funded.every((x) => x.funding_status === 'funded')).toBe(true);
  });

  it('parks uncosted buys in needs_cost regardless of budget (M4-D16)', () => {
    const r = computeFunding([rec('a', 1, 5000), rec('b', 2, null)], 100000);
    expect(r.needsCost.map((x) => x.id)).toEqual(['b']);
    expect(r.needsCost[0].funding_status).toBe('needs_cost');
    expect(r.funded.map((x) => x.id)).toEqual(['a']);
    expect(r.fundedCash).toBe(5000); // uncosted never counted against budget
  });

  it('budget 0 → all costed deferred; budget ≥ Σ → all costed funded', () => {
    const recs = [rec('a', 1, 5000), rec('b', 2, 3000), rec('c', 3, null)];
    const zero = computeFunding(recs, 0);
    expect(zero.funded).toHaveLength(0);
    expect(zero.deferred.map((x) => x.id).sort()).toEqual(['a', 'b']);
    expect(zero.needsCost.map((x) => x.id)).toEqual(['c']);

    const all = computeFunding(recs, 9000);
    expect(all.funded.map((x) => x.id).sort()).toEqual(['a', 'b']);
    expect(all.deferred).toHaveLength(0);
    expect(all.fundedCash).toBeLessThanOrEqual(9000);
  });

  it('orders deferred by soonest stockout first', () => {
    const recs = [rec('a', 1, 5000, 20), rec('b', 2, 5000, 3)];
    const r = computeFunding(recs, 0);
    expect(r.deferred.map((x) => x.id)).toEqual(['b', 'a']); // 3d before 20d
  });
});

describe('computeFundingM8 - reject keeps the row IN PLACE (M8-F1 REVISED)', () => {
  const r = (id: string, rank: number, cost: number | null): M8FundingRow => ({
    id,
    rank,
    order_qty: 1,
    unit_cost: cost,
  });
  const NONE: ReadonlySet<string> = new Set();

  it('a within-budget row that is rejected STAYS within budget, cash excluded', () => {
    // a 5000, b 3000 (REJECTED), c 2000; ample budget so all three would fund.
    // M8-F1 REVISED: reject no longer routes b into Over - it stays in the section
    // the budget lands it in (Within), just greyed + excluded from committed.
    const rows = [r('a', 1, 5000), r('b', 2, 3000), r('c', 3, 2000)];
    const out = computeFundingM8(rows, 100000, { pins: NONE, rejects: new Set(['b']) });

    // the rejected row is STILL in the result AND stays in Within (not moved to Over).
    const allIds = [...out.within, ...out.over, ...out.needsCost].map((x) => x.id).sort();
    expect(allIds).toEqual(['a', 'b', 'c']);
    expect(out.within.map((x) => x.id)).toContain('b');
    expect(out.over.map((x) => x.id)).not.toContain('b');

    // its cash is excluded from committed (only a + c count: 5000 + 2000 = 7000).
    expect(out.committed).toBe(7000);
    expect(out.free).toBe(100000 - 7000);
  });

  it('an over-budget row that is rejected STAYS in Over budget', () => {
    // budget only covers a (5000). b + c fall to Over on the budget alone. Rejecting
    // b must leave it exactly where it was (Over), never bump it up or down.
    const rows = [r('a', 1, 5000), r('b', 2, 3000), r('c', 3, 4000)];
    const out = computeFundingM8(rows, 5000, { pins: NONE, rejects: new Set(['b']) });
    expect(out.within.map((x) => x.id)).toEqual(['a']);
    expect(out.committed).toBe(5000); // b's 3000 never counted
    expect(out.over.map((x) => x.id).sort()).toEqual(['b', 'c']);
  });

  it('a rejected row never draws down the budget (frees cash for the rest)', () => {
    // budget 7000. Without reject: a(5000)+b(3000) would take 8000 → b defers. With b
    // rejected, b consumes nothing, so c(2000) still fits alongside a within budget.
    const rows = [r('a', 1, 5000), r('b', 2, 3000), r('c', 3, 2000)];
    const out = computeFundingM8(rows, 7000, { pins: NONE, rejects: new Set(['b']) });
    // b did not eat the budget, so a + c both fund (7000); b sits over-budget, unfunded.
    expect(out.within.map((x) => x.id).sort()).toEqual(['a', 'c']);
    expect(out.over.map((x) => x.id)).toEqual(['b']);
    expect(out.committed).toBe(7000);
  });

  it('a pinned (dragged-in) row that is rejected stays within, cash excluded', () => {
    // a is pinned to Within but rejected: the pin holds its section (M8-F1), the
    // reject strips its cash from committed.
    const rows = [r('a', 1, 5000), r('b', 2, 3000)];
    const out = computeFundingM8(rows, 3000, {
      pins: new Set(['a']),
      rejects: new Set(['a']),
    });
    expect(out.within.map((x) => x.id)).toContain('a');
    expect(out.committed).toBe(3000); // only b's 3000; a's 5000 excluded
  });

  it('re-accepting (empty rejects) restores the row to normal funding', () => {
    const rows = [r('a', 1, 5000), r('b', 2, 3000)];
    const out = computeFundingM8(rows, 100000, { pins: NONE, rejects: NONE });
    expect(out.within.map((x) => x.id).sort()).toEqual(['a', 'b']);
    expect(out.committed).toBe(8000);
  });
});

describe('computeFundingM8 - pins are ADDITIVE, dragging one row never evicts another (M8-F)', () => {
  const r = (id: string, rank: number, cost: number): M8FundingRow => ({
    id,
    rank,
    order_qty: 1,
    unit_cost: cost,
  });
  const NONE: ReadonlySet<string> = new Set();

  it('pinning an over-budget row keeps every already-funded row Within (no eviction)', () => {
    // budget 8000. Greedy funds a(5000)+c(2000); b(6000) is over budget.
    const rows = [r('a', 1, 5000), r('b', 2, 6000), r('c', 3, 2000)];
    const base = computeFundingM8(rows, 8000, { pins: NONE, rejects: NONE });
    expect(base.within.map((x) => x.id).sort()).toEqual(['a', 'c']);
    expect(base.over.map((x) => x.id)).toEqual(['b']);

    // Drag b up (pin it). b must JOIN Within; a and c must STAY Within (the old
    // budget-first pin evicted a here). Overspend just shows as a negative free.
    const out = computeFundingM8(rows, 8000, { pins: new Set(['b']), rejects: NONE });
    expect(out.within.map((x) => x.id).sort()).toEqual(['a', 'b', 'c']);
    expect(out.over).toEqual([]);
    expect(out.committed).toBe(13000);
    expect(out.free).toBe(8000 - 13000); // negative = pinned overspend
  });

  it('deferring (forcedOver) a funded row moves only that row to Over', () => {
    const rows = [r('a', 1, 5000), r('b', 2, 2000), r('c', 3, 1000)];
    // ample budget: all three would fund; force b to Over.
    const out = computeFundingM8(rows, 100000, {
      pins: NONE,
      rejects: NONE,
      forcedOver: new Set(['b']),
    });
    expect(out.within.map((x) => x.id).sort()).toEqual(['a', 'c']);
    expect(out.over.map((x) => x.id)).toEqual(['b']);
  });
});

describe('scoreFromFactors - graceful degrade (M4-D14)', () => {
  const F = (key: RankFactor['key'], weight: number, value: number | null, present: boolean): RankFactor => ({
    key,
    weight,
    value,
    present,
  });

  it('drops an absent factor from BOTH numerator and denominator (not zeroed)', () => {
    const withMargin = [
      F('urgency', 0.4, 0.8, true),
      F('margin', 0.3, 0.4, true),
      F('abc', 0.15, 1.0, true),
    ];
    const dropped = [
      F('urgency', 0.4, 0.8, true),
      F('margin', 0.3, null, false),
      F('abc', 0.15, 1.0, true),
    ];
    expect(scoreFromFactors(withMargin)).toBeCloseTo(0.694118, 5);
    expect(scoreFromFactors(dropped)).toBeCloseTo(0.854545, 5); // NOT 0.552941 (zeroed)
  });
});

describe('slider bounds derive from the run costed cash', () => {
  it('sliderMaxFor adds ~10% headroom rounded to RM 1,000', () => {
    const recs = [rec('a', 1, 6000), rec('b', 2, 4000), rec('c', 3, null)];
    expect(sliderMaxFor(recs)).toBe(11000); // ceil(10000*1.1/1000)*1000
  });

  it('the default budget is the COMPANY figure when there is one', () => {
    const recs = [rec('a', 1, 6000), rec('b', 2, 4000), rec('c', 3, null)];
    expect(defaultBudgetFor(recs, 5_000_000)).toBe(5_000_000);
  });

  it('with no company figure the default is the whole plan, not a fraction of it', () => {
    // It used to open at ~60% of the plan's own cost, which invents a limit nobody set and
    // files the rest under "Over budget".
    const recs = [rec('a', 1, 6000), rec('b', 2, 4000), rec('c', 3, null)];
    expect(defaultBudgetFor(recs)).toBe(10000);
    expect(defaultBudgetFor(recs, null)).toBe(10000);
    expect(defaultBudgetFor(recs, 0)).toBe(10000);
  });
});
