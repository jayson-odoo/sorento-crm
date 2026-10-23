/** OI-LINE-SPLIT owner round 18 Oct (AC-A2b): the wire `new_qty` / `new_date` reach SplitLine. */
import { describe, expect, it } from 'vitest';
import { fromPayload } from './lineSplitModel';

const line = (over: Record<string, unknown>) => ({
  line_id: 'L1', line_no: 480, item_code: 'CSK14B', location: 'BRW-BB',
  base_qty: 417, base_date: '2026-10-20', now_qty: 14, now_date: '2026-09-20',
  pending_change: true, delivered_qty: 0, splits: [], ...over,
});
const read = (over: Record<string, unknown>) =>
  fromPayload({
    pso_id: 'p', so_number: 'SO1', customer: null, project: null,
    lines: [line(over)],
  } as never)[0] as unknown as Record<string, unknown>;

describe('fromPayload new_qty / new_date', () => {
  it('maps values to newQty and newDate', () => {
    const l = read({ new_qty: 14, new_date: '2026-09-20' });
    expect(l.newQty).toBe(14);
    expect(l.newDate).toBe('2026-09-20');
  });

  it('keeps null as null (blank cell), qty 0 is not blank', () => {
    const l = read({ new_qty: null, new_date: null });
    expect(l.newQty).toBeNull();
    expect(l.newDate).toBeNull();
    expect(read({ new_qty: 0, new_date: null }).newQty).toBe(0);
  });
});
