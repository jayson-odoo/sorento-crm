import { describe, it, expect } from 'vitest';
import type { RankFactor, ReorderRecommendation } from '../types/reorder.types';
import {
  computeFunding,
  defaultBudgetFor,
  scoreFromFactors,
  sliderMaxFor,
} from './reorderCashAllocation';

/** Minimal buy rec for allocator tests — only the fields the allocator reads. */
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

describe('computeFunding — greedy skip-overflow (M4-D3)', () => {
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

describe('scoreFromFactors — graceful degrade (M4-D14)', () => {
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
  it('sliderMaxFor adds ~10% headroom rounded to RM 1,000; defaultBudgetFor ≈ 60%', () => {
    const recs = [rec('a', 1, 6000), rec('b', 2, 4000), rec('c', 3, null)];
    expect(sliderMaxFor(recs)).toBe(11000); // ceil(10000*1.1/1000)*1000
    expect(defaultBudgetFor(recs)).toBe(6000); // round(10000*0.6/500)*500
  });
});
