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
  isReservableInquiryRow,
  reserveRowsOfLines,
  lineConfirmationOf,
  lineFooterTotals,
  lineHistoryEntries,
  reserveHistoryRowOf,
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
    const entries = lineHistoryEntries(line);
    // F2: fresh carries previous_qty (its Why needs it), so a Before entry follows Now.
    expect(entries.map((entry) => String(entry.what))).toEqual(['Now', 'Before', 'Used']);
    expect(entries.filter((entry) => String(entry.what) !== 'Before').map((entry) => [entry.row.id, entry.what])).toEqual([
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

  it('a line whose rows are all used is not rendered (was O2 Nothing to buy)', () => {
    // OI-RESERVE-USED-ROW (owner, 4 Nov 2026, supersedes O2/G6 for this shape): a line left with
    // only used rows is History, not a line, on both the Lines tab and the Documents counts.
    expect(
      foldInquiryLines([row({ id: 'a', core_line_id: 'cl-6', qty: '3', redirected_to_pool: true })]),
    ).toEqual([]);
  });

});

describe('AC-ND-4 (G4, S2): SO Qty is the sales order line qty the server sends', () => {
  it('reads so_line_qty, whatever the rows asked for', () => {
    const [line] = foldInquiryLines([row({ id: 'a', core_line_id: 'cl-4', qty: '3', so_line_qty: '5' })]);
    expect(line.soQty).toBe(5);
    expect(line).not.toHaveProperty('soQtyMocked');
  });

  it('a row that names no sales order line has no SO Qty, never a figure borrowed off its rows', () => {
    const [line] = foldInquiryLines([row({ id: 'a', core_line_id: null, line_no: null, qty: '3', so_line_qty: null })]);
    expect(line.soQty).toBeNull();
  });

  it('a cancelled line still reads the SO Qty the sales order shows', () => {
    const [cancelled] = foldInquiryLines([
      row({ id: 'b', core_line_id: 'cl-5', qty: '4', so_line_qty: '4', line_cancelled: true }),
    ]);
    expect(cancelled.soQty).toBe(4);
  });
});

describe('AC-ND-20 (S2): the one Lines fetch carries cancelled rows; they are history, never a line', () => {
  it('a cancelled row folds into its line as history and adds to no quantity', () => {
    const [line] = foldInquiryLines([
      row({ id: 'now', core_line_id: 'cl-1', qty: '5', so_line_qty: '5' }),
      row({ id: 'old', core_line_id: 'cl-1', qty: '2', state: 'cancelled', note: 'Superseded by revision 2' }),
    ]);
    expect(line.liveRows.map((r) => r.id)).toEqual(['now']);
    expect(line.historyRows.map((r) => r.id)).toEqual(['old']);
    expect([line.requested, line.remaining]).toEqual([5, 5]);
  });

  it('a line whose every row is cancelled is not rendered (the header counts it out too, G10)', () => {
    const lines = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-1', line_no: 1 }),
      row({ id: 'b', core_line_id: 'cl-2', line_no: 2, state: 'cancelled' }),
      row({ id: 'c', core_line_id: null, line_no: null, state: 'cancelled' }),
    ]);
    expect(lines.map((line) => line.lineNo)).toEqual([1]);
  });

  it('a line of only a used row and a cancelled row is not rendered', () => {
    // OI-RESERVE-USED-ROW (owner, 4 Nov 2026, supersedes O2/G6 for this shape): a line left with
    // only used rows is History, not a line, on both the Lines tab and the Documents counts.
    const lines = foldInquiryLines([
      row({ id: 'u', core_line_id: 'cl-3', line_no: 3, redirected_to_pool: true }),
      row({ id: 'x', core_line_id: 'cl-3', line_no: 3, state: 'cancelled' }),
    ]);
    expect(lines).toEqual([]);
  });
});

