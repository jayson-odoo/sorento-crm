/**
 * Shared presentation helpers for the Activity Timeline (labels, colours,
 * day grouping). Kept separate so the main component stays readable and these
 * mappings are trivially unit-testable in Phase-2.
 */
import type {
  ActivityAction,
  ActivityDayGroup,
  ActivityEntityType,
  ActivityItem,
} from '../types/activity.types';

export const ENTITY_TYPE_OPTIONS: {
  value: ActivityEntityType;
  label: string;
}[] = [
  { value: 'complaint', label: 'Complaint' },
  { value: 'order', label: 'Order' },
  { value: 'user', label: 'User' },
  { value: 'supplier', label: 'Supplier' },
  { value: 'promotion', label: 'Promotion' },
  { value: 'form', label: 'Form' },
  { value: 'ticket', label: 'Ticket' },
  { value: 'stock_inquiry', label: 'Stock Inquiry' },
  { value: 'purchase_request', label: 'Purchase Request' },
  { value: 'product', label: 'Product' },
];

export const ACTION_OPTIONS: { value: ActivityAction; label: string }[] = [
  { value: 'created', label: 'Created' },
  { value: 'updated', label: 'Updated' },
  { value: 'deleted', label: 'Deleted' },
];

export function entityTypeLabel(type: ActivityEntityType): string {
  return (
    ENTITY_TYPE_OPTIONS.find((o) => o.value === type)?.label ??
    type.replace(/_/g, ' ')
  );
}

/** Badge variant for the entity-type chip. */
export function entityBadgeVariant(
  type: ActivityEntityType,
): 'primary' | 'secondary' | 'info' | 'warning' {
  switch (type) {
    case 'complaint':
    case 'ticket':
      return 'warning';
    case 'order':
    case 'purchase_request':
    case 'stock_inquiry':
      return 'info';
    case 'user':
    case 'supplier':
      return 'secondary';
    default:
      return 'primary';
  }
}

/** Colour + verb for the action marker on the timeline. */
export function actionMeta(action: ActivityAction): {
  label: string;
  dotClass: string;
  textClass: string;
} {
  switch (action) {
    case 'created':
      return {
        label: 'created',
        dotClass: 'bg-green-500',
        textClass: 'text-green-600 dark:text-green-400',
      };
    case 'deleted':
      return {
        label: 'deleted',
        dotClass: 'bg-destructive',
        textClass: 'text-destructive',
      };
    case 'updated':
    default:
      return {
        label: 'updated',
        dotClass: 'bg-amber-500',
        textClass: 'text-amber-600 dark:text-amber-500',
      };
  }
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

function dayKey(d: Date): string {
  const y = d.getFullYear();
  const m = `${d.getMonth() + 1}`.padStart(2, '0');
  const day = `${d.getDate()}`.padStart(2, '0');
  return `${y}-${m}-${day}`;
}

const DAY_MONTH_YEAR = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
});

const WEEKDAY = new Intl.DateTimeFormat('en-GB', { weekday: 'long' });

/** "Today", "Yesterday", "Monday", or "28 Jun 2026" for older dates. */
export function dayLabel(d: Date): string {
  const today = startOfDay(new Date());
  const target = startOfDay(d);
  const diffDays = Math.round((today - target) / (24 * 60 * 60 * 1000));
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays > 1 && diffDays < 7) return WEEKDAY.format(d);
  return DAY_MONTH_YEAR.format(d);
}

/** Group already-sorted (newest-first) items into day buckets. */
export function groupByDay(items: ActivityItem[]): ActivityDayGroup[] {
  const groups: ActivityDayGroup[] = [];
  const index = new Map<string, ActivityDayGroup>();
  for (const item of items) {
    const d = new Date(item.changed_at);
    const key = dayKey(d);
    let group = index.get(key);
    if (!group) {
      group = { date_key: key, label: dayLabel(d), items: [] };
      index.set(key, group);
      groups.push(group);
    }
    group.items.push(item);
  }
  return groups;
}
