/**
 * `generatePeriods` (S1-19): the same golden table as
 * `sorento_crm_backend/tests/test_sales_targets_s1.py::test_generate_periods_golden` (16.2), so
 * the FE hint in SetTargetModal (period count + last period's dates, S1-25) can never disagree
 * with what the API actually creates.
 *
 * Exported name/signature the coder must match (stated so both sides land on the same contract):
 *   `generatePeriods(start: string, end: string, splitEvery: number | null, splitUnit: 'day' | 'week' | 'month' | null): { start: string; end: string }[]`
 * Dates are plain `YYYY-MM-DD` strings in and out - no `Date` objects, so callers never fight
 * timezone-shifted midnights.
 */
import { describe, expect, it } from 'vitest';
import { generatePeriods } from './periods';

describe('generatePeriods', () => {
  it('no split: one period for the whole range', () => {
    expect(generatePeriods('2026-10-01', '2026-12-15', null, null)).toEqual([
      { start: '2026-10-01', end: '2026-12-15' },
    ]);
  });

  it('monthly: 1-31 Oct, 1-30 Nov, 1-15 Dec', () => {
    expect(generatePeriods('2026-10-01', '2026-12-15', 1, 'month')).toEqual([
      { start: '2026-10-01', end: '2026-10-31' },
      { start: '2026-11-01', end: '2026-11-30' },
      { start: '2026-12-01', end: '2026-12-15' },
    ]);
  });

  it('every 2 weeks: five 14-day periods then a short tail', () => {
    expect(generatePeriods('2026-10-01', '2026-12-15', 2, 'week')).toEqual([
      { start: '2026-10-01', end: '2026-10-14' },
      { start: '2026-10-15', end: '2026-10-28' },
      { start: '2026-10-29', end: '2026-11-11' },
      { start: '2026-11-12', end: '2026-11-25' },
      { start: '2026-11-26', end: '2026-12-09' },
      { start: '2026-12-10', end: '2026-12-15' },
    ]);
  });

  it('a start on the 31st, monthly: steps to the shorter month\'s last day', () => {
    expect(generatePeriods('2027-01-31', '2027-03-30', 1, 'month')).toEqual([
      { start: '2027-01-31', end: '2027-02-27' },
      { start: '2027-02-28', end: '2027-03-30' },
    ]);
  });

  it('every 2 weeks landing exactly on the end date: five periods, no short tail', () => {
    expect(generatePeriods('2026-10-01', '2026-12-09', 2, 'week')).toEqual([
      { start: '2026-10-01', end: '2026-10-14' },
      { start: '2026-10-15', end: '2026-10-28' },
      { start: '2026-10-29', end: '2026-11-11' },
      { start: '2026-11-12', end: '2026-11-25' },
      { start: '2026-11-26', end: '2026-12-09' },
    ]);
  });

  it('a one-day range is valid', () => {
    expect(generatePeriods('2026-10-01', '2026-10-01', null, null)).toEqual([
      { start: '2026-10-01', end: '2026-10-01' },
    ]);
  });

  it('caps at 104 periods and throws past it', () => {
    // 1 Jan 2026 to 29 Dec 2027 weekly = 728 days / 7 = exactly 104: fine.
    expect(generatePeriods('2026-01-01', '2027-12-29', 1, 'week')).toHaveLength(104);
    // Two days later: 105, over the cap.
    expect(() => generatePeriods('2026-01-01', '2027-12-31', 1, 'week')).toThrow();
  });

  it('end before start throws', () => {
    expect(() => generatePeriods('2026-12-15', '2026-10-01', null, null)).toThrow();
  });
});