describe('AC-ND-17 (G4, G10): footer totals over the line rows, cancelled lines excluded', () => {
  it('sums SO Qty, Requested, Taken; Remaining is the footer subtraction', () => {
    const lines = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-1', qty: '5', so_line_qty: '5' }),
      row({ id: 'b', core_line_id: 'cl-2', qty: '6', so_line_qty: '12', linked_qty: '6', state: 'partly_linked' }),
      row({ id: 'c', core_line_id: 'cl-2', qty: '4', so_line_qty: '12' }),
      row({ id: 'd', core_line_id: 'cl-5', qty: '4', so_line_qty: '4', line_cancelled: true }),
      row({ id: 'e', core_line_id: null, line_no: null, qty: '1', so_line_qty: null }),
    ]);
    // SO Qty is counted once per line (12, not 24), a line with no SO Qty adds nothing.
    expect(lineFooterTotals(lines)).toEqual({ soQty: 17, requested: 16, taken: 6, remaining: 10 });
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
    const [line] = foldInquiryLines([
      row({ id: 'now', core_line_id: 'cl-1', raised_at: '2026-09-25T08:00:00Z' }),
      ...cancelled,
    ]);
    const entries = lineHistoryEntries(line);
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
      row({ id: 'carried', core_line_id: 'cl-1', qty: '2', state: 'cancelled', note: 'Superseded by revision 2', raised_at: '2026-09-19T08:00:00Z' }),
    ]);
    const entries = lineHistoryEntries(line);
    expect(entries.map((entry) => [entry.row.id, entry.what])).toEqual([
      ['fresh', 'Now'],
      ['used', 'Used'],
      ['carried', 'Re-raised'],
    ]);
    expect(entries[2].why).toBe('Superseded by revision 2');
  });

  it('S1: a superseded row no later row raises again at its qty stays Superseded', () => {
    const [line] = foldInquiryLines([
      row({ id: 'fresh', core_line_id: 'cl-1', qty: '5', raised_at: '2026-09-25T08:00:00Z' }),
      row({ id: 'old', core_line_id: 'cl-1', qty: '2', state: 'cancelled', note: 'Superseded by revision 2', raised_at: '2026-09-19T08:00:00Z' }),
    ]);
    const entries = lineHistoryEntries(line);
    expect(entries[1].what).toBe('Superseded');
  });

  it('rows on a cancelled line read Line cancelled', () => {
    const [line] = foldInquiryLines([row({ id: 'a', core_line_id: 'cl-5', line_cancelled: true })]);
    expect(lineHistoryEntries(line).map((entry) => entry.what)).toEqual(['Line cancelled']);
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
    // A used-only line is not rendered at all (OI-RESERVE-USED-ROW), so it has no Reserve tab.
    expect(
      foldInquiryLines([
        row({ id: 'd', core_line_id: 'cl-6', reserve_state: 'reserved', redirected_to_pool: true }),
      ]),
    ).toEqual([]);
  });
});

/**
 * PR #1266 fix round W1 (owner, 26 Sep 2026: "i just realized after we click confirm, at
 * the line level can't really see it is confirmed, can we have an icon here to show it is
 * confirmed?"). Counted rows = the line's live rows minus any rejected row; a cancelled
 * line always reads none.
 */
