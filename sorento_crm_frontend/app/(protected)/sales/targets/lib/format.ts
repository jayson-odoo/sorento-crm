/**
 * Display helpers for targets. Figures are RM or units by the target's metric; the unit is
 * named by the column or the Measures pill, so a cell shows the bare number.
 */
import type {
  TargetBasis,
  TargetMetric,
  TargetProductScope,
} from '../types/salesTarget.types';

const NUMBER = new Intl.NumberFormat('en-MY', { maximumFractionDigits: 2 });
const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/** `120000` -> `120,000`; `null` -> `-`. */
export function formatFigure(value: number | null | undefined): string {
  return value === null || value === undefined ? '-' : NUMBER.format(value);
}

/** `50` -> `50%`; `null` (no target, or a target of 0) -> `-`. */
export function formatPct(value: number | null | undefined): string {
  return value === null || value === undefined
    ? '-'
    : `${NUMBER.format(value)}%`;
}

/** `2026-10-01` -> `1 Oct 2026`. A calendar date, so no timezone conversion applies. */
export function shortDate(day: string | null | undefined): string {
  if (!day) return '';
  const [year, month, date] = day.split('-').map(Number);
  return `${date} ${MONTHS[month - 1]} ${year}`;
}

export const METRIC_LABEL: Record<TargetMetric, string> = {
  amount: 'Amount',
  quantity: 'Quantity',
};
export const BASIS_LABEL: Record<TargetBasis, string> = {
  ordered: 'Ordered',
  delivered: 'Delivered',
};
export const SCOPE_LABEL: Record<TargetProductScope, string> = {
  all: 'All products',
  categories: 'Categories',
  products: 'Products',
};

/** RM for an amount target, units for a quantity one. */
export function unitOf(metric: TargetMetric | null | undefined): string {
  return metric === 'quantity' ? 'units' : 'RM';
}

/** "All products", "3 categories", "1 product". */
export function scopeSummary(
  scope: TargetProductScope | null,
  count: number,
): string {
  if (!scope || scope === 'all') return 'All products';
  const noun = scope === 'categories' ? 'categor' : 'product';
  const plural =
    scope === 'categories'
      ? count === 1
        ? 'y'
        : 'ies'
      : count === 1
        ? ''
        : 's';
  return `${count} ${noun}${plural}`;
}

/** "Every 2 weeks", "Every month", or "Off". */
export function splitSummary(
  every: number | null,
  unit: string | null,
): string {
  if (!every || !unit) return 'Off';
  return every === 1 ? `Every ${unit}` : `Every ${every} ${unit}s`;
}

/** Today's `YYYY-MM-DD` and the last day of its month, as the modal's default range. */
export function endOfMonth(day: string): string {
  const [year, month] = day.split('-').map(Number);
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return `${day.slice(0, 8)}${String(last).padStart(2, '0')}`;
}

/** `2026-10-01` -> a local-midnight `Date`, for the shared `DatePicker` (which works in local days). */
export function dateFromYmd(day: string): Date | undefined {
  const [year, month, date] = day.split('-').map(Number);
  if (!year || !month || !date) return undefined;
  return new Date(year, month - 1, date);
}
