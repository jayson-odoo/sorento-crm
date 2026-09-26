/**
 * `PLAN-oi-no-double-count-25sep.md` S0 (issue #1248): the Lines tab folds an order
 * inquiry's rows into ONE row per sales order line. Owner rulings 26 Sep 2026: four
 * quantity columns SO Qty / Requested / Taken / Remaining (G4), always one row per line
 * (G5), every row that is not the line's current need goes to History (G1, G6), a
 * cancelled line stays as one grey row (G7), an all-retired line reads Nothing to buy (O2).
 */
import { describe, expect, it } from 'vitest';
import {
  foldInquiryLines,
  foldKeyOf,
  lineFooterTotals,
  lineHistoryEntries,
  reserveHistoryRowOf,
  usedRowIdsToConfirm,
} from './orderInquiryLineFold';
import type { OrderInquiryWorklistRow } from '../types/orderInquiry.types';

function row(overrides: Partial<OrderInquiryWorklistRow>): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    verb: 'ORDER',
    state: 'raised',
    qty: '10',
    linked_qty: '0',
    reserved_qty: '0',
    bundled_qty: '0',
    so_number: 'SO402757',
    ...overrides,
  } as OrderInquiryWorklistRow;
}

describe('AC-ND-1 / AC-ND-2: one row per sales order line, in line order', () => {
  it('folds every row of a line into one, keyed by core_line_id', () => {
    const lines = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-2', line_no: 2 }),
      row({ id: 'b', core_line_id: 'cl-1', line_no: 1 }),
      row({ id: 'c', core_line_id: 'cl-2', line_no: 2 }),
    ]);
    expect(lines.map((line) => line.lineNo)).toEqual([1, 2]);
    expect(lines[1].rows.map((r) => r.id)).toEqual(['a', 'c']);
  });

  it('falls back to SO number + line no when the row reaches no core line', () => {
    const lines = foldInquiryLines([
      row({ id: 'a', core_line_id: null, line_no: 3 }),
      row({ id: 'b', core_line_id: null, line_no: 3 }),
    ]);
    expect(lines).toHaveLength(1);
  });

  it('a row with no line at all is a line of its own, sorted last', () => {
    const lines = foldInquiryLines([
      row({ id: 'x', core_line_id: null, line_no: null }),
      row({ id: 'y', core_line_id: null, line_no: null }),
      row({ id: 'a', core_line_id: 'cl-1', line_no: 1 }),
    ]);
    expect(lines.map((line) => line.key)).toEqual([foldKeyOf(row({ id: 'a', core_line_id: 'cl-1' })), 'row:x', 'row:y']);
  });
});

describe('AC-ND-5 / 5a / 5b (G4): Requested, Taken, Remaining over the live buy rows', () => {
  it('AC-ND-8: a partly linked 6 on PO plus a fresh 4 reads Requested 10, Taken 6, Remaining 4', () => {
    const [line] = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-2', line_no: 2, qty: '6', linked_qty: '6', state: 'partly_linked' }),
      row({ id: 'b', core_line_id: 'cl-2', line_no: 2, qty: '4', state: 'raised' }),
    ]);
    expect([line.requested, line.taken, line.remaining]).toEqual([10, 6, 4]);
    // G5: the most urgent live state wins - raised (To buy) beats partly linked.
    expect(line.state).toBe('raised');
  });

  it('Taken counts CS reserved qty too; Remaining subtracts bundled and never goes negative', () => {
    const [line] = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-4', qty: '5', reserved_qty: '2', bundled_qty: '1' }),
    ]);
    expect([line.requested, line.taken, line.remaining]).toEqual([5, 2, 2]);
    const [over] = foldInquiryLines([row({ id: 'b', core_line_id: 'cl-5', qty: '3', linked_qty: '5' })]);
    expect(over.remaining).toBe(0);
  });

  it('AC-ND-9: a 364 + 364 sheet split reads Requested 728 as one line', () => {
    const [line] = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-3', qty: '364', linked_qty: '364', state: 'placed' }),
      row({ id: 'b', core_line_id: 'cl-3', qty: '364', linked_qty: '364', state: 'placed' }),
    ]);
    expect([line.requested, line.taken, line.remaining]).toEqual([728, 728, 0]);
    expect(line.liveRows.map((r) => r.id)).toEqual(['a', 'b']);
  });

  it('AC-ND-9a: DELAY / ADVANCE / CANCEL_BALANCE rows add to no quantity; the most urgent is the Instruction', () => {
    const [line] = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-1', qty: '5' }),
      row({ id: 'b', core_line_id: 'cl-1', qty: '5', verb: 'DELAY' }),
      row({ id: 'c', core_line_id: 'cl-1', qty: '2', verb: 'CANCEL_BALANCE' }),
      row({ id: 'd', core_line_id: 'cl-1', qty: '5', verb: 'ADVANCE' }),
    ]);
    expect(line.requested).toBe(5);
    expect(line.instructionRow.id).toBe('c');
    expect(line.primary.id).toBe('a');
  });
});

