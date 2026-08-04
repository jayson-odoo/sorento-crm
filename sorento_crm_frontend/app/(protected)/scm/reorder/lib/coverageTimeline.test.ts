/**
 * Coverage Timeline presentation helpers - the three that carry a real trap.
 *
 *  - `dayLabel` must not move a date. A plain calendar date run through a
 *    local-timezone formatter shifts a day west of Greenwich, which would reorder
 *    the timeline against the balances the server accumulated.
 *  - `computedAtLabel` must NOT convert. `computed_at` is already naive Malaysia
 *    wall-clock, so treating it as UTC would add eight hours.
 *  - `supplySplit` must read the rows rather than recompute anything, and must keep
 *    on-order separate from in-transit: only the on-order half is still negotiable.
 */
import { describe, it, expect } from 'vitest';
import { computedAtLabel, dayLabel, supplySplit } from './coverageTimeline';
import type { CoverageRow } from '../types/coverage.types';

function row(over: Partial<CoverageRow['event']>, balance = 0): CoverageRow {
  return {
    event: {
      at: '2026-08-03',
      qty: 0,
      kind: 'supply',
      ref: '',
      label: '',
      location: '',
      supply_stage: null,
      ...over,
    },
    balance,
  };
}

describe('dayLabel', () => {
  it('renders a plain calendar date without shifting it', () => {
    expect(dayLabel('2026-07-01')).toBe('01 Jul 2026');
    expect(dayLabel('2026-08-25')).toBe('25 Aug 2026');
    // A date at the start of the month is the one that would slip backwards.
    expect(dayLabel('2027-01-01')).toBe('01 Jan 2027');
  });

  it('tolerates a full timestamp and returns empty for nothing', () => {
    expect(dayLabel('2026-08-03T09:12:00')).toBe('03 Aug 2026');
    expect(dayLabel(null)).toBe('');
  });
});

describe('computedAtLabel', () => {
  it('renders the wall-clock as written, adding no timezone offset', () => {
    expect(computedAtLabel('2026-08-03T09:12:00')).toBe('03 Aug 2026, 09:12');
    // 09:12 must not become 17:12.
    expect(computedAtLabel('2026-08-03T09:12:00')).not.toContain('17:12');
  });

  it('falls back to the date alone when there is no time part', () => {
    expect(computedAtLabel('2026-08-03')).toBe('03 Aug 2026');
    expect(computedAtLabel(null)).toBe('');
  });
});

describe('supplySplit', () => {
  it('keeps on-order and in-transit separate', () => {
    const split = supplySplit([
      row({ kind: 'opening', at: null, qty: 0 }),
      row({ kind: 'demand', qty: -135, supply_stage: null }),
      row({ qty: 200, supply_stage: 'on_order' }),
      row({ qty: 150, supply_stage: 'on_order' }),
      row({ qty: 400, supply_stage: 'in_transit' }),
    ]);
    expect(split).toEqual({ on_order: 350, in_transit: 400 });
  });

  it('counts a stageless supply row as on order, never as already shipped', () => {
    // Optimism is the wrong default: treating unknown supply as loaded would say the
    // stock can no longer be re-dated when it can.
    expect(supplySplit([row({ qty: 90, supply_stage: null })])).toEqual({
      on_order: 90,
      in_transit: 0,
    });
  });

  it('is zero when there is no supply at all', () => {
    expect(supplySplit([row({ kind: 'demand', qty: -20 })])).toEqual({
      on_order: 0,
      in_transit: 0,
    });
  });
});