describe('W1 line confirmation', () => {
  it('W1: a line whose every live row is acknowledged reads confirmed, by its latest confirmer', () => {
    const [line] = foldInquiryLines([
      row({
        id: 'a',
        core_line_id: 'cl-1',
        line_no: 1,
        ack_state: 'acknowledged',
        acknowledged_by_name: 'Aisyah',
        acknowledged_at: '2026-09-26T09:00:00Z',
      }),
      row({
        id: 'b',
        core_line_id: 'cl-1',
        line_no: 1,
        ack_state: 'acknowledged',
        acknowledged_by_name: 'Nurain',
        acknowledged_at: '2026-09-26T11:00:00Z',
      }),
      // A used (history) row sitting in `changed` must not stop the line reading confirmed.
      row({
        id: 'used',
        core_line_id: 'cl-1',
        line_no: 1,
        redirected_to_pool: true,
        ack_state: 'changed',
      }),
      // A cancelled row sitting in `awaiting` must not stop the line reading confirmed either.
      row({
        id: 'old',
        core_line_id: 'cl-1',
        line_no: 1,
        state: 'cancelled',
        ack_state: 'awaiting',
      }),
    ]);
    expect(lineConfirmationOf(line)).toEqual({ kind: 'confirmed', by: 'Nurain', at: '2026-09-26T11:00:00Z' });
  });

  it('W1: a line with some live rows acknowledged reads n of m', () => {
    const [line] = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-2', line_no: 2, ack_state: 'acknowledged' }),
      row({ id: 'b', core_line_id: 'cl-2', line_no: 2, ack_state: 'awaiting' }),
      row({ id: 'c', core_line_id: 'cl-2', line_no: 2, ack_state: 'changed' }),
    ]);
    expect(lineConfirmationOf(line)).toEqual({ kind: 'partly', confirmed: 1, total: 3 });
  });

  it('W1: nothing to confirm reads none', () => {
    const [everyAwaiting] = foldInquiryLines([
      row({ id: 'a', core_line_id: 'cl-3', line_no: 3, ack_state: 'awaiting' }),
      row({ id: 'b', core_line_id: 'cl-3', line_no: 3, ack_state: 'awaiting' }),
    ]);
    expect(lineConfirmationOf(everyAwaiting)).toEqual({ kind: 'none' });

    const [onlyRejected] = foldInquiryLines([
      row({ id: 'd', core_line_id: 'cl-5', line_no: 5, ack_state: 'rejected' }),
    ]);
    expect(lineConfirmationOf(onlyRejected)).toEqual({ kind: 'none' });

    // A rejected row is left out of n of m entirely: 1 acked + 1 rejected reads confirmed,
    // not "1 of 2".
    const [rejectedLeftOut] = foldInquiryLines([
      row({ id: 'e', core_line_id: 'cl-6', line_no: 6, ack_state: 'acknowledged', acknowledged_by_name: 'Aisyah', acknowledged_at: '2026-09-26T09:00:00Z' }),
      row({ id: 'f', core_line_id: 'cl-6', line_no: 6, ack_state: 'rejected' }),
    ]);
    expect(lineConfirmationOf(rejectedLeftOut)).toEqual({ kind: 'confirmed', by: 'Aisyah', at: '2026-09-26T09:00:00Z' });
  });
  // Review SF1: a cancelled SO line flips its rows back to `changed` and waits on Confirm
  // (G7, C1). Its State reads "Line cancelled" before and after, so the mark is the only
  // place Confirm shows on it.
  it('W1 SF1: a cancelled SO line reads none while it waits and confirmed once confirmed', () => {
    const [waiting] = foldInquiryLines([
      row({ id: 'c', core_line_id: 'cl-4', line_no: 4, line_cancelled: true, ack_state: 'changed' }),
    ]);
    expect(lineConfirmationOf(waiting)).toEqual({ kind: 'none' });

    const [confirmed] = foldInquiryLines([
      row({
        id: 'c',
        core_line_id: 'cl-4',
        line_no: 4,
        line_cancelled: true,
        ack_state: 'acknowledged',
        acknowledged_by_name: 'Aisyah',
        acknowledged_at: '2026-09-26T11:30:00Z',
      }),
    ]);
    expect(lineConfirmationOf(confirmed)).toEqual({
      kind: 'confirmed',
      by: 'Aisyah',
      at: '2026-09-26T11:30:00Z',
    });
  });
});

describe('Review S1 (PR #1266 at a98e01cf): a line AutoCount has not reconciled yet', () => {
  // `core_sales_order_line_id` is null on every unreconciled line, and `core_line_id` /
  // `line_no` come off that same join, so both are null too. The mirror line
  // (`so_line_id`) is still there and is the key the header counts use (G10).
  const unreconciled = (over: Partial<OrderInquiryWorklistRow>) =>
    row({
      core_line_id: null,
      line_no: null,
      so_line_id: 'sol-1',
      so_line_no: 1,
      so_line_qty: '5',
      ...over,
    });

  it('folds a used row and a fresh row on an unreconciled line into ONE line', () => {
    const lines = foldInquiryLines([
      unreconciled({ id: 'used', qty: '2', redirected_to_pool: true, ack_state: 'changed' }),
      unreconciled({ id: 'fresh', qty: '5', ack_state: 'changed' }),
    ]);
    expect(lines).toHaveLength(1);
    expect(lines[0].rows.map((r) => r.id).sort()).toEqual(['fresh', 'used']);
    expect(lines[0].requested).toBe(5);
  });

  it('the SO Qty footer counts the unreconciled line once, not once per row', () => {
    const lines = foldInquiryLines([
      unreconciled({ id: 'used', qty: '2', redirected_to_pool: true }),
      unreconciled({ id: 'fresh', qty: '5' }),
    ]);
    expect(lineFooterTotals(lines).soQty).toBe(5);
  });

  it('keys on the mirror line, so two unreconciled lines stay two lines', () => {
    const lines = foldInquiryLines([
      unreconciled({ id: 'a', so_line_id: 'sol-1', so_line_no: 1 }),
      unreconciled({ id: 'b', so_line_id: 'sol-2', so_line_no: 2 }),
    ]);
    expect(lines).toHaveLength(2);
    expect(foldKeyOf(lines[0].rows[0])).not.toBe(foldKeyOf(lines[1].rows[0]));
  });

  it('sorts unreconciled lines by the sales order line No. (so_line_no)', () => {
    const lines = foldInquiryLines([
      unreconciled({ id: 'b', so_line_id: 'sol-2', so_line_no: 2 }),
      unreconciled({ id: 'a', so_line_id: 'sol-1', so_line_no: 1 }),
    ]);
    expect(lines.map((line) => line.lineNo)).toEqual([1, 2]);
  });
});