describe('AC-ND-7 (G1): the #1248 case folds to the current need; the used row goes to History', () => {
  const used = row({
    id: 'used',
    core_line_id: 'cl-1',
    line_no: 1,
    qty: '2',
    linked_qty: '2',
    state: 'placed',
    redirected_to_pool: true,
    ack_state: 'changed',
  });
  const fresh = row({
    id: 'fresh',
    core_line_id: 'cl-1',
    line_no: 1,
    qty: '5',
    note: 'Replaces 2 used; PO-2026/09-0023 received',
    previous_qty: '2',
    ack_state: 'changed',
  });

  it('reads Requested 5, Taken 0, Remaining 5 off the fresh row alone', () => {
    const [line] = foldInquiryLines([used, fresh]);
    expect([line.requested, line.taken, line.remaining]).toEqual([5, 0, 5]);
    expect(line.liveRows.map((r) => r.id)).toEqual(['fresh']);
    expect(line.historyRows.map((r) => r.id)).toEqual(['used']);
  });

  it('History lists Now first (with its Was), then the used row', () => {
    const [line] = foldInquiryLines([used, fresh]);
    const entries = lineHistoryEntries(line, []);
    expect(entries.map((entry) => [entry.row.id, entry.what])).toEqual([
      ['fresh', 'Now'],
      ['used', 'Used'],
    ]);
    expect(entries[0].why).toBe('Was 2. Replaces 2 used; PO-2026/09-0023 received');
  });

  it('B1: the line State reads To confirm, not To buy, while its live row waits on purchasing in changed', () => {
    const [line] = foldInquiryLines([used, fresh]);
    expect(line.state).toBe('to_confirm');
  });

  it('B1: a fresh row born awaiting does not turn the line To confirm (AC-ND-8 still reads To buy)', () => {
    const [line] = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-2', qty: '6', linked_qty: '6', state: 'partly_linked', ack_state: 'acknowledged' }),
      row({ id: 'b', core_line_id: 'cl-2', qty: '4', state: 'raised', ack_state: 'awaiting' }),
    ]);
    expect(line.state).toBe('raised');
  });

  it('G6: confirming the line also confirms its used rows still in changed', () => {
    expect(usedRowIdsToConfirm([used, fresh], ['fresh'])).toEqual(['used']);
    expect(usedRowIdsToConfirm([used, fresh], [])).toEqual([]);
    expect(usedRowIdsToConfirm([{ ...used, ack_state: 'acknowledged' }, fresh], ['fresh'])).toEqual([]);
  });
});

describe('AC-ND-10 / AC-ND-11: cancelled line and Nothing to buy', () => {
  it('G7: a cancelled sales order line reads Requested 0, Remaining 0, state line_cancelled', () => {
    const [line] = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-5', qty: '4', line_cancelled: true }),
    ]);
    expect(line.state).toBe('line_cancelled');
    expect([line.requested, line.remaining]).toEqual([0, 0]);
    expect(line.muted).toBe(true);
  });

  it('O2: a line whose rows are all retired reads Nothing to buy, all zero', () => {
    const [line] = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-6', qty: '3', redirected_to_pool: true }),
    ]);
    expect(line.state).toBe('nothing_to_buy');
    expect([line.requested, line.taken, line.remaining]).toEqual([0, 0, 0]);
    expect(line.liveRows).toEqual([]);
    expect(line.muted).toBe(true);
  });
});

describe('AC-ND-4 (G4): SO Qty is mocked until S1 sends so_line_qty', () => {
  it('reads so_line_qty when the payload carries it', () => {
    const [line] = foldInquiryLines([row({ id: 'a', core_line_id: 'cl-4', qty: '3', so_line_qty: '5' })]);
    expect(line.soQty).toBe(5);
    expect(line.soQtyMocked).toBe(false);
  });

  it('falls back to what the line asked for, flagged as mocked', () => {
    const [line] = foldInquiryLines([row({ id: 'a', core_line_id: 'cl-4', qty: '3' })]);
    expect(line.soQty).toBe(3);
    expect(line.soQtyMocked).toBe(true);
    const [cancelled] = foldInquiryLines([row({ id: 'b', core_line_id: 'cl-5', qty: '4', line_cancelled: true })]);
    expect(cancelled.soQty).toBe(4);
  });
});

describe('AC-ND-17 (G4, G10): footer totals over the line rows, cancelled lines excluded', () => {
  it('sums SO Qty, Requested, Taken; Remaining is the footer subtraction', () => {
    const lines = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-1', qty: '5' }),
      row({ id: 'b', core_line_id: 'cl-2', qty: '6', linked_qty: '6', state: 'partly_linked' }),
      row({ id: 'c', core_line_id: 'cl-2', qty: '4' }),
      row({ id: 'd', core_line_id: 'cl-5', qty: '4', line_cancelled: true }),
    ]);
    expect(lineFooterTotals(lines)).toEqual({ soQty: 15, requested: 15, taken: 6, remaining: 9 });
  });

  it('S3: footer Remaining is the sum of the line Remaining cells, so an over-covered line nets nothing off another', () => {
    const lines = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-1', line_no: 1, qty: '5', linked_qty: '8', state: 'placed' }),
      row({ id: 'b', core_line_id: 'cl-2', line_no: 2, qty: '10' }),
    ]);
    expect(lines.map((line) => line.remaining)).toEqual([0, 10]);
    expect(lineFooterTotals(lines).remaining).toBe(10);
  });
});

