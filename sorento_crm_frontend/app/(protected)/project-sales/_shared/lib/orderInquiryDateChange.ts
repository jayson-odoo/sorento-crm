/**
 * OI-ONE-DELIVERY-DATE (AC-E1..E3): the Was / Now of an OI row's delivery date, in the shape
 * the SO line's own change lightbox (`BoardChangeTable`) reads. `delivery_date` is the SO
 * line's date (Now) and `previous_delivery_date` the Was, both resolved by the backend; a row
 * whose Was is empty or equals the Now has no change to show.
 */
import type { BoardChangeAnnotation } from './boardChangeAnnotations';
import type { OrderInquiryWorklistRow } from '../types/orderInquiry.types';

export function orderInquiryDateChange(
  row: OrderInquiryWorklistRow,
): BoardChangeAnnotation | null {
  const was = row.previous_delivery_date ?? null;
  const now = row.delivery_date ?? null;
  if (!was || !now || was.slice(0, 10) === now.slice(0, 10)) return null;
  return {
    rowId: row.id,
    soNumber: row.so_number ?? '',
    lineNo: row.line_no ?? 0,
    itemCode: row.item_code ?? '',
    kind: now > was ? 'delayed' : 'advanced',
    closed: false,
    // The quantity is the row's on both sides: only the date moved, and the lightbox prints
    // only the fields that moved.
    was: { qty: row.qty, date: was, decision: null },
    now: { qty: row.qty, date: now, decision: null },
    suggestionLines: [],
    lateDays: null,
    shortfallQty: null,
    productChangedFrom: null,
    movedTransfer: null,
    projectLineId: null,
  };
}