describe('Review S2 (PR #1266): a line whose only waiting row is a used row reads To confirm', () => {
  // One rule, shared with the header's `lines_to_confirm` and the Confirm sweep: a used
  // row waits while it is not cancelled and its ack is awaiting or changed.
  it('shape a re-pinned: live rows confirmed, the used row still changed, reads its live state', () => {
    // OI-RESERVE-USED-ROW: only a live row holds a line To confirm (the tabs tally).
    const [line] = foldInquiryLines([
      row({ id: 'used', core_line_id: 'cl-1', qty: '2', redirected_to_pool: true, ack_state: 'changed' }),
      row({ id: 'fresh', core_line_id: 'cl-1', qty: '5', state: 'placed', ack_state: 'acknowledged' }),
    ]);
    expect(line.state).toBe('placed');
    expect(line.waitingUsedRows.map((r) => r.id)).toEqual(['used']);
  });

  it('shape b re-pinned: a line with only a used row is not rendered, whatever its ack', () => {
    // OI-RESERVE-USED-ROW (owner, 4 Nov 2026, supersedes O2/G6 for this shape): a line left with
    // only used rows is History, not a line, on both the Lines tab and the Documents counts.
    for (const ack_state of ['changed', 'awaiting', 'acknowledged'] as const) {
      expect(
        foldInquiryLines([
          row({ id: 'used', core_line_id: 'cl-1', qty: '2', redirected_to_pool: true, ack_state }),
        ]),
      ).toEqual([]);
    }
  });

  it('a live row CS changed still reads To confirm', () => {
    const [line] = foldInquiryLines([
      row({ id: 'used', core_line_id: 'cl-1', qty: '2', redirected_to_pool: true, ack_state: 'awaiting' }),
      row({ id: 'fresh', core_line_id: 'cl-1', qty: '5', state: 'placed', ack_state: 'changed' }),
    ]);
    expect(line.state).toBe('to_confirm');
  });

  it('a cancelled used row is history and never waits', () => {
    const [line] = foldInquiryLines([
      row({ id: 'live', core_line_id: 'cl-1', qty: '5', state: 'placed', ack_state: 'acknowledged' }),
      row({ id: 'old', core_line_id: 'cl-1', qty: '2', state: 'cancelled', redirected_to_pool: true, ack_state: 'changed' }),
    ]);
    expect(line.state).toBe('placed');
    expect(line.waitingUsedRows).toEqual([]);
  });

  it('a cancelled SO line still reads Line cancelled while its used row waits', () => {
    const [line] = foldInquiryLines([
      row({ id: 'used', core_line_id: 'cl-1', qty: '2', redirected_to_pool: true, ack_state: 'changed', line_cancelled: true }),
      row({ id: 'live', core_line_id: 'cl-1', qty: '5', ack_state: 'acknowledged', line_cancelled: true }),
    ]);
    expect(line.state).toBe('line_cancelled');
    expect(line.waitingUsedRows.map((r) => r.id)).toEqual(['used']);
  });
});

