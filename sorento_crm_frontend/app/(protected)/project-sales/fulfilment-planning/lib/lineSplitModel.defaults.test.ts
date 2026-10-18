/**
 * OI-LINE-SPLIT owner round 2 (AC-A5 "Pending change default"): "+ Split" on a line that is
 * not split yet and has a pending change starts NEW QTY @ NEW DATE on its own line plus the
 * rest @ base date on New line. No pending change, or an already split line: unchanged.
 */
import { describe, expect, it } from 'vitest';
import * as m from './lineSplitModel';

type Line = Parameters<typeof m.splitsOf>[0];

const mk = (
  no: number,
  baseQty: number,
  baseDate: string,
  newQty: number | null,
  newDate: string | null,
  extra: Partial<Line> = {},
): Line =>
  ({
    lineId: `l${no}`,
    lineNo: no,
    itemCode: 'CSK14B',
    location: 'BRW-BB',
    baseQty,
    baseDate,
    nowQty: newQty ?? baseQty,
    nowDate: newDate ?? baseDate,
    newQty,
    newDate,
    pendingChange: newQty != null || newDate != null,
    splits: [],
    ...extra,
  }) as Line;

const rows = (lines: Line[], lineId: string) => {
  const r = m.addSplit(lines, lineId);
  const line = r.lines.find((l) => l.lineId === lineId)!;
  return { r, splits: line.splits, line };
};
const shape = (s: { qty: number; deliveryDate: string | null; sitsOnLineId: string | null }) => [
  s.qty,
  s.deliveryDate,
  s.sitsOnLineId,
];

describe('addSplit on a pending, unsplit line', () => {
  it('line 480: 417 @ 2026-10-20, new 14 @ 2026-09-20 -> 14 @ new date own line, 403 @ base date New line', () => {
    const { r, splits } = rows([mk(480, 417, '2026-10-20', 14, '2026-09-20')], 'l480');
    expect(splits.map(shape)).toEqual([
      [14, '2026-09-20', 'l480'],
      [403, '2026-10-20', null],
    ]);
    expect(r.id).toBe(splits[1].id);
  });

  it('line 752: qty above base is capped at base, the New line gets 0', () => {
    const { r, splits } = rows([mk(752, 504, '2026-12-20', 649, '2027-01-02')], 'l752');
    expect(splits.map(shape)).toEqual([
      [504, '2027-01-02', 'l752'],
      [0, '2026-12-20', null],
    ]);
    expect(r.id).toBe(splits[1].id);
  });

  it('date only: whole base qty on the new date, New line 0', () => {
    const { r, splits } = rows([mk(608, 192, '2026-11-20', null, '2027-01-02')], 'l608');
    expect(splits.map(shape)).toEqual([
      [192, '2027-01-02', 'l608'],
      [0, '2026-11-20', null],
    ]);
    expect(r.id).toBe(splits[1].id);
  });

  it('qty only down: new qty at the base date, the rest on New line', () => {
    const { r, splits } = rows([mk(480, 417, '2026-10-20', 14, null)], 'l480');
    expect(splits.map(shape)).toEqual([
      [14, '2026-10-20', 'l480'],
      [403, '2026-10-20', null],
    ]);
    expect(r.id).toBe(splits[1].id);
  });
});

describe('addSplit guards (unchanged behaviour)', () => {
  it('no pending change: base on own line plus 0 on New line', () => {
    const { r, splits } = rows([mk(480, 417, '2026-10-20', null, null)], 'l480');
    expect(splits.map(shape)).toEqual([
      [417, '2026-10-20', 'l480'],
      [0, '2026-10-20', null],
    ]);
    expect(r.id).toBe(splits[1].id);
  });

  it('an already split line with a pending change: keeps its split, appends what is left at the base date on New line', () => {
    const line = mk(480, 417, '2026-10-20', 14, '2026-09-20', {
      splits: [
        {
          id: 's1',
          qty: 100,
          deliveryDate: '2026-11-01',
          isCancel: false,
          sitsOnLineId: 'l480',
          remark: '',
        },
      ],
    });
    const { r, splits } = rows([line], 'l480');
    expect(splits).toHaveLength(2);
    expect(splits[0]).toEqual(line.splits[0]);
    expect(shape(splits[1])).toEqual([317, '2026-10-20', null]);
    expect(r.id).toBe(splits[1].id);
  });

  it('a line that reads REMAIN with one plain own split (edited and put back) still gets the pending default', () => {
    const line = mk(480, 417, '2026-10-20', 14, '2026-09-20', {
      splits: [
        {
          id: m.implicitSplitId('l480'),
          qty: 417,
          deliveryDate: '2026-10-20',
          isCancel: false,
          sitsOnLineId: 'l480',
          remark: '',
        },
      ],
    });
    const { r, splits } = rows([line], 'l480');
    expect(splits.map(shape)).toEqual([
      [14, '2026-09-20', 'l480'],
      [403, '2026-10-20', null],
    ]);
    expect(r.id).toBe(splits[1].id);
  });

  it('a base-0 (added) line with a new qty never gets a row without an id', () => {
    const { r, splits } = rows([mk(900, 0, '2026-10-20', 5, null)], 'l900');
    expect(splits.every((s) => typeof s.id === 'string' && s.id.length > 0)).toBe(true);
    expect(r.id).toBeTruthy();
  });

  it('keeps the stored own split id and remark when the pending default rewrites its qty and date', () => {
    const line = mk(480, 417, '2026-10-20', 14, '2026-09-20', {
      splits: [
        {
          id: 's1',
          qty: 417,
          deliveryDate: '2026-10-20',
          isCancel: false,
          sitsOnLineId: 'l480',
          remark: 'hold',
        },
      ],
    });
    const { r, splits } = rows([line], 'l480');
    expect(splits).toHaveLength(2);
    expect(splits[0].id).toBe('s1');
    expect(splits[0].remark).toBe('hold');
    expect(shape(splits[0])).toEqual([14, '2026-09-20', 'l480']);
    expect(shape(splits[1])).toEqual([403, '2026-10-20', null]);
    expect(splits[1].id).not.toBe('s1');
    expect(r.id).toBe(splits[1].id);
  });

  it('does not mutate the input lines', () => {
    const lines = [mk(480, 417, '2026-10-20', 14, '2026-09-20')];
    const before = structuredClone(lines);
    m.addSplit(lines, 'l480');
    expect(lines).toEqual(before);
  });
});
