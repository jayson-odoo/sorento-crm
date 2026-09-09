/**
 * AC-S4.5 (PLAN-reorder-feedback-9sep.md, S4): one wording helper for the sales-order
 * window, used by the header tab, the plan-page subtitle and the plans list so all three
 * never say it three different ways.
 *
 * `describeWindow(start, end)` - both ISO `YYYY-MM-DD` strings or null/undefined:
 *   both set   -> "01/01/2025 to 31/10/2026"
 *   end only   -> "up to 31/10/2026"
 *   start only -> "from 01/01/2025"
 *   neither    -> "every open order"
 */
import { describe, expect, it } from 'vitest';
import { describeWindow } from './runListing';

describe('describeWindow (AC-S4.5)', () => {
  it('both dates set reads "X to Y"', () => {
    expect(describeWindow('2025-01-01', '2026-10-31')).toBe('01/01/2025 to 31/10/2026');
  });

  it('end only reads "up to Y"', () => {
    expect(describeWindow(null, '2026-10-31')).toBe('up to 31/10/2026');
  });

  it('start only reads "from X"', () => {
    expect(describeWindow('2025-01-01', null)).toBe('from 01/01/2025');
  });

  it('neither set reads "every open order"', () => {
    expect(describeWindow(null, null)).toBe('every open order');
    expect(describeWindow(undefined, undefined)).toBe('every open order');
  });

  it('empty strings read the same as null', () => {
    expect(describeWindow('', '')).toBe('every open order');
  });
});
