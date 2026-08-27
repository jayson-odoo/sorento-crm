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

/**
 * The words the screen reads the handshake by (R7). "Confirm" replaced "Acknowledge"
 * everywhere a person can see it; the stored `ack_state` values and the permission slug
 * are untouched, so this is the only place the two vocabularies meet.
 */
export const ACK_LABELS: Record<OrderInquiryAckState, string> = {
  awaiting: 'To confirm',
  acknowledged: 'Confirmed',
  changed: 'Changed',
  rejected: 'Rejected',
};

/**
 * The default the page opens on (R3): awaiting AND changed, which to purchasing are one
 * question - nobody has said yes to this yet. Its own filter value rather than two,
 * because a to-do list is one press and not a multi-select.
 */
export const ACK_TO_CONFIRM = 'to_confirm';

/**
 * How the page says "show me everything" in the URL. An ABSENT `?ack=` opens on the
 * default, so a cleared filter needs a word of its own or a reload would put the default
 * straight back over the choice.
 */
export const ACK_ANY = 'all';

/** What the Confirmed filter offers, in the order purchasing reads them. */
export const ACK_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: ACK_TO_CONFIRM, label: ACK_LABELS.awaiting },
  { value: 'acknowledged', label: ACK_LABELS.acknowledged },
  { value: 'changed', label: ACK_LABELS.changed },
  { value: 'rejected', label: ACK_LABELS.rejected },
];

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
 * A row the bulk Reject may take (plan section 1, Reject): any OWED row, whether or not
 * it already carries links. Drafts are links on an unconfirmed row, so most rows in
 * front of purchasing are `placed` - refusing only unlinked ones would refuse almost
 * nothing. A cancelled or actioned row has nothing left to refuse, and a rejected one
 * has already been.
 */
export function isBulkRejectable(row: OrderInquiryAckFields & { state?: string }): boolean {
  if (!isRejectable(row)) return false;
  return row.state === 'raised' || row.state === 'partly_linked' || row.state === 'placed';
}

/**
 * What the row said before CS last amended it - the Was half of the Was / Now table.
 *
 * Read off the row's own `previous_qty` / `previous_delivery_date`, which the settle-in-place
 * writes (`project_order_inquiry_service._settle_row_in_place`). It used to be parsed back
 * out of the note beside them, and the note is a sentence for a person: "Was 10, no previous
 * delivery date" gave up the quantity as `10,` - the sentence's own comma read as part of
 * the number. A figure the screen prints is asked for as a figure.
 *
 * A row with no previous quantity returns nothing at all rather than a guess, and the cell
 * then prints the state without a table.
 */
export function previousValueOf(row: OrderInquiryAckFields): {
  qty: string;
  date: string | null;
} | null {
  const qty = row.previous_qty;
  if (qty === null || qty === undefined || qty === '') return null;
  return { qty: String(qty), date: row.previous_delivery_date ?? null };
}
