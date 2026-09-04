/**
 * S4 (`PLAN-scm-spo-planner-feedback-3sep.md`) - a taken-only entry must still land on the
 * schedule, and `bucketKeyFor` is the week function a picker matches its own rows against
 * (AC-D3), exported so it agrees with the matrix rather than reimplementing it.
 */
import { describe, it, expect } from 'vitest';
import { buildSpoScheduleMatrix, bucketKeyFor, type SpoMatrixEntry } from './spoScheduleMatrix';

function entry(over: Partial<SpoMatrixEntry<{ id: string }>> = {}): SpoMatrixEntry<{ id: string }> {
  return {
    row_key: 'item:ABC',
    row_label: 'ABC',
    row_description: null,
    shipment_line_id: 'sl-1',
    date: '2026-09-01',
    qty: 10,
    detail: { id: 'e1' },
    ...over,
  };
}

describe('buildSpoScheduleMatrix', () => {
  it('drops an entry with neither qty nor taken_qty', () => {
    const matrix = buildSpoScheduleMatrix([entry({ qty: 0, taken_qty: 0 })]);

    expect(matrix.rows).toHaveLength(0);
    expect(matrix.cells).toHaveLength(0);
  });

  it('a taken-only entry (qty 0, taken_qty > 0) still creates its row and cell (S5 groundwork)', () => {
    const matrix = buildSpoScheduleMatrix([entry({ qty: 0, taken_qty: 25 })]);

    expect(matrix.rows).toHaveLength(1);
    expect(matrix.cells).toHaveLength(1);
    expect(matrix.cells[0].qty).toBe(0);
    expect(matrix.cells[0].taken_qty).toBe(25);
  });

  it('sums taken_qty across entries the same way qty is summed', () => {
    const matrix = buildSpoScheduleMatrix([
      entry({ shipment_line_id: 'sl-1', qty: 10, taken_qty: 5 }),
      entry({ shipment_line_id: 'sl-1', qty: 6, taken_qty: 4 }),
    ]);

    expect(matrix.cells[0].qty).toBe(16);
    expect(matrix.cells[0].taken_qty).toBe(9);
  });

  it('an entry with no taken_qty at all sums as 0, not undefined', () => {
    const matrix = buildSpoScheduleMatrix([entry({ taken_qty: undefined })]);

    expect(matrix.cells[0].taken_qty).toBe(0);
  });

  it("a row carries the FIRST entry's shipment_line_id", () => {
    const matrix = buildSpoScheduleMatrix([
      entry({ shipment_line_id: 'sl-first', date: '2026-09-01' }),
      entry({ shipment_line_id: 'sl-second', date: '2026-09-15' }),
    ]);

    expect(matrix.rows[0].shipment_line_id).toBe('sl-first');
  });
});

describe('bucketKeyFor', () => {
  it('returns the same key for two dates in the same Monday-start week', () => {
    // 2026-09-01 (Tue) and 2026-09-03 (Thu) fall in the same week; a date the week AFTER
    // does not - proves the bucketing is weekly without hardcoding a specific ISO string
    // (`startOfWeekIso` reads through `toISOString`, so its own key shifts with the host's
    // timezone the same way `Date` always does - this only asserts the invariant, not a
    // stamp of the literal date).
    expect(bucketKeyFor('2026-09-01')).toBe(bucketKeyFor('2026-09-03'));
    expect(bucketKeyFor('2026-09-01')).not.toBe(bucketKeyFor('2026-09-08'));
  });

  it("returns 'no_date' for a null date", () => {
    expect(bucketKeyFor(null)).toBe('no_date');
  });

  it('agrees with the matrix\'s own bucketing for the same date', () => {
    const matrix = buildSpoScheduleMatrix([entry({ date: '2026-09-01' })]);

    expect(matrix.buckets[0].key).toBe(bucketKeyFor('2026-09-01'));
  });

  // S5: a real regression, not just the invariant above - `startOfWeekIso` used to format
  // through `toISOString().slice(0, 10)` after LOCAL date arithmetic, so on a UTC+8 host the
  // UTC conversion rolled every key (and the label built off it) back one further day, to
  // the SUNDAY before the Monday it meant. Prod showed "30 Aug 2026" / "13 Sept 2026" -
  // Sundays. These pin the literal so the bug cannot come back quietly.
  it('returns the Monday of the week (2026-09-03, a Thursday, buckets to 2026-08-31)', () => {
    expect(bucketKeyFor('2026-09-03')).toBe('2026-08-31');
  });

  it('labels the week by its Monday, never the prior Sunday', () => {
    const matrix = buildSpoScheduleMatrix([entry({ date: '2026-09-03' })]);

    expect(matrix.buckets[0].label).toBe('31 Aug 2026');
  });
});
