/**
 * Consequence maths for the order-quantity decision (AC-C2.7).
 *
 * Two rules are pinned here:
 *
 *  - A chosen quantity ABOVE the shortfall produces a STATEMENT, not a warning:
 *    the shortfall is fully covered, the excess is reported as spare with the
 *    pool it lands in, and nothing in the returned shape marks it as invalid.
 *  - A figure with no input behind it is NAMED, never zeroed. Months of cover
 *    needs a demand statistic (present for 62% of the book) and container volume
 *    needs recorded dimensions (16%), so both are nullable and carry the name of
 *    the missing input instead of a 0 that reads as "already out of stock" and
 *    "no space needed".
 *
 * The real fixtures from `summaryOrderMockStore` are used rather than hand-typed
 * numbers, so a fixture drifting from the ACs fails here too.
 */
import { describe, it, expect } from 'vitest';
import { SUMMARY_ORDER_FIXTURES } from './summaryOrderMockStore';
import { orderQuantityImpact, positionAfterBuy, fmtCost, fmtVariance } from './orderImpact';

const BOTH = SUMMARY_ORDER_FIXTURES.row('B2155-NL-BLUE'); // demand rate + dimensions
const COVER_ONLY = SUMMARY_ORDER_FIXTURES.row('SRTWT7408'); // demand rate, no dimensions
const NEITHER = SUMMARY_ORDER_FIXTURES.row('SRTBS4832'); // neither

const GDS = SUMMARY_ORDER_FIXTURES.suppliers('B2155-NL-BLUE').candidates[0];

describe('orderQuantityImpact - a quantity above the shortfall is not an error (AC-C2.7)', () => {
  it('reports the shortfall fully covered and the excess as spare, with where it lands', () => {
    const impact = orderQuantityImpact(BOTH, 600, GDS);
    expect(impact.shortfall).toBe(278);
    expect(impact.shortfall_covered).toBe(278);
    expect(impact.shortfall_remaining).toBe(0);
    expect(impact.spare_qty).toBe(322);
    expect(impact.spare_lands_at).toBe('BRW');
  });

  it('reports a quantity BELOW the shortfall as partly covered, still without an error flag', () => {
    const impact = orderQuantityImpact(BOTH, 100, GDS);
    expect(impact.shortfall_covered).toBe(100);
    expect(impact.shortfall_remaining).toBe(178);
    expect(impact.spare_qty).toBe(0);
    // Nothing in the shape says "invalid" - the caller has no warning to render.
    expect(Object.keys(impact)).not.toContain('error');
  });

  it('states the cash committed at the chosen supplier ex-works cost, in their currency', () => {
    const impact = orderQuantityImpact(BOTH, 600, GDS);
    expect(impact.cash_committed.value).toBeCloseTo(600 * 128.4, 6);
    expect(impact.currency).toBe('CNY');
    expect(fmtCost(impact.cash_committed.value, impact.currency)).toBe('CNY 77,040.00');
  });

  it('states the container volume added from the recorded unit volume', () => {
    const impact = orderQuantityImpact(BOTH, 600, GDS);
    expect(impact.volume_cbm.value).toBeCloseTo(600 * 0.082, 6);
  });

  it('quotes months of cover against the position AFTER the buy, not before it', () => {
    const impact = orderQuantityImpact(BOTH, 600, GDS);
    const position = positionAfterBuy(BOTH, 600);
    expect(position).toBe(96 + 120 + 200 + 600 - 480 - 186);
    expect(impact.months_of_cover.value).toBeCloseTo(position / (3.6 * 30), 6);
  });
});

describe('orderQuantityImpact - a missing input is named, never zeroed', () => {
  it('names the missing dimensions rather than printing a volume of 0', () => {
    const impact = orderQuantityImpact(COVER_ONLY, 200, GDS);
    expect(impact.volume_cbm.value).toBeNull();
    expect(impact.volume_cbm.missing).toBe('dimensions not recorded');
    // The cover figure IS derivable for this product, so it is still stated.
    expect(impact.months_of_cover.value).not.toBeNull();
  });

  it('names the missing demand rate rather than printing a cover of 0 months', () => {
    const impact = orderQuantityImpact(NEITHER, 100, GDS);
    expect(impact.months_of_cover.value).toBeNull();
    expect(impact.months_of_cover.missing).toBe('demand rate not recorded');
    expect(impact.volume_cbm.value).toBeNull();
    expect(impact.volume_cbm.missing).toBe('dimensions not recorded');
  });

  it('says no supplier is chosen yet rather than committing cash at an assumed cost', () => {
    const impact = orderQuantityImpact(BOTH, 600, null);
    expect(impact.cash_committed.value).toBeNull();
    expect(impact.cash_committed.missing).toBe('no supplier chosen yet');
    expect(impact.currency).toBeNull();
  });

  it('says the chosen supplier has no cost on record when that is the reason', () => {
    const uncosted = { ...GDS, last_po_cost: null };
    const impact = orderQuantityImpact(BOTH, 600, uncosted);
    expect(impact.cash_committed.value).toBeNull();
    expect(impact.cash_committed.missing).toBe('no cost on record for this supplier');
  });

  it('treats a zero demand rate as no rate at all, not as instant stock-out', () => {
    const impact = orderQuantityImpact({ ...BOTH, avg_daily_demand: 0 }, 600, GDS);
    expect(impact.months_of_cover.value).toBeNull();
    expect(impact.months_of_cover.missing).toBe('demand rate not recorded');
  });
});

describe('orderQuantityImpact - degenerate quantities', () => {
  it('treats an empty or negative quantity as nothing ordered, covering nothing', () => {
    const impact = orderQuantityImpact(BOTH, Number.NaN, GDS);
    expect(impact.shortfall_covered).toBe(0);
    expect(impact.shortfall_remaining).toBe(278);
    expect(impact.spare_qty).toBe(0);
    expect(impact.cash_committed.value).toBe(0);
  });
});

describe('cost formatting - ex-works in the supplier currency (AC-C3.4)', () => {
  it('never renders a CNY cost as RM', () => {
    expect(fmtCost(128.4, 'CNY')).toBe('CNY 128.40');
    expect(fmtCost(88, 'MYR')).toBe('MYR 88.00');
  });

  it('signs the ordered-to-incoming variance, so a reprice upward reads as +', () => {
    expect(fmtVariance(6.5, 'CNY')).toBe('+CNY 6.50');
    expect(fmtVariance(-1.5, 'CNY')).toBe('-CNY 1.50');
    expect(fmtVariance(0, 'CNY')).toBe('CNY 0.00');
  });
});
