/**
 * Margin and discontinue verdicts (2026-08-11 markup).
 *
 * Pinned hardest: a thin margin alone never suggests discontinuing a product that still
 * sells, an unknown side never renders as a number, and every factor travels with its
 * figure so the verdict can be argued with.
 */
import { describe, expect, it } from 'vitest';
import { discontinueAdvice, marginOf, type ProductEconomics } from './productHealth';
import type { TrajectoryEntry } from './trajectory';

const THRESHOLDS = { margin_floor_pct: 15, dead_turnover_months: 6 };

const econ = (over: Partial<ProductEconomics> = {}): ProductEconomics => ({
  product_id: 'p1',
  avg_sell_price: 100,
  sell_source: 'orders',
  sold_qty: 240,
  on_hand: 40,
  avg_monthly_out: 20,
  turnover_months: 2,
  no_movement: false,
  ...over,
});

const trend = (verdict: TrajectoryEntry['verdict']): TrajectoryEntry => ({
  verdict, recent_qty: 0, previous_qty: 0, change_pct: null, year_ago_qty: null,
  year_change_pct: null, window_months: 12, months: [], customers: [], agents: [],
  agents_available: false,
});

describe('marginOf', () => {
  it('healthy when the sell clears the floor over the cost', () => {
    expect(marginOf(60, econ(), 15)).toMatchObject({ tone: 'healthy', pct: 40 });
  });

  it('thin below the floor, negative below cost', () => {
    expect(marginOf(90, econ(), 15).tone).toBe('thin');
    expect(marginOf(120, econ(), 15).tone).toBe('negative');
  });

  it('unknown when either side is missing - never a guess', () => {
    expect(marginOf(null, econ(), 15).tone).toBe('unknown');
    expect(marginOf(60, econ({ avg_sell_price: null, sell_source: null }), 15).tone).toBe('unknown');
    // Zero cost is the zero-price problem, not a 100% margin.
    expect(marginOf(0, econ(), 15).tone).toBe('unknown');
  });
});

describe('discontinueAdvice', () => {
  it('suggests discontinuing only when demand dies AND the stock stops moving', () => {
    const out = discontinueAdvice(
      econ({ turnover_months: 14, sold_qty: 6, avg_monthly_out: 0.5 }),
      marginOf(90, econ(), 15),
      trend('falling'),
      THRESHOLDS,
    );
    expect(out?.consider).toBe(true);
  });

  it('a hot seller with a thin margin is a pricing conversation, not a discontinuation', () => {
    const out = discontinueAdvice(econ(), marginOf(90, econ(), 15), trend('rising'), THRESHOLDS);
    expect(out?.consider).toBe(false);
  });

  it('dead stock with no movement at all still qualifies', () => {
    const dead = econ({ no_movement: true, avg_monthly_out: 0, turnover_months: null,
                        sold_qty: 0, on_hand: 25 });
    const out = discontinueAdvice(dead, marginOf(60, dead, 15), undefined, THRESHOLDS);
    expect(out?.consider).toBe(true);
    expect(out?.factors.join(' ')).toContain('nothing left this product');
  });

  it('carries every factor with its number, verdict or not', () => {
    const out = discontinueAdvice(econ(), marginOf(60, econ(), 15), trend('rising'), THRESHOLDS);
    const text = out?.factors.join(' ') ?? '';
    expect(text).toContain('240 sold');
    expect(text).toContain('2 months of stock');
    expect(text).toContain('Margin: 40%');
    expect(text).toContain('Cash tied up: 2,400');
  });

  it('no economics, no opinion', () => {
    expect(discontinueAdvice(undefined, marginOf(60, undefined, 15), undefined, THRESHOLDS)).toBeNull();
  });
});
