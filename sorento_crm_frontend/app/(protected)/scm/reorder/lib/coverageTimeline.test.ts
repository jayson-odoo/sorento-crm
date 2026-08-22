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
import {
  computedAtLabel,
  coverVerdict,
  dayLabel,
  shortfallWhen,
  supplySplit,
} from './coverageTimeline';
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
    expect(dayLabel('2026-07-01')).toBe('01/07/2026');
    expect(dayLabel('2026-08-25')).toBe('25/08/2026');
    // A date at the start of the month is the one that would slip backwards.
    expect(dayLabel('2027-01-01')).toBe('01/01/2027');
  });

  it('tolerates a full timestamp and returns empty for nothing', () => {
    expect(dayLabel('2026-08-03T09:12:00')).toBe('03/08/2026');
    expect(dayLabel(null)).toBe('');
  });
});

describe('computedAtLabel', () => {
  it('renders the wall-clock as written, adding no timezone offset', () => {
    expect(computedAtLabel('2026-08-03T09:12:00')).toBe('03/08/2026, 09:12');
    // 09:12 must not become 17:12.
    expect(computedAtLabel('2026-08-03T09:12:00')).not.toContain('17:12');
  });

  it('falls back to the date alone when there is no time part', () => {
    expect(computedAtLabel('2026-08-03')).toBe('03/08/2026');
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


/**
 * The verdict answers ONE question: is the committed demand covered from stock we
 * already hold. The reorder engine on the same screen answers a different one: is
 * stock above its reorder point. Both are legitimate and they disagree routinely,
 * so the verdict has to say which question it answered.
 *
 * The case that forced this, live on the dev database: B2155-NL-BLUE opens at 10,831
 * against a reorder point of 12,369.66. Committed demand of 7,646 IS covered, so the
 * panel said "existing stock covers it" - sitting beside a grid row recommending a
 * buy of 18,551, with a 1,539 deficit against the reorder point printed two lines
 * above. A planner reading "covers it" ignores a real replenishment signal.
 */
describe('coverVerdict', () => {
  it('names the pool when committed demand is covered and stock is above the floor', () => {
    const v = coverVerdict(true, 0, 'BRW', null);
    expect(v.tone).toBe('stock');
    expect(v.headline).toBe('Use the pool (BRW)');
    expect(v.note).toBeNull();
  });

  it('still says buy when the demand itself is short', () => {
    const v = coverVerdict(false, 4056, 'BRW', { at: '2026-07-01', qty: 4056, ref: 'SO1', label: '' });
    expect(v.tone).toBe('buy');
    expect(v.headline).toBe('Buy 4,056');
  });

  it('keeps a fractional buy quantity fractional', () => {
    // `buy_qty` is the timeline's peak deficit: floor minus balance, rounded to 4 places
    // on the server. Both sides of that subtraction can be fractional (a reorder level of
    // 49.33, a part-delivered order line), so rounding it here would quietly restate the
    // engine's answer on the one line the planner acts on.
    expect(coverVerdict(false, 12.5, 'BRW').headline).toBe('Buy 12.5');
    expect(coverVerdict(false, 0.25, 'BRW').headline).toBe('Buy 0.25');
  });

  it('writes a whole buy quantity without decimal padding', () => {
    expect(coverVerdict(false, 300, 'BRW').headline).toBe('Buy 300');
  });

  it('qualifies the verdict when the demand is covered but stock is below the floor', () => {
    const v = coverVerdict(true, 0, 'BRW', {
      at: null,
      qty: 1538.6555,
      ref: '',
      label: 'opening on hand',
    });
    expect(v.tone).toBe('stock');
    // The scope of the claim is stated, so it cannot be read as "nothing to do".
    expect(v.headline).toContain('Committed demand is covered');
    // And the other question is answered too, with its number.
    expect(v.note).toContain('1,539');
    expect(v.note).toContain('reorder point');
  });

  it('says covered rather than naming a pool when there is no pool location', () => {
    expect(coverVerdict(true, 0, '', null).headline).toBe('Use existing stock');
  });
});


describe('shortfallWhen', () => {
  it('names the date when an event caused the shortfall', () => {
    expect(shortfallWhen('2026-08-03')).toBe('on 03/08/2026');
  });

  it('says today when the opening balance is already under the floor', () => {
    // The server sends `at: null` because no event caused it and the opening balance
    // carries no date. Rendered through the dated phrasing this left "Short 1,539 on"
    // dangling on screen.
    expect(shortfallWhen(null)).toBe('today');
  });
});
