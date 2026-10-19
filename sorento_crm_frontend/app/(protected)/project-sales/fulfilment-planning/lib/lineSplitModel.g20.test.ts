/**
 * OI-LINE-SPLIT AC-G20 (model): the "N left" chip makes its own row, "+ Split" never makes a
 * qty-0 row. Lines model SO417636 CSK14B. Customer data is a placeholder.
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
    lineId: `L${no}`,
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

const owner = () => [
  mk(480, 417, '2026-10-20', 14, '2026-09-20'),
  mk(608, 192, '2026-11-20', 632, null),
  mk(752, 504, '2026-12-20', 649, '2027-01-02'),
];
const by = (lines: Line[], id: string) => lines.find((l) => l.lineId === id)!;
const shape = (s: m.SplitDraft) => [s.qty, s.deliveryDate, s.sitsOnLineId];

/** 480 = 14 + 403, the 403 moved onto 608 and cut to 236, 167 left. */
function cutTo236() {
  let lines = m.addSplit(owner(), 'L480').lines;
  const moved = by(lines, 'L480').splits[1];
  lines = m.moveSplit(lines, 'L480', moved.id, moved.qty, {
    date: m.plannedDateOf(lines, 'L608')!,
    sitsOnLineId: 'L608',
  });
  lines = m.setQty(lines, 'L480', moved.id, 236);
  return { lines, movedId: moved.id };
}

describe('AC-G20 F1 the chip makes its own row', () => {
  it('"167 left" dropped on 608 is a separate 167 split next to the 236', () => {
    const { lines, movedId } = cutTo236();
    expect(m.gapOf(by(lines, 'L480'))).toBe(167);
    const next = m.placeRest(lines, 'L480', {
      date: m.plannedDateOf(lines, 'L608')!,
      sitsOnLineId: 'L608',
    });
    const splits = by(next, 'L480').splits;
    expect(splits.find((s) => s.id === movedId)!.qty).toBe(236);
    const on608 = splits.filter((s) => s.sitsOnLineId === 'L608');
    expect(on608.map(shape)).toEqual([
      [236, '2026-11-20', 'L608'],
      [167, '2026-11-20', 'L608'],
    ]);
  });

  it('the 167 re-dated to 2029, then 752 "37 left" lands on 608 at the earliest foreign date', () => {
    const { lines } = cutTo236();
    let next = m.placeRest(lines, 'L480', {
      date: m.plannedDateOf(lines, 'L608')!,
      sitsOnLineId: 'L608',
    });
    const rest = by(next, 'L480').splits.find((s) => s.qty === 167);
    expect(rest, 'a separate 167 split').toBeTruthy();
    next = m.setDate(next, 'L480', rest!.id, '2029-11-20');
    next = next.map((l) =>
      l.lineId === 'L752'
        ? {
            ...l,
            splits: [
              {
                id: 's467',
                qty: 467,
                deliveryDate: '2027-01-02',
                isCancel: false,
                sitsOnLineId: 'L752',
                remark: '',
              },
            ],
          }
        : l,
    );
    expect(m.gapOf(by(next, 'L752'))).toBe(37);
    const date = m.plannedDateOf(next, 'L608');
    expect(date).toBe('2026-11-20');
    next = m.placeRest(next, 'L752', { date: date!, sitsOnLineId: 'L608' });
    expect(by(next, 'L752').splits.find((s) => s.qty === 37)).toMatchObject({
      deliveryDate: '2026-11-20',
      sitsOnLineId: 'L608',
    });
  });

  it('guard: dragging a whole row onto a same-line same-date split still merges', () => {
    const { lines } = cutTo236();
    const withRest = m.placeRest(lines, 'L480', { date: '2029-11-20', sitsOnLineId: 'L608' });
    const rest = by(withRest, 'L480').splits.find((s) => s.qty === 167)!;
    const next = m.moveSplit(withRest, 'L480', rest.id, 167, {
      date: '2026-11-20',
      sitsOnLineId: 'L608',
    });
    const on608 = by(next, 'L480').splits.filter((s) => s.sitsOnLineId === 'L608');
    expect(on608.map(shape)).toEqual([[403, '2026-11-20', 'L608']]);
  });
});

describe('AC-G20 F3 + Split never makes a qty-0 row', () => {
  it('752 (new 649 >= base 504) gets exactly one split, 504 at 2027-01-02', () => {
    const next = m.addSplit(owner(), 'L752').lines;
    const splits = by(next, 'L752').splits;
    expect(splits.map(shape)).toEqual([[504, '2027-01-02', 'L752']]);
    expect(splits.some((s) => s.qty === 0)).toBe(false);
  });

  it('guard: 480 still gets 14 + 403', () => {
    const splits = by(m.addSplit(owner(), 'L480').lines, 'L480').splits;
    expect(splits.map((s) => s.qty)).toEqual([14, 403]);
  });
});