describe('SO-LINE-CHANGE-HISTORY F2 (AC-7, AC-9 to AC-13): the Before entry', () => {
  const nowRow = (overrides: Partial<OrderInquiryWorklistRow> = {}) =>
    row({
      id: 'e9fac76d',
      core_line_id: 'cl-1',
      qty: '280',
      delivery_date: '2027-03-01',
      previous_qty: '182',
      previous_delivery_date: '2026-06-01',
      inquiry_no: 'OI-2609-0011',
      changed_at: '2026-09-17T03:25:36Z',
      raised_at: '2026-09-20T08:00:00Z',
      note: 'Customer moved the date',
      ...overrides,
    });
  const whats = (rows: OrderInquiryWorklistRow[]) =>
    lineHistoryEntries(foldInquiryLines(rows)[0]).map((entry) => String(entry.what));

  it('AC-7: one Before entry directly after Now and before retired rows, with the exact Why', () => {
    const retired = row({ id: 'old', core_line_id: 'cl-1', state: 'cancelled', raised_at: '2026-09-01T08:00:00Z' });
    const [line] = foldInquiryLines([retired, nowRow()]);
    const entries = lineHistoryEntries(line);
    expect(entries.map((entry) => String(entry.what))).toEqual(['Now', 'Before', 'Cancelled']);
    expect(entries[1].why).toBe('Was 182 on 01/06/2026, before OI-2609-0011 changed it');
  });

  it('AC-9: no previous delivery date reads "Was 182, before ... changed it"', () => {
    const entries = lineHistoryEntries(foldInquiryLines([nowRow({ previous_delivery_date: null })])[0]);
    expect(entries.map((entry) => String(entry.what))).toEqual(['Now', 'Before']);
    expect(entries[1].why).toBe('Was 182, before OI-2609-0011 changed it');
  });

  it('AC-10: no previous_* adds no Before entry', () => {
    expect(whats([nowRow({ previous_qty: null, previous_delivery_date: null })])).toEqual(['Now']);
  });

  it('AC-11: previous_qty equal to qty with a different previous date still lists a Before entry', () => {
    const entries = lineHistoryEntries(
      foldInquiryLines([nowRow({ qty: '182', previous_qty: '182' })])[0],
    );
    expect(entries.filter((entry) => String(entry.what) === 'Before')).toHaveLength(1);
  });

  it('AC-12: two Now rows with previous_* give two Before entries, in Now-row order, after both Now rows', () => {
    const a = nowRow({ id: 'a', previous_qty: '10', inquiry_no: 'OI-2609-0001' });
    const b = nowRow({ id: 'b', previous_qty: '20', inquiry_no: 'OI-2609-0002' });
    const entries = lineHistoryEntries(foldInquiryLines([a, b])[0]);
    expect(entries.map((entry) => String(entry.what))).toEqual(['Now', 'Now', 'Before', 'Before']);
    const gridIds = entries.map((entry) => (entry as { id?: string }).id ?? entry.row.id);
    expect(gridIds).toEqual(['a', 'b', 'a:before', 'b:before']);
    expect(new Set(gridIds).size).toBe(4);
    expect(entries[2].why).toBe('Was 10 on 01/06/2026, before OI-2609-0001 changed it');
    expect(entries[3].why).toBe('Was 20 on 01/06/2026, before OI-2609-0002 changed it');
  });

  it('AC-13: the Now entry keeps its own Why wording', () => {
    const entries = lineHistoryEntries(foldInquiryLines([nowRow()])[0]);
    expect(entries[0].what).toBe('Now');
    expect(entries[0].why).toBe('Was 182. Customer moved the date');
  });
});

describe('OI-RESERVE-ANY-ROW: the reserve-bearing row of any verb addresses the line (AC-AR-11)', () => {
  it('an ORDER row beside a DELAY row carrying the request: the DELAY row is primary', () => {
    const [line] = foldInquiryLines([
      row({ id: 'order', so_line_id: 'sol-1', qty: '22' }),
      row({ id: 'delay', so_line_id: 'sol-1', verb: 'DELAY', qty: '33', reserve_state: 'requested' }),
    ]);
    expect(line.primary.id).toBe('delay');
    // Requested stays the buy rows' qty: the DELAY row restates the line, it adds nothing.
    expect(line.requested).toBe(22);
  });

  it('Taken counts reserve on a not-Done DELAY row', () => {
    const [line] = foldInquiryLines([
      row({ id: 'delay', so_line_id: 'sol-1', verb: 'DELAY', qty: '33', reserved_qty: '33', reserve_state: 'reserved' }),
    ]);
    expect(line.taken).toBe(33);
  });

  it('isReservableInquiryRow: live and not Done, any verb', () => {
    expect(isReservableInquiryRow(row({ verb: 'DELAY' }))).toBe(true);
    expect(isReservableInquiryRow(row({ verb: 'ADVANCE', state: 'placed' }))).toBe(true);
    expect(isReservableInquiryRow(row({ verb: 'DELAY', state: 'actioned' }))).toBe(false);
    expect(isReservableInquiryRow(row({ state: 'cancelled' }))).toBe(false);
    expect(isReservableInquiryRow(row({ verb: 'DELAY', redirected_to_pool: true }))).toBe(false);
  });
});

