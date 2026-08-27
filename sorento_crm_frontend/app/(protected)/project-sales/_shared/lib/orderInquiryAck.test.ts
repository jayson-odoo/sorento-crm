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
  ACK_TO_CONFIRM,
  ackStateOf,
  isAcknowledgeable,
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

describe('ACK_TO_CONFIRM / ACK_FILTER_OPTIONS (R3: the page opens on a to-do list)', () => {
  it('is its own filter value, not the raw awaiting state', () => {
    expect(ACK_TO_CONFIRM).toBe('to_confirm');
    expect(ACK_ANY).toBe('all');
  });

  it('offers To confirm first, then the three other states, in that order', () => {
    expect(ACK_FILTER_OPTIONS.map((option) => option.value)).toEqual([
      'to_confirm',
      'acknowledged',
      'changed',
      'rejected',
    ]);
    expect(ACK_FILTER_OPTIONS.map((option) => option.label)).toEqual([
      'To confirm',
      'Confirmed',
      'Changed',
      'Rejected',
    ]);
  });
});

describe('isAcknowledgeable', () => {
  it('is true for an awaiting row still owed', () => {
    expect(isAcknowledgeable({ ack_state: 'awaiting', state: 'raised' })).toBe(true);
  });

  it('is true for a changed row - re-acknowledging is how it returns', () => {
    expect(isAcknowledgeable({ ack_state: 'changed', state: 'partly_linked' })).toBe(true);
  });

  it('is false once acknowledged - a second press would move the stamp', () => {
    expect(isAcknowledgeable({ ack_state: 'acknowledged', state: 'raised' })).toBe(false);
  });

  it('is false for a rejected row - CS re-decides the line, not purchasing', () => {
    expect(isAcknowledgeable({ ack_state: 'rejected', state: 'raised' })).toBe(false);
  });

  it('is false for a cancelled row even while still awaiting (plan section 7)', () => {
    expect(isAcknowledgeable({ ack_state: 'awaiting', state: 'cancelled' })).toBe(false);
  });

  it('is false for an actioned row even while still awaiting', () => {
    expect(isAcknowledgeable({ ack_state: 'awaiting', state: 'actioned' })).toBe(false);
  });

  it('defaults ack_state to awaiting, so a row with none is still gated on its state', () => {
    expect(isAcknowledgeable({ state: 'cancelled' })).toBe(false);
    expect(isAcknowledgeable({ state: 'raised' })).toBe(true);
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
