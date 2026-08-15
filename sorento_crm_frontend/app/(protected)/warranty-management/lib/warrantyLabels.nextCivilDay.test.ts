/**
 * `nextCivilDay` - S7b Phase 2c follow-up gate, item 1 counterpart.
 *
 * Mirrors `warrantyLabels.previousCivilDay.test.ts`. Pins the class of
 * date-arithmetic bug this helper exists to avoid: month rollover, YEAR
 * rollover, leap day, and the non-leap "century-ish" neighbour that a
 * hand-rolled "add one" often gets wrong. Also asserts the computation does
 * not shift under a non-UTC process timezone, matching the house rule
 * already pinned for `formatCivilDate` in `warrantyLabels.test.ts` (civil
 * dates must never move because the machine running the test is west of
 * Greenwich).
 *
 * AC-P26: this is exactly the arithmetic the Supersede dialog performs to
 * compute the earliest date it may offer for a successor's start (the day
 * strictly after the incumbent's own `effective_from`), so a regression here
 * silently offers a date the backend refuses, or refuses one it would accept.
 */
import { describe, it, expect } from 'vitest';
import { nextCivilDay } from './warrantyLabels';

describe('nextCivilDay', () => {
  it('steps forward inside a month', () => {
    expect(nextCivilDay('2026-06-14')).toBe('2026-06-15');
  });

  it('steps forward across a month boundary', () => {
    expect(nextCivilDay('2026-01-31')).toBe('2026-02-01');
  });

  it('steps forward across a YEAR boundary', () => {
    expect(nextCivilDay('2025-12-31')).toBe('2026-01-01');
  });

  it('steps forward onto leap day in a leap year', () => {
    expect(nextCivilDay('2028-02-28')).toBe('2028-02-29');
  });

  it('steps forward off leap day into March', () => {
    expect(nextCivilDay('2028-02-29')).toBe('2028-03-01');
  });

  it('steps forward past the 28th in a non-leap year (no phantom 29th)', () => {
    expect(nextCivilDay('2027-02-28')).toBe('2027-03-01');
  });

  it('returns null for a falsy or malformed input', () => {
    expect(nextCivilDay(null)).toBeNull();
    expect(nextCivilDay(undefined)).toBeNull();
    expect(nextCivilDay('not-a-date')).toBeNull();
    expect(nextCivilDay('')).toBeNull();
  });

  it('does not shift under a non-UTC process TZ (America/Los_Angeles)', () => {
    const original = process.env.TZ;
    process.env.TZ = 'America/Los_Angeles';
    try {
      expect(nextCivilDay('2026-01-31')).toBe('2026-02-01');
      expect(nextCivilDay('2025-12-31')).toBe('2026-01-01');
      expect(nextCivilDay('2028-02-28')).toBe('2028-02-29');
    } finally {
      process.env.TZ = original;
    }
  });
});
