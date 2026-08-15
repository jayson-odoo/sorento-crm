/**
 * `previousCivilDay` - S7b Phase 2c follow-up gate, item 1.
 *
 * Pins the class of date-arithmetic bug this helper exists to avoid: month
 * rollover, YEAR rollover, leap day, and the non-leap "century-ish" neighbour
 * that a hand-rolled "subtract one" often gets wrong. Also asserts the
 * computation does not shift under a non-UTC process timezone, matching the
 * house rule already pinned for `formatCivilDate` in `warrantyLabels.test.ts`
 * (civil dates must never move because the machine running the test is west
 * of Greenwich).
 *
 * AC-P26: this is exactly the arithmetic the Supersede dialog performs on the
 * incumbent's closing date, so a regression here silently mis-dates every
 * supersede confirmation.
 */
import { describe, it, expect } from 'vitest';
import { previousCivilDay } from './warrantyLabels';

describe('previousCivilDay', () => {
  it('steps back across a month boundary', () => {
    expect(previousCivilDay('2026-09-01')).toBe('2026-08-31');
  });

  it('steps back across a YEAR boundary', () => {
    expect(previousCivilDay('2026-01-01')).toBe('2025-12-31');
  });

  it('steps back onto leap day in a leap year', () => {
    expect(previousCivilDay('2028-03-01')).toBe('2028-02-29');
  });

  it('steps back to the 28th in a non-leap year (no phantom 29th)', () => {
    expect(previousCivilDay('2027-03-01')).toBe('2027-02-28');
  });

  it('returns null for a falsy or malformed input', () => {
    expect(previousCivilDay(null)).toBeNull();
    expect(previousCivilDay(undefined)).toBeNull();
    expect(previousCivilDay('not-a-date')).toBeNull();
    expect(previousCivilDay('')).toBeNull();
  });

  it('an ordinary mid-month day just steps back by one', () => {
    expect(previousCivilDay('2026-06-15')).toBe('2026-06-14');
  });

  it('does not shift under a non-UTC process TZ (America/Los_Angeles)', () => {
    const original = process.env.TZ;
    process.env.TZ = 'America/Los_Angeles';
    try {
      expect(previousCivilDay('2026-09-01')).toBe('2026-08-31');
      expect(previousCivilDay('2026-01-01')).toBe('2025-12-31');
      expect(previousCivilDay('2028-03-01')).toBe('2028-02-29');
    } finally {
      process.env.TZ = original;
    }
  });
});
