/**
 * SPARE-PART-ORDER-REQUEST (`PLAN-spare-part-order-request-12nov.md`): the words and small
 * rules every screen of a spare part request shares. The request IS an order inquiry of
 * type `spare_part_request`; these keep the list, the OI page and the form saying the same
 * thing about it.
 */
import type { OrderInquiryType } from '../types/orderInquiry.types';

export const SPARE_PART_REQUEST_TYPE: OrderInquiryType = 'spare_part_request';
export const SPARE_PART_CREATE_PERMISSION = 'procurement.spare_part_requests.create';

export const INQUIRY_TYPE_LABEL: Record<OrderInquiryType, string> = {
  sales_order: 'Sales order',
  spare_part_request: 'Spare part request',
};

export const INQUIRY_TYPE_OPTIONS = (Object.keys(INQUIRY_TYPE_LABEL) as OrderInquiryType[]).map(
  (value) => ({ value, label: INQUIRY_TYPE_LABEL[value] }),
);

/** A payload from before the type existed is a sales-order inquiry. */
export function inquiryTypeOf(header: { inquiry_type?: string | null }): OrderInquiryType {
  return header.inquiry_type === SPARE_PART_REQUEST_TYPE ? SPARE_PART_REQUEST_TYPE : 'sales_order';
}

export function inquiryTypeLabel(header: { inquiry_type?: string | null }): string {
  return INQUIRY_TYPE_LABEL[inquiryTypeOf(header)];
}

export function isSparePartInquiry(header: { inquiry_type?: string | null }): boolean {
  return inquiryTypeOf(header) === SPARE_PART_REQUEST_TYPE;
}

const STATE_LABEL: Record<string, string> = {
  draft: 'Draft',
  pending_approval: 'Pending approval',
  rejected: 'Rejected',
  raised: 'Raised',
  actioned: 'Done',
  cancelled: 'Cancelled',
};

export function sparePartStateLabel(state: string | null | undefined): string {
  return STATE_LABEL[state ?? ''] ?? 'Raised';
}

/** The states before purchasing sees the request. */
export function isPreApproval(state: string | null | undefined): boolean {
  return state === 'draft' || state === 'pending_approval' || state === 'rejected';
}

export function sparePartStateVariant(
  state: string | null | undefined,
): 'secondary' | 'warning' | 'destructive' | 'info' {
  if (state === 'pending_approval') return 'warning';
  if (state === 'rejected') return 'destructive';
  if (state === 'draft') return 'secondary';
  return 'info';
}

/** `10.0000` and `10` are the same quantity: a "was" mark only when the value moved. */
export function changedFrom(
  current: string | number | null | undefined,
  submitted: string | number | null | undefined,
): boolean {
  if (submitted == null || submitted === '' || current == null || current === '') return false;
  return Number(current) !== Number(submitted);
}

/** `10.0000` -> `10`, `12.5000` -> `12.5`. */
export function plainNumber(value: string | number | null | undefined): string {
  if (value == null || value === '') return '';
  const n = Number(value);
  return Number.isFinite(n) ? String(n) : String(value);
}