describe('OI-RESERVE-ANY-ROW owner (b): ORDER and DELAY both live on one line, each reserve counted once', () => {
  it('Requested stays the buy qty; Taken adds each row reserve once', () => {
    const [line] = foldInquiryLines([
      row({ id: 'order', so_line_id: 'sol-1', qty: '22', linked_qty: '0', reserved_qty: '10' }),
      row({ id: 'delay', so_line_id: 'sol-1', verb: 'DELAY', qty: '33', reserved_qty: '5' }),
    ]);
    expect(line.requested).toBe(22);
    expect(line.taken).toBe(15);
    expect(line.remaining).toBe(7);
  });
});

describe('OI-RESERVE-ANY-ROW crew: one action on one line asks once for the line', () => {
  const both = [
    row({ id: 'used', so_line_id: 'sol-1', qty: '55', redirected_to_pool: true }),
    row({ id: 'order', so_line_id: 'sol-1', qty: '22' }),
    row({ id: 'delay', so_line_id: 'sol-1', verb: 'DELAY', qty: '33' }),
    row({ id: 'other', so_line_id: 'sol-2', qty: '7' }),
  ];

  it('a ticked line with a live ORDER and a live DELAY row sends one row, the ORDER (primary)', () => {
    const picked = new Set(['order', 'delay']);
    expect(reserveRowsOfLines(both, (r) => picked.has(r.id)).map((r) => r.id)).toEqual(['order']);
  });

  it('picking only the DELAY row still sends the line once, on its buy row', () => {
    expect(reserveRowsOfLines(both, (r) => r.id === 'delay').map((r) => r.id)).toEqual(['order']);
  });

  it('OI-2609-0257 line 7: only the DELAY row is live, so it is the one sent', () => {
    const rows = [
      row({ id: 'used', so_line_id: 'sol-7', qty: '55', redirected_to_pool: true }),
      row({ id: 'delay', so_line_id: 'sol-7', verb: 'DELAY', qty: '33' }),
    ];
    expect(reserveRowsOfLines(rows, (r) => r.id === 'delay').map((r) => r.id)).toEqual(['delay']);
  });

  it('two ticked lines send one row each', () => {
    expect(reserveRowsOfLines(both, () => true).map((r) => r.id)).toEqual(['order', 'other']);
  });
});

describe('OI-RESERVE-ANY-ROW review R1: a line split over several ORDER rows asks for each', () => {
  const split = [
    row({ id: 'a', so_line_id: 'sol-1', qty: '10' }),
    row({ id: 'b', so_line_id: 'sol-1', qty: '12' }),
  ];

  it('both raised ORDER rows of the line are sent', () => {
    expect(reserveRowsOfLines(split, () => true).map((r) => r.id)).toEqual(['a', 'b']);
  });

  it('after A is requested, B is still sent (A is not primary-locked)', () => {
    const rows = [{ ...split[0], reserve_state: 'requested' } as OrderInquiryWorklistRow, split[1]];
    expect(reserveRowsOfLines(rows, () => true).map((r) => r.id)).toEqual(['a', 'b']);
    expect(reserveRowsOfLines(rows, (r) => r.id === 'b').map((r) => r.id)).toEqual(['b']);
  });

  it('a Done ORDER row is left out; a line with nothing reservable sends its primary', () => {
    const done = [row({ id: 'x', so_line_id: 'sol-1', state: 'actioned' })];
    expect(reserveRowsOfLines([...done, row({ id: 'y', so_line_id: 'sol-1' })], () => true).map((r) => r.id)).toEqual(['y']);
    expect(reserveRowsOfLines(done, () => true).map((r) => r.id)).toEqual(['x']);
  });

  it('two live notice rows and no buy row: one row, the picked one', () => {
    const notices = [
      row({ id: 'adv', so_line_id: 'sol-1', verb: 'ADVANCE' }),
      row({ id: 'dly', so_line_id: 'sol-1', verb: 'DELAY' }),
    ];
    expect(reserveRowsOfLines(notices, (r) => r.id === 'dly').map((r) => r.id)).toEqual(['dly']);
    expect(reserveRowsOfLines(notices, () => true)).toHaveLength(1);
  });
});
