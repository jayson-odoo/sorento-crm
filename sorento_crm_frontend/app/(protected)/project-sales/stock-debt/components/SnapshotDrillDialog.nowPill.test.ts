import { describe, expect, it } from 'vitest';
import { nowPill, type GroupLine } from './SnapshotDrillDialog';

/** OI-RESERVE-USED-ROW (owner, 4 Nov): the drill's Now is ONE pill per line, first match wins. */
function line(
  so_status: string | null,
  open_qty: number,
  rows: Array<{ reserve_state?: 'requested' | 'parked' | 'reserved' | 'cancelled' | null; reserve_qty?: number | null }>,
): GroupLine {
  return {
    now: { so_status, open_qty },
    group_oi_rows: rows.map((row, index) => ({
      oi_id: 'oi', inquiry_no: 'OI-2609-0257', row_id: `r${index}`, qty: 33, verb: 'ORDER',
      state: 'raised', requestable: false, ...row,
    })),
  } as unknown as GroupLine;
}

describe('nowPill', () => {
  it('Open N with no request', () => {
    expect(nowPill(line('open', 33, [{}])).text).toBe('Open 33');
  });
  it('Reserve requested N, the prod case', () => {
    expect(nowPill(line('open', 33, [{ reserve_state: 'requested', reserve_qty: 33 }])).text).toBe(
      'Reserve requested 33',
    );
  });
  it('Reserved outranks requested, and sums the line\'s rows', () => {
    const pill = nowPill(
      line('open', 50, [
        { reserve_state: 'reserved', reserve_qty: 20 },
        { reserve_state: 'reserved', reserve_qty: 13 },
        { reserve_state: 'requested', reserve_qty: 17 },
      ]),
    );
    expect(pill.text).toBe('Reserved 33');
  });
  it('requested outranks parked', () => {
    expect(
      nowPill(line('open', 9, [{ reserve_state: 'parked', reserve_qty: 4 }, { reserve_state: 'requested', reserve_qty: 5 }])).text,
    ).toBe('Reserve requested 5');
  });
  it('a cancelled request reads Open', () => {
    expect(nowPill(line('open', 7, [{ reserve_state: 'cancelled', reserve_qty: 7 }])).text).toBe('Open 7');
  });
  it('SO cancelled outranks everything; a missing SO reads SO missing', () => {
    expect(nowPill(line('cancelled', 0, [{ reserve_state: 'reserved', reserve_qty: 5 }])).text).toBe('SO cancelled');
    expect(nowPill(line(null, 0, [])).text).toBe('SO missing');
  });
});
