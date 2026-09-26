/**
 * The handshake's own words (`PLAN-scm-oi-handshake.md`, AC-H2/AC-H4/AC-H5/AC-H8): one
 * place decides a row's label, whether it may be ticked or refused, and what its previous
 * value read - so the column, the checkbox and the bulk bar can never disagree.
 */
import { describe, expect, it } from 'vitest';
import {
  ACK_ANY,
  ACK_FILTER_OPTIONS,
  ACK_LABELS,
  ackStateOf,
  bundledHostChangeLines,
  isBulkRejectable,
  isRejectable,
  previousValueOf,
} from './orderInquiryAck';

describe('ackStateOf', () => {
  it('reads each of the four states off the row', () => {
    expect(ackStateOf({ ack_state: 'awaiting' })).toBe('awaiting');
    expect(ackStateOf({ ack_state: 'acknowledged' })).toBe('acknowledged');
    expect(ackStateOf({ ack_state: 'changed' })).toBe('changed');
    expect(ackStateOf({ ack_state: 'rejected' })).toBe('rejected');
  });

  it('falls back to awaiting when the row carries none', () => {
    expect(ackStateOf({})).toBe('awaiting');
  });

  it('falls back to awaiting for a value the four states do not name', () => {
    // A row written before the column existed, or a value a future state renamed -
    // either way, an unrecognised string must not read as one of the four labels.
    expect(ackStateOf({ ack_state: 'somehow-else' })).toBe('awaiting');
  });
});

describe('ACK_LABELS (R7: Confirm replaced Acknowledge everywhere a person can see it)', () => {
  it('prints the label the column, the filter and the bulk bar all read', () => {
    expect(ACK_LABELS.awaiting).toBe('To confirm');
    expect(ACK_LABELS.acknowledged).toBe('Confirmed');
    expect(ACK_LABELS.changed).toBe('Changed');
    expect(ACK_LABELS.rejected).toBe('Rejected');
  });
});

describe('ACK_ANY / ACK_FILTER_OPTIONS (PLAN-oi-confirm-per-so, AC-CF-13: G4/G5 reversed)', () => {
  it('ACK_ANY is the URL word for "show me everything"', () => {
    expect(ACK_ANY).toBe('all');
  });

  it('offers To confirm, Confirmed, Changed, Rejected, All - a row is born awaiting again', () => {
    expect(ACK_FILTER_OPTIONS.map((option) => option.value)).toEqual([
      'to_confirm',
      'acknowledged',
      'changed',
      'rejected',
      'all',
    ]);
    expect(ACK_FILTER_OPTIONS.map((option) => option.label)).toEqual([
      'To confirm',
      'Confirmed',
      'Changed',
      'Rejected',
      'All',
    ]);
  });
});

describe('isRejectable', () => {
  it('is true for every state except rejected', () => {
    expect(isRejectable({ ack_state: 'awaiting' })).toBe(true);
    expect(isRejectable({ ack_state: 'acknowledged' })).toBe(true);
    expect(isRejectable({ ack_state: 'changed' })).toBe(true);
  });

  it('is false once already rejected - nothing left to refuse', () => {
    expect(isRejectable({ ack_state: 'rejected' })).toBe(false);
  });
});

describe('isBulkRejectable (plan section 1: Reject takes ANY owed row, draft-linked included)', () => {
  it('is true for a raised row, whether or not it already carries drafted links', () => {
    // Drafts are written at raise now, so most rows purchasing sees are already
    // `placed` - a Reject scoped to unlinked rows would refuse almost nothing.
    expect(isBulkRejectable({ ack_state: 'awaiting', state: 'raised' })).toBe(true);
    expect(isBulkRejectable({ ack_state: 'awaiting', state: 'placed' })).toBe(true);
    expect(isBulkRejectable({ ack_state: 'awaiting', state: 'partly_linked' })).toBe(true);
  });

  it('is true for a changed row still placed - purchasing has to look again', () => {
    expect(isBulkRejectable({ ack_state: 'changed', state: 'placed' })).toBe(true);
  });

  it('is true for an already-confirmed row - Reject accepts a placed row too (R1)', () => {
    expect(isBulkRejectable({ ack_state: 'acknowledged', state: 'placed' })).toBe(true);
  });

  it('is false once already rejected', () => {
    expect(isBulkRejectable({ ack_state: 'rejected', state: 'placed' })).toBe(false);
  });

  it('is false for a cancelled or an actioned row - nothing left to refuse', () => {
    expect(isBulkRejectable({ ack_state: 'awaiting', state: 'cancelled' })).toBe(false);
    expect(isBulkRejectable({ ack_state: 'awaiting', state: 'actioned' })).toBe(false);
  });
});

