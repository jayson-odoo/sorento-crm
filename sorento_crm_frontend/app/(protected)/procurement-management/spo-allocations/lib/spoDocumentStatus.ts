/**
 * How an SPO document (and its lines) are WORDED and coloured on screen, in one place -
 * the twin of `scm/lib/purchaseOrderStatus.ts`: the buyer reads this book the same way as
 * the purchase-order book (plan: "the page should read like the Purchase Orders page").
 */
import type { StatusBadgeVariant } from '@/lib/status-badge';
import type { PlanningSpan } from '../types/spoDocument.types';

export interface StatusPill {
  label: string;
  variant: StatusBadgeVariant;
}

/** Outstanding reads GREEN, matching the PO page's own pill (markup ruling, 1 Sep). */
const OUTSTANDING: StatusPill = { label: 'Outstanding', variant: 'success' };
const COMPLETED: StatusPill = { label: 'Completed', variant: 'secondary' };

export function spoDocumentStatusPill(status: 'outstanding' | 'completed'): StatusPill {
  return status === 'outstanding' ? OUTSTANDING : COMPLETED;
}

/** The four planning-visibility states a line can carry (Q4, UAC AC-6). */
const PLANNING_SPAN_PILL: Record<PlanningSpan, StatusPill> = {
  in_plan: { label: 'In plan', variant: 'success' },
  pool: { label: 'Pool', variant: 'info' },
  off: { label: 'Off', variant: 'secondary' },
  // A gap in the data, not a failure - the same reason "No location" reads warning
  // rather than destructive on every other unlocated-demand surface in this product.
  none: { label: 'No location', variant: 'warning' },
};

export function planningSpanBadge(span: PlanningSpan): StatusPill {
  return PLANNING_SPAN_PILL[span];
}

/** `dd/mm/yyyy`, or a plain dash for an unset date - never `NaN/NaN/NaN`. Dates render
 *  AS IS elsewhere in this feature (Q3): this only guards against a null input, it never
 *  masks or reinterprets what the date actually says. */
export function fmtEta(iso: string | null | undefined): string {
  if (!iso) return '-';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '-';
  const day = String(date.getDate()).padStart(2, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  return `${day}/${month}/${date.getFullYear()}`;
}

export function fmtQty(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '-';
  return value.toLocaleString();
}

/** Overdue days read amber once late, plain muted at zero - the same idiom the import-jobs
 *  "skipped" figure and the order KPI warning already use across the product. */
export function overdueClassName(days: number): string {
  return days > 0
    ? 'font-medium text-amber-600 dark:text-amber-500 tabular-nums'
    : 'text-muted-foreground tabular-nums';
}
