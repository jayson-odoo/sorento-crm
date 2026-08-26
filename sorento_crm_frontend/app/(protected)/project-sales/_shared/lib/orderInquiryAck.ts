/**
 * The handshake, in the words the screen reads it by (`PLAN-scm-oi-handshake.md`).
 *
 * One place for the four states' labels, their colour and the sentence a cell prints, so
 * the column, the filter and the bulk bar cannot come to disagree about what "Changed"
 * means. Nothing here explains the feature - the words are the answer, not a lesson.
 */
import type {
  OrderInquiryAckFields,
  OrderInquiryAckState,
} from '../types/orderInquiry.types';

export const ACK_STATES: OrderInquiryAckState[] = [
  'awaiting',
  'acknowledged',
  'changed',
  'rejected',
];

export const ACK_LABELS: Record<OrderInquiryAckState, string> = {
  awaiting: 'Awaiting',
  acknowledged: 'Acknowledged',
  changed: 'Changed',
  rejected: 'Rejected',
};

/** The badge variants the rest of this screen already uses, one per state. */
export const ACK_VARIANTS: Record<OrderInquiryAckState, 'secondary' | 'success' | 'warning' | 'destructive'> = {
  awaiting: 'secondary',
  acknowledged: 'success',
  changed: 'warning',
  rejected: 'destructive',
};

export function ackStateOf(row: OrderInquiryAckFields): OrderInquiryAckState {
  const value = (row.ack_state ?? 'awaiting') as OrderInquiryAckState;
  return ACK_STATES.includes(value) ? value : 'awaiting';
}

/**
 * A row worth taking on: never read (or changed since it was), and still OWED.
 *
 * The second half is why this is not just a state test. A cancelled row was called off
 * and an actioned one was answered somewhere else - the same two `scm.committed_v` and
 * the three supply cards already drop - so acknowledging one takes on work nobody is
 * doing, and the cascade behind the press would link nothing for it anyway.
 */
export function isAcknowledgeable(row: OrderInquiryAckFields & { state?: string }): boolean {
  const ack = ackStateOf(row);
  if (ack !== 'awaiting' && ack !== 'changed') return false;
  return row.state !== 'cancelled' && row.state !== 'actioned';
}

/** A row purchasing has not refused, so there is still something to refuse. */
export function isRejectable(row: OrderInquiryAckFields): boolean {
  return ackStateOf(row) !== 'rejected';
}

/**
 * What the previous value was, off the note part 3's settle-in-place writes:
 * `Was 10 on 2026-08-25`, or `Was 10, no previous delivery date`.
 *
 * Parsed rather than stored a second time. The settle writes exactly one such phrase per
 * change and appends it, so the LAST match is the most recent one; anything that does not
 * match returns nothing at all rather than a guess, and the cell then prints the state
 * without a table.
 */
export function previousValueOf(note: string | null | undefined): {
  qty: string;
  date: string | null;
} | null {
  if (!note) return null;
  const matches = [...note.matchAll(/Was ([\d.,]+)(?: on (\d{4}-\d{2}-\d{2}))?/g)];
  const last = matches[matches.length - 1];
  if (!last) return null;
  return { qty: last[1], date: last[2] ?? null };
}
