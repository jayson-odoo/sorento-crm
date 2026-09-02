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
 * How the page says "show me everything" in the URL. An ABSENT `?ack=` opens on the
 * default, so a cleared filter needs a word of its own or a reload would put the default
 * straight back over the choice.
 */
export const ACK_ANY = 'all';

/**
 * What the Confirmed filter offers, in the order purchasing reads them (S3, review of
 * PR #471). No "To confirm" any more: a row is born acknowledged and a settle
 * auto-acknowledges again (G4), so nothing sits in `awaiting` (bar a pre-migration or
 * otherwise legacy row) for that option to mean anything about - the filter still
 * selects a genuinely rejected or changed row, which is what purchasing still looks up.
 */
export const ACK_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: 'acknowledged', label: ACK_LABELS.acknowledged },
  { value: 'changed', label: ACK_LABELS.changed },
  { value: 'rejected', label: ACK_LABELS.rejected },
];

export function ackStateOf(row: OrderInquiryAckFields): OrderInquiryAckState {
  const value = (row.ack_state ?? 'awaiting') as OrderInquiryAckState;
  return ACK_STATES.includes(value) ? value : 'awaiting';
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
