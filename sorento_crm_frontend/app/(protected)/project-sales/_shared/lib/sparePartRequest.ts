/**
 * SPARE-PART-ORDER-REQUEST (`PLAN-spare-part-order-request-12nov.md`): the words and small
 * rules every screen of a spare part request shares. The request IS an order inquiry of
 * type `spare_part_request`; these keep the list, the OI page and the form saying the same
 * thing about it.
 */
import type { OrderInquiryType } from '../types/orderInquiry.types';

export const SPARE_PART_REQUEST_TYPE: OrderInquiryType = 'spare_part_request';
export const SPARE_PART_CREATE_PERMISSION = 'procurement.spare_part_requests.create';
/** The approver / purchasing read (crew ruling: mirrors `procurement.purchase_requests.view`). */
export const SPARE_PART_VIEW_PERMISSION = 'procurement.spare_part_requests.view';
/** Either spare part grant opens the list, the record and the OI page; the server scopes the
 *  rows (own, decidable, or every submitted one for an admin). */
export const SPARE_PART_READ_PERMISSIONS = [SPARE_PART_CREATE_PERMISSION, SPARE_PART_VIEW_PERMISSION];

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

/** G3: the request's own pill reads Draft / Pending approval / Rejected before approval and
 *  Approved after it, whatever purchasing has done with it since. */
export function sparePartRequestStatusLabel(state: string | null | undefined): string {
  if (state === 'cancelled') return 'Cancelled';
  return isPreApproval(state) ? sparePartStateLabel(state) : 'Approved';
}

/** The list's status filter. "Approved" covers every state after approval. */
export const SPARE_PART_STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'pending_approval', label: 'Pending approval' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'raised', label: 'Approved' },
];

/** The states a status filter pick sends: "Approved" is raised and done. */
export function sparePartFilterStates(picked: string[]): string[] {
  return picked.flatMap((state) => (state === 'raised' ? ['raised', 'actioned'] : [state]));
}

/** Row photos (server rule `can_write_photos`): the requester while it is a draft or rejected,
 *  the current approver while it is pending. The requester's edit while pending (G5) leaves
 *  the photos to the approver. */
export function canEditSparePartPhotos(header: {
  state?: string | null;
  can_edit?: boolean;
  can_decide?: boolean;
}): boolean {
  if (header.can_decide) return true;
  return Boolean(header.can_edit) && (header.state === 'draft' || header.state === 'rejected');
}

/** G3: the request's own pages. */
export const SPARE_PART_REQUESTS_PATH = '/procurement-management/spare-part-requests';

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
