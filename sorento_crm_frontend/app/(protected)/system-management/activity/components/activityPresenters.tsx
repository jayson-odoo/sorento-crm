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
  { value: 'attachment', label: 'Attachment' },
];

export const ACTION_OPTIONS: { value: ActivityAction; label: string }[] = [
  { value: 'created', label: 'Created' },
  { value: 'updated', label: 'Updated' },
  { value: 'deleted', label: 'Deleted' },
  { value: 'imported', label: 'Imported' },
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
    case 'imported':
      return {
        label: 'imported',
        dotClass: 'bg-blue-500',
        textClass: 'text-blue-600 dark:text-blue-400',
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

// Activity timeline is Malaysia-time based (day grouping + labels), regardless
// of the viewer's browser timezone.
const MALAYSIA_TZ = 'Asia/Kuala_Lumpur';

/** YYYY-MM-DD for the instant in Malaysia time — the day-bucket key + day math. */
function dayKey(d: Date): string {
  // en-CA formats as YYYY-MM-DD.
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: MALAYSIA_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(d);
}

const DAY_MONTH_YEAR = new Intl.DateTimeFormat('en-GB', {
  timeZone: MALAYSIA_TZ,
  day: 'numeric',
  month: 'short',
  year: 'numeric',
});

const WEEKDAY = new Intl.DateTimeFormat('en-GB', { timeZone: MALAYSIA_TZ, weekday: 'long' });

/** "Today", "Yesterday", "Monday", or "28 Jun 2026" — all in Malaysia time. */
export function dayLabel(d: Date): string {
  // Diff the two MYT calendar-day keys (parsed as UTC midnight, so DST-free math).
  const diffDays = Math.round(
    (Date.parse(dayKey(new Date()) + 'T00:00:00Z') - Date.parse(dayKey(d) + 'T00:00:00Z')) /
      (24 * 60 * 60 * 1000),
  );
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