describe('previousValueOf', () => {
  it('reads qty and date off the row the settle-in-place wrote', () => {
    expect(
      previousValueOf({ previous_qty: '10', previous_delivery_date: '2026-08-25' }),
    ).toEqual({ qty: '10', date: '2026-08-25' });
  });

  it('reads a quantity whose line had no previous delivery date', () => {
    // The case the old note-parsing got wrong: the backend's own sentence for it is
    // "Was 10, no previous delivery date", and the qty character class swallowed the
    // comma, so the Was / Now table printed `10,`. The figure is a figure now.
    expect(previousValueOf({ previous_qty: '10', previous_delivery_date: null })).toEqual({
      qty: '10',
      date: null,
    });
  });

  it('reads the LATEST change, because that is the only value the row keeps', () => {
    // Each settle overwrites these two columns, so a row amended twice states what it
    // said before the SECOND amendment - "what changed since I looked", not a history.
    expect(
      previousValueOf({ previous_qty: '20', previous_delivery_date: '2026-08-20' }),
    ).toEqual({ qty: '20', date: '2026-08-20' });
  });

  it('returns nothing for a row that has never been amended, rather than guessing', () => {
    expect(previousValueOf({})).toBeNull();
    expect(previousValueOf({ previous_qty: null })).toBeNull();
    expect(previousValueOf({ previous_qty: '' })).toBeNull();
  });

  it('ignores the note entirely - it is prose, not a value', () => {
    expect(previousValueOf({ note: 'Was 10 on 2026-08-25' } as never)).toBeNull();
  });
});

describe('bundledHostChangeLines (PLAN-oi-bundled-row-host-change.md)', () => {
  it('returns null for a row that carries no bundled_host_changes at all', () => {
    expect(bundledHostChangeLines({})).toBeNull();
    expect(bundledHostChangeLines({ bundled_host_changes: null })).toBeNull();
    expect(bundledHostChangeLines({ bundled_host_changes: [] })).toBeNull();
  });

  it('reads a hosts own Was/Now, in the order the entries came in', () => {
    expect(
      bundledHostChangeLines({
        bundled_host_changes: [
          {
            item_code: 'SRTWCX8605-S-RL-PJ',
            qty: '280',
            delivery_date: '2027-03-01',
            previous_qty: '182',
            previous_delivery_date: '2026-06-01',
          },
        ],
      }),
    ).toEqual(['with SRTWCX8605-S-RL-PJ: Was 182 on 01/06/2026, now 280 on 01/03/2027']);
  });

  it('reads a live host with no Was of its own as "no change"', () => {
    expect(
      bundledHostChangeLines({
        bundled_host_changes: [
          {
            item_code: 'SRTWCY8605-PJ',
            qty: '50',
            delivery_date: '2026-05-01',
            previous_qty: null,
            previous_delivery_date: null,
          },
        ],
      }),
    ).toEqual(['with SRTWCY8605-PJ: 50 on 01/05/2026, no change']);
  });

  it('reads a host with no live row of its own as "no open row"', () => {
    expect(
      bundledHostChangeLines({
        bundled_host_changes: [
          {
            item_code: 'SRTWCZ',
            qty: null,
            delivery_date: null,
            previous_qty: null,
            previous_delivery_date: null,
          },
        ],
      }),
    ).toEqual(['with SRTWCZ: no open row']);
  });

  it('lists every host, one line each, in the order the server sent them', () => {
    expect(
      bundledHostChangeLines({
        bundled_host_changes: [
          {
            item_code: 'X',
            qty: '280',
            delivery_date: '2027-03-01',
            previous_qty: '182',
            previous_delivery_date: '2026-06-01',
          },
          {
            item_code: 'Y',
            qty: '50',
            delivery_date: '2026-05-01',
            previous_qty: null,
            previous_delivery_date: null,
          },
        ],
      }),
    ).toEqual([
      'with X: Was 182 on 01/06/2026, now 280 on 01/03/2027',
      'with Y: 50 on 01/05/2026, no change',
    ]);
  });
});
