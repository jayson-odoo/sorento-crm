/**
 * The handshake's own words (`PLAN-scm-oi-handshake.md`, AC-H2/AC-H4/AC-H5/AC-H8): one
 * place decides a row's label, whether it may be ticked or refused, and what its previous
 * value read - so the column, the checkbox and the bulk bar can never disagree.
 */
import { describe, expect, it } from 'vitest';
import {
  ACK_LABELS,
  ackStateOf,
  isAcknowledgeable,
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

describe('ACK_LABELS', () => {
  it('prints the label the column, the filter and the bulk bar all read', () => {
    expect(ACK_LABELS.awaiting).toBe('Awaiting');
    expect(ACK_LABELS.acknowledged).toBe('Acknowledged');
    expect(ACK_LABELS.changed).toBe('Changed');
    expect(ACK_LABELS.rejected).toBe('Rejected');
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

describe('previousValueOf', () => {
  it('reads qty and date off the settle-in-place note', () => {
    expect(previousValueOf('Was 10 on 2026-08-25')).toEqual({
      qty: '10',
      date: '2026-08-25',
    });
  });

  // DEFECT, reported not fixed: `previousValueOf`'s qty character class is
  // `[\d.,]+`, which is greedy across the comma the backend's own note format writes
  // right after the quantity in the no-previous-date case
  // (`app/services/project_order_inquiry_service.py:711`,
  // `f"Was {_qty_str(previous_qty)}, no previous delivery date"`). The capture group
  // therefore reads `"10,"` - comma included - rather than `"10"`, and the Was / Now
  // table (`OrderInquiryAckCell` -> `BoardChangeTable`) would print the trailing
  // comma on any CHANGED row whose line has no delivery date. Left `.fails` per the
  // tester's brief - report only, do not fix here.
  it.fails('reads a qty-only phrase with no previous delivery date', () => {
    expect(previousValueOf('Was 10, no previous delivery date')).toEqual({
      qty: '10',
      date: null,
    });
  });

  it('takes the LAST match when a row carries more than one change', () => {
    expect(
      previousValueOf('Was 10 on 2026-08-10; later: Was 20 on 2026-08-20'),
    ).toEqual({ qty: '20', date: '2026-08-20' });
  });

  it('returns nothing for a note with no such phrase, rather than guessing', () => {
    expect(previousValueOf('Auto: decision_confirm')).toBeNull();
  });

  it('returns nothing for a blank or absent note', () => {
    expect(previousValueOf(null)).toBeNull();
    expect(previousValueOf(undefined)).toBeNull();
    expect(previousValueOf('')).toBeNull();
  });
});