describe('AC-ND-15: History row labels', () => {
  it('labels superseded, re-raised, cancel balance and plain cancelled rows, newest first after Now', () => {
    const [line] = foldInquiryLines([row({ id: 'now', core_line_id: 'cl-1', raised_at: '2026-09-25T08:00:00Z' })]);
    // Review S1: only notes the backend really writes. A carry and a plain supersede both
    // stamp "Superseded by revision N"; the carry is the one a later row of the line
    // raises again at the same qty (`s` held 4, the line now asks 10).
    const cancelled = [
      row({ id: 's', core_line_id: 'cl-1', qty: '4', state: 'cancelled', note: 'Superseded by revision 2', raised_at: '2026-09-19T08:00:00Z' }),
      row({ id: 'r', core_line_id: 'cl-1', state: 'cancelled', note: 'Superseded by revision 3', raised_at: '2026-09-22T08:00:00Z' }),
      row({ id: 'cb', core_line_id: 'cl-1', state: 'cancelled', verb: 'CANCEL_BALANCE', raised_at: '2026-09-21T08:00:00Z' }),
      row({ id: 'x', core_line_id: 'cl-1', state: 'cancelled', raised_at: '2026-09-20T08:00:00Z' }),
      row({ id: 'other', core_line_id: 'cl-9', state: 'cancelled' }),
    ];
    const entries = lineHistoryEntries(line, cancelled);
    expect(entries.map((entry) => [entry.row.id, entry.what])).toEqual([
      ['now', 'Now'],
      ['r', 'Re-raised'],
      ['cb', 'Cancel balance'],
      ['x', 'Cancelled'],
      ['s', 'Superseded'],
    ]);
  });

  it('S1: the mockup #1248 carry reads Re-raised off real data, a same-qty row raised later on the line', () => {
    const [line] = foldInquiryLines([
      row({ id: 'used', core_line_id: 'cl-1', qty: '2', state: 'placed', redirected_to_pool: true, raised_at: '2026-09-25T07:00:00Z' }),
      row({ id: 'fresh', core_line_id: 'cl-1', qty: '5', raised_at: '2026-09-25T08:00:00Z' }),
    ]);
    const entries = lineHistoryEntries(line, [
      row({ id: 'carried', core_line_id: 'cl-1', qty: '2', state: 'cancelled', note: 'Superseded by revision 2', raised_at: '2026-09-19T08:00:00Z' }),
    ]);
    expect(entries.map((entry) => [entry.row.id, entry.what])).toEqual([
      ['fresh', 'Now'],
      ['used', 'Used'],
      ['carried', 'Re-raised'],
    ]);
    expect(entries[2].why).toBe('Superseded by revision 2');
  });

  it('S1: a superseded row no later row raises again at its qty stays Superseded', () => {
    const [line] = foldInquiryLines([row({ id: 'fresh', core_line_id: 'cl-1', qty: '5', raised_at: '2026-09-25T08:00:00Z' })]);
    const entries = lineHistoryEntries(line, [
      row({ id: 'old', core_line_id: 'cl-1', qty: '2', state: 'cancelled', note: 'Superseded by revision 2', raised_at: '2026-09-19T08:00:00Z' }),
    ]);
    expect(entries[1].what).toBe('Superseded');
  });

  it('rows on a cancelled line read Line cancelled', () => {
    const [line] = foldInquiryLines([row({ id: 'a', core_line_id: 'cl-5', line_cancelled: true })]);
    expect(lineHistoryEntries(line, []).map((entry) => entry.what)).toEqual(['Line cancelled']);
  });
});

describe('S4 (AC-ND-14): the Reserve tab follows whichever live row carries the reserve', () => {
  it('finds the reserved row even when a requested row is the primary', () => {
    const [line] = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-4', qty: '2', reserve_state: 'reserved' }),
      row({ id: 'b', core_line_id: 'cl-4', qty: '3', reserve_state: 'requested' }),
    ]);
    expect(line.primary.id).toBe('b');
    expect(reserveHistoryRowOf(line)?.id).toBe('a');
  });

  it('reads a declined row too, and nothing when no live row carries reserve history', () => {
    const [declined] = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-4', qty: '3' }),
      row({ id: 'b', core_line_id: 'cl-4', qty: '2', reserve_state: 'declined' }),
    ]);
    expect(reserveHistoryRowOf(declined)?.id).toBe('b');
    const [plain] = foldInquiryLines([row({ id: 'c', core_line_id: 'cl-5', reserve_state: 'requested' })]);
    expect(reserveHistoryRowOf(plain)).toBeNull();
    const [usedOnly] = foldInquiryLines([
      row({ id: 'd', core_line_id: 'cl-6', reserve_state: 'reserved', redirected_to_pool: true }),
    ]);
    expect(reserveHistoryRowOf(usedOnly)).toBeNull();
  });
});
