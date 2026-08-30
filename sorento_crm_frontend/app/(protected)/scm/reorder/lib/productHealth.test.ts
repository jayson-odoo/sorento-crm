/**
 * Movement health, and the MOQ pump-up beside it.
 *
 * Pinned hardest (AC-R12): the four classes read exactly as the captain named them, no
 * margin figure survives anywhere, and every factor travels with its count so the verdict
 * can be argued with.
 */
import { describe, expect, it } from 'vitest';
import { MOVEMENT_SORT, healthVerdict, moqGap, type ProductEconomics } from './productHealth';

const econ = (over: Partial<ProductEconomics> = {}): ProductEconomics => ({
  product_id: 'p1',
  avg_sell_price: 100,
  sell_source: 'orders',
  sold_qty: 240,
  on_hand: 40,
  avg_monthly_out: 20,
  turnover_months: 2,
  no_movement: false,
  lifecycle_decision: null,
  lifecycle_decided_at: null,
  sold_recent_qty: 50,
  bought_recent_qty: 30,
  movement_class: 'fast_moving',
  ...over,
});

describe('healthVerdict', () => {
  it('sold and bought reads Fast moving, and asks for nothing', () => {
    const v = healthVerdict(econ())!;
    expect(v.label).toBe('Fast moving');
    expect(v.tone).toBe('success');
    expect(v.consider).toBe(false);
    expect(v.suggestion).toBeNull();
  });

  it('sold with nothing bought reads Slow moving', () => {
    const v = healthVerdict(econ({ bought_recent_qty: 0, movement_class: 'slow_moving' }))!;
    expect(v.label).toBe('Slow moving');
    expect(v.consider).toBe(false);
  });

  it('neither, with stock still on hand, reads Dead and says what to consider', () => {
    const v = healthVerdict(
      econ({ sold_recent_qty: 0, bought_recent_qty: 0, on_hand: 40, movement_class: 'dead' }),
    )!;
    expect(v.label).toBe('Dead');
    expect(v.consider).toBe(true);
    expect(v.suggestion).toBe('Consider discontinuing');
  });

  it('neither and nothing on hand reads No history, which is not a verdict on the product', () => {
    const v = healthVerdict(
      econ({ sold_recent_qty: 0, bought_recent_qty: 0, on_hand: 0, movement_class: 'no_history' }),
    )!;
    expect(v.label).toBe('No history');
    expect(v.consider).toBe(false);
    expect(v.suggestion).toBeNull();
  });

  it('every factor travels with its count, and names its own window', () => {
    const v = healthVerdict(econ(), { sold_window_months: 3, bought_window_months: 6 })!;
    expect(v.factors).toEqual([
      'Sold: 50 delivered in the last 3 months.',
      'Bought: 30 received in the last 6 months.',
      'On hand: 40 in the pool.',
    ]);
  });

  it('carries no margin figure at all', () => {
    const v = healthVerdict(econ())!;
    expect(v.factors.join(' ')).not.toMatch(/margin/i);
  });

  it('no economics is no verdict, never a default one', () => {
    expect(healthVerdict(undefined)).toBeNull();
  });
});

describe('MOVEMENT_SORT', () => {
  it('floats the rows the buyer should re-question to the top of the column', () => {
    expect(
      (['fast_moving', 'dead', 'no_history', 'slow_moving'] as const)
        .slice()
        .sort((a, b) => MOVEMENT_SORT[a] - MOVEMENT_SORT[b]),
    ).toEqual(['dead', 'no_history', 'slow_moving', 'fast_moving']);
  });
});

describe('moqGap - the pump-up, with its sell-through odds', () => {
  it('names the extra and how fast it clears at the current pace', () => {
    // Need 20, MOQ 100 -> 80 extra at 20/month = 4 months: clears.
    const gap = moqGap(20, 100, 100, econ(), 6);
    expect(gap).toMatchObject({ extra: 80, months_to_clear: 4, verdict: 'clears' });
    expect(gap?.sentence).toContain('clears in about 4 months');
  });

  it('suggests a promotion or a lower MOQ when the extra outlives the turnover line', () => {
    // 80 extra at 5/month = 16 months, line is 6.
    const gap = moqGap(20, 100, 100, econ({ avg_monthly_out: 5 }), 6);
    expect(gap?.verdict).toBe('slow');
    expect(gap?.sentence).toMatch(/promotion|negotiate/);
  });

  it('says so when nothing sells to clear the extra', () => {
    const gap = moqGap(20, 100, 100, econ({ avg_monthly_out: 0, no_movement: true }), 6);
    expect(gap?.verdict).toBe('no_pace');
    expect(gap?.months_to_clear).toBeNull();
  });

  it('no gap when the need already reaches the MOQ, or no MOQ is on file', () => {
    expect(moqGap(150, 100, 150, econ(), 6)).toBeNull();
    expect(moqGap(20, null, 20, econ(), 6)).toBeNull();
    expect(moqGap(0, 100, 0, econ(), 6)).toBeNull();
  });
});
