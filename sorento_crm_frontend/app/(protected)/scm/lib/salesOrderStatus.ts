/**
 * How a sales order's status is WORDED on screen, in one place.
 *
 * The stored values are `open` and `closed` (2,854 and 11,006 orders; the lines carry the
 * same pair). AutoCount - the system this book is exported from, and the one the client
 * reads all day - calls those Outstanding and Completed, and "Open" beside a 2020 order
 * that shipped six years ago reads as a live commitment. The stored values are untouched;
 * only the words are.
 *
 * The other three (`partially_delivered`, `fulfilled`, `cancelled`) exist because
 * `create_do_from_so` writes them, so they keep their system-wide wording and colour rather
 * than being renamed on a guess about what AutoCount would call them.
 */
import { formatStatusLabel, getStatusBadgeVariant, type StatusBadgeVariant } from '@/lib/status-badge';

const SALES_ORDER_STATUS_LABEL: Record<string, string> = {
  open: 'Outstanding',
  closed: 'Completed',
};

/** Extra variants for the two words the system table does not know in this sense.
 *  `closed` is not a failure - it is an order that finished - so it reads muted rather
 *  than the destructive the generic table gives a "closed" anything. */
const SALES_ORDER_STATUS_VARIANT: Record<string, StatusBadgeVariant> = {
  open: 'success',
  closed: 'secondary',
};

export function salesOrderStatusLabel(value: string | null | undefined): string {
  const key = (value ?? '').trim().toLowerCase();
  return SALES_ORDER_STATUS_LABEL[key] ?? formatStatusLabel(value ?? '');
}

export function salesOrderStatusVariant(value: string | null | undefined): StatusBadgeVariant {
  const key = (value ?? '').trim().toLowerCase();
  return SALES_ORDER_STATUS_VARIANT[key] ?? getStatusBadgeVariant(value ?? '');
}

/**
 * Priority's own variant table.
 *
 * The system status table maps `normal` to success and `low` to destructive, which is right
 * for stock health and backwards for an order priority. Shared between the list column and
 * the detail field so the same word is not two colours on two screens; anything not named
 * here still falls through to the system table.
 */
export const SALES_ORDER_PRIORITY_VARIANTS: Record<string, StatusBadgeVariant> = {
  urgent: 'destructive',
  high: 'warning',
  medium: 'info',
  normal: 'secondary',
  low: 'secondary',
};

export function salesOrderPriorityVariant(value: string | null | undefined): StatusBadgeVariant {
  const key = (value ?? '').trim().toLowerCase();
  return SALES_ORDER_PRIORITY_VARIANTS[key] ?? getStatusBadgeVariant(value ?? '');
}

/**
 * The status filter's options, worded the same way the column is - a filter reading "Open"
 * over a column of "Outstanding" is two names for one thing on one screen.
 *
 * TWO statuses, because two is all this book holds: `open` (2,854) and `closed` (11,006).
 * The list used to offer Partially delivered, Fulfilled and Cancelled as well - three
 * choices that match nothing, so picking one empties the screen and the user is left
 * wondering which of their other filters did it. The three words still RENDER (see the
 * label table above) for any row that acquires them through `create_do_from_so`; they are
 * simply not offered as a filter until they exist.
 */
export const SALES_ORDER_STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'open', label: SALES_ORDER_STATUS_LABEL.open },
  { value: 'closed', label: SALES_ORDER_STATUS_LABEL.closed },
];
