/**
 * Sales asks as a salesperson's to-do list (lane SALES-ASKS-TODO): the payload both mounts
 * (portal Customer asks, CRM Sales > Customer asks) receive, and the ONE pure function that
 * turns it into counts and groups. The server owns the day boundary (`today_start`); nothing
 * here guesses a timezone.
 *
 * Rules that may still move with the grill (plan section 3, marks `[Q<n> pending]`):
 * - Q3 grouping: `needs_attention` first, then `today`.
 * - Q4 overdue: needs attention = open and asked before `today_start`.
 */
import type { StockAsk } from '@/lib/stock-asks';

export interface AskTodoPayload {
  /** Malaysia midnight of today, as a UTC instant ("2026-09-28T16:00:00Z"). */
  today_start: string;
  /** state open, oldest first, capped at 500. */
  open: StockAsk[];
  /** state done with `done_at >= today_start`, newest first. */
  done_today: StockAsk[];
  truncated: boolean;
  /** CRM only: whose list this is. null when the caller is linked to no sales agent. */
  agent?: { code: string; name: string } | null;
}

/** One line of the manager's Agent select (`GET /api/v1/sales/customer-asks/agents`). */
export interface AskAgentSummary {
  /** The filter key, never shown. */
  agent_id: string;
  code: string;
  name: string;
  open: number;
  needs_attention: number;
}

export type TodoGroupKey = 'needs_attention' | 'today';

export interface TodoGroup {
  key: TodoGroupKey;
  label: string;
  asks: StockAsk[];
}

export interface BucketedTodo {
  counts: { open: number; needs_attention: number; done_today: number };
  groups: TodoGroup[];
  done: StockAsk[];
}

const DAY_MS = 86_400_000;
const MALAYSIA_OFFSET_MS = 8 * 3_600_000;
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Backend datetimes are naive UTC; treat a string with no zone as UTC. */
export function utcMs(value: string): number {
  return Date.parse(/(Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`);
}

function byCreated(a: StockAsk, b: StockAsk): number {
  return utcMs(a.created_at) - utcMs(b.created_at) || a.id.localeCompare(b.id);
}

/** Whole Malaysia days between the ask's day and today (1 = yesterday). 0 for today. */
export function daysBeforeToday(createdAt: string, todayStart: string): number {
  const start = utcMs(todayStart);
  const created = utcMs(createdAt);
  if (created >= start) return 0;
  return Math.ceil((start - created) / DAY_MS);
}

/** `Yesterday` or `Mon 22 Sep` (the months are named here: `Intl` en-GB spells it "Sept"). */
export function dayLabel(createdAt: string, todayStart: string): string {
  const days = daysBeforeToday(createdAt, todayStart);
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  const d = new Date(utcMs(createdAt) + MALAYSIA_OFFSET_MS);
  return `${WEEKDAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

/** "Yesterday", "2 days ago" ... for a Needs attention row; '' for a row from today. */
export function ageLabel(createdAt: string, todayStart: string): string {
  const days = daysBeforeToday(createdAt, todayStart);
  if (days === 0) return '';
  return days === 1 ? 'Yesterday' : `${days} days ago`;
}

export function bucketTodo(payload: AskTodoPayload): BucketedTodo {
  const start = utcMs(payload.today_start);
  const needsAttention = payload.open.filter((a) => utcMs(a.created_at) < start).sort(byCreated);
  const today = payload.open.filter((a) => utcMs(a.created_at) >= start).sort((a, b) => byCreated(b, a));

  const groups: TodoGroup[] = [];
  if (needsAttention.length) groups.push({ key: 'needs_attention', label: 'Needs attention', asks: needsAttention });
  if (today.length) groups.push({ key: 'today', label: 'Today', asks: today });

  return {
    counts: {
      open: payload.open.length,
      needs_attention: needsAttention.length,
      done_today: payload.done_today.length,
    },
    groups,
    done: payload.done_today,
  };
}
