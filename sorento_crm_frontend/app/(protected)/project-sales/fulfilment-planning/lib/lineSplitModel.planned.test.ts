/**
 * OI-LINE-SPLIT v4 crew audit: the PLANNED date of a line (UAC A7). A line carries one planned
 * date: (a) its own non-cancel split that stays on it, else (b) another line's split already
 * sitting on it, else (c) its AutoCount date (current, else base).
 */
import { describe, expect, it } from 'vitest';
import * as m from './lineSplitModel';

type Line = Parameters<typeof m.splitsOf>[0];
type Split = Line['splits'][number];

const mk = (id: string, no: number, qty: number, date: string, opts: Partial<Line> = {}): Line =>
  ({
    lineId: id, lineNo: no, itemCode: 'CSK14B', location: 'BRW-BB', baseQty: qty, baseDate: date,
    nowQty: qty, nowDate: date, pendingChange: false, splits: [], ...opts,
  }) as Line;
const sp = (id: string, qty: number, date: string | null, on: string | null, x: Partial<Split> = {}): Split =>
  ({ id, qty, deliveryDate: date, isCancel: false, sitsOnLineId: on, remark: '', ...x });
const by = (lines: Line[], id: string) => lines.find((l) => l.lineId === id)!;

describe('plannedDateOf', () => {
  it('(a) a split line: the date of its own split that stays on it', () => {
    const lines = [
      mk('a', 752, 504, '2026-12-20', {
        nowQty: 649, nowDate: '2027-01-02',
        splits: [sp('x', 14, '2026-09-20', 'a'), sp('y', 490, '2027-03-01', 'z')],
      }),
      mk('z', 900, 5, '2026-01-01'),
    ];
    expect(m.plannedDateOf(lines, 'a')).toBe('2026-09-20');
  });

  it('(a) wins over another line split sitting on it', () => {
    const lines = [
      mk('a', 752, 20, '2026-12-20', { splits: [sp('x', 20, '2026-09-20', 'a')] }),
      mk('b', 480, 10, '2026-10-20', { splits: [sp('y', 10, '2026-11-11', 'a')] }),
    ];
    expect(m.plannedDateOf(lines, 'a')).toBe('2026-09-20');
  });

  it('a cancel split on its own line is not the planned date', () => {
    const lines = [
      mk('a', 752, 20, '2026-12-20', {
        nowDate: '2027-01-02',
        splits: [sp('x', 20, null, 'a', { isCancel: true })],
      }),
    ];
    expect(m.plannedDateOf(lines, 'a')).toBe('2027-01-02');
  });

  it('(b) an unsplit line takes the date of another line split already sitting on it', () => {
    const lines = [
      mk('a', 608, 192, '2026-11-20'),
      mk('b', 480, 417, '2026-10-20', {
        splits: [sp('x', 14, '2026-10-20', 'b'), sp('y', 403, '2026-12-01', 'a')],
      }),
    ];
    expect(m.plannedDateOf(lines, 'a')).toBe('2026-12-01');
  });

  it('(b) a split line whose own splits all moved away also follows what sits on it', () => {
    const lines = [
      mk('a', 608, 10, '2026-11-20', { splits: [sp('s', 10, '2026-12-05', 'c')] }),
      mk('b', 480, 417, '2026-10-20', { splits: [sp('y', 417, '2026-12-01', 'a')] }),
      mk('c', 700, 1, '2026-01-01'),
    ];
    expect(m.plannedDateOf(lines, 'a')).toBe('2026-12-01');
  });

  it('(c) otherwise AutoCount\'s current date, else the base date', () => {
    const lines = [
      mk('a', 752, 504, '2026-12-20', { nowDate: '2027-01-02' }),
      mk('b', 608, 192, '2026-11-20', { nowDate: null }),
    ];
    expect(m.plannedDateOf(lines, 'a')).toBe('2027-01-02');
    expect(m.plannedDateOf(lines, 'b')).toBe('2026-11-20');
  });

  it('is null for an unknown line, and targetDateOf is unchanged', () => {
    const lines = [mk('a', 752, 504, '2026-12-20', { nowDate: '2027-01-02' })];
    expect(m.plannedDateOf(lines, 'nope')).toBeNull();
    expect(m.targetDateOf(lines[0])).toBe('2027-01-02');
  });
});

describe('plannedDateOf rule (b) is order-free: the EARLIEST foreign date', () => {
  const build = () => [
    mk('p', 480, 100, '2026-10-20', { splits: [sp('x', 100, '2026-12-05', 'l')] }),
    mk('q', 752, 100, '2026-10-20', { splits: [sp('y', 100, '2026-11-25', 'l')] }),
    mk('l', 608, 192, '2026-11-20', { nowDate: '2027-02-02' }),
  ];

  it('takes 2026-11-25 although the 12-05 split comes first in the array', () => {
    expect(m.plannedDateOf(build(), 'l')).toBe('2026-11-25');
  });

  it('gives the same answer with the array reversed', () => {
    expect(m.plannedDateOf([...build()].reverse(), 'l')).toBe('2026-11-25');
  });

  it('considers every split of a foreign line, not just its first', () => {
    const lines = [
      mk('p', 480, 200, '2026-10-20', {
        splits: [sp('x', 100, '2026-12-05', 'l'), sp('x2', 100, '2026-11-01', 'l')],
      }),
      mk('l', 608, 192, '2026-11-20'),
    ];
    expect(m.plannedDateOf(lines, 'l')).toBe('2026-11-01');
  });
});

describe('plannedDateOf ignores a line that reads REMAIN for rule (a)', () => {
  it('a remark-only line (one split equal to base, own line and date) uses its AutoCount date', () => {
    const lines = [
      mk('a', 752, 504, '2026-12-20', {
        nowDate: '2027-01-02',
        splits: [sp('x', 504, '2026-12-20', 'a', { remark: 'hold' })],
      }),
    ];
    expect(m.readsRemain(lines[0])).toBe(true);
    expect(m.plannedDateOf(lines, 'a')).toBe('2027-01-02');
  });
});
