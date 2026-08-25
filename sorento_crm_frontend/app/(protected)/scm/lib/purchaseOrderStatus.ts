/**
 * How a purchase order's status is WORDED on screen, in one place - the twin of
 * `salesOrderStatus.ts`, because the two books are the same document read from opposite
 * sides and a buyer who has learnt one screen has learnt the other.
 *
 * The stored values are not the sales book's `open`/`closed` pair: `purchase_orders.status`
 * holds `closed` (8,760), `active` (4), `received` (4) and `draft_recommendation` (2), and
 * there is NO `on_order` status at all - being on order is DERIVED (`is_on_order`: a live
 * status AND an open line with more ordered than received). So the pill reads the derived
 * fact rather than the raw word:
 *
 *   * still expecting goods  -> Outstanding
 *   * a live order with nothing left to come -> Completed
 *   * `draft` / `draft_recommendation` -> Draft (nobody has placed it yet)
 *   * `cancelled` -> Cancelled
 *
 * "Closed" and "Received" are gone as words. The captain's instruction was that closed
 * versus on order should read as Completed versus Outstanding, and a 2020 order stamped
 * `active` because the extract wrote it that way must not read as a live commitment.
 * The stored values are untouched; only the words are.
 */
import { getStatusBadgeVariant, type StatusBadgeVariant } from '@/lib/status-badge';

export interface PurchaseOrderStatusPill {
  label: string;
  variant: StatusBadgeVariant;
}

const OUTSTANDING: PurchaseOrderStatusPill = { label: 'Outstanding', variant: 'success' };
/** Not a failure - an order that finished - so it reads muted rather than the destructive
 *  the generic table gives a "closed" anything. Same choice the sales book made. */
const COMPLETED: PurchaseOrderStatusPill = { label: 'Completed', variant: 'secondary' };
/** The two the system status table already words this way, so the pill agrees with every
 *  other screen rather than painting a draft and a cancellation the same neutral grey. */
const DRAFT: PurchaseOrderStatusPill = { label: 'Draft', variant: 'warning' };
const CANCELLED: PurchaseOrderStatusPill = { label: 'Cancelled', variant: 'destructive' };

export function isDraftPurchaseOrder(status: string | null | undefined): boolean {
  const key = (status ?? '').trim().toLowerCase();
  return key === 'draft' || key === 'draft_recommendation';
}

/**
 * Whether this order still counts as incoming supply.
 *
 * `is_on_order` is the backend's own answer (`purchase_order_service._is_on_order`, the
 * same predicate `scm.po_ordered_v` uses), so it is trusted whenever it is present. The
 * fallback is only for a payload that predates the flag.
 */
export function countsAsOnOrder(po: {
  status: string;
  is_on_order?: boolean;
}): boolean {
  return po.is_on_order ?? (!isDraftPurchaseOrder(po.status) && po.status !== 'cancelled');
}

/** The header pill: one call, because the word and the colour are the same decision. */
export function purchaseOrderStatusPill(po: {
  status: string;
  is_on_order?: boolean;
}): PurchaseOrderStatusPill {
  const key = (po.status ?? '').trim().toLowerCase();
  if (isDraftPurchaseOrder(key)) return DRAFT;
  if (key === 'cancelled') return CANCELLED;
  return countsAsOnOrder(po) ? OUTSTANDING : COMPLETED;
}

/**
 * The per-line pill. A line is `open` while it is still owed and anything else once it has
 * left the book, which is the same two words one row down - the header total and the line
 * that makes it up must not be described in two vocabularies.
 */
export function purchaseOrderLineStatusPill(
  lineStatus: string | null | undefined,
): PurchaseOrderStatusPill {
  const key = (lineStatus ?? 'open').trim().toLowerCase();
  if (key === 'cancelled') return CANCELLED;
  return key === 'open' ? OUTSTANDING : COMPLETED;
}

/** Anything outside the four words above still renders through the system table rather
 *  than as a raw enum value. */
export function purchaseOrderFallbackVariant(
  value: string | null | undefined,
): StatusBadgeVariant {
  return getStatusBadgeVariant(value ?? '');
}

/**
 * The Status filter's options.
 *
 * Only the two the All / Outstanding / Completed toggle CANNOT reach. That toggle filters
 * on `outstanding`, which lumps a draft and a cancelled order in with the completed ones,
 * so the dropdown exists to pull those two back out - and offering "Received" or "Closed"
 * beside a column that never prints either word is how a filter and a column come to be
 * two names for one thing on one screen.
 */
export const PURCHASE_ORDER_STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'draft_recommendation', label: DRAFT.label },
  { value: 'cancelled', label: CANCELLED.label },
];
