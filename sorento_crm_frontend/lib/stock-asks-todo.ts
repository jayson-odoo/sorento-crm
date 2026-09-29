/**
 * Sales asks as a salesperson's to-do list (lane SALES-ASKS-TODO): the payload both mounts
 * (portal Customer asks, CRM Sales > Customer asks) receive, and the ONE pure function that
 * turns it into counts and groups. The server owns the day boundary (`today_start`); nothing
 * here guesses a timezone.
 *
 * Rules (owner rulings, plan section 0b):
 * - Q3 grouping: `Needs attention` pinned (one group per Malaysia day, oldest first), then `Today`.
 * - Q4 overdue: needs attention = open and asked before `today_start`.
 */
import { BRANCH_LABEL, type StockAsk } from '@/lib/stock-asks';

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

export type TodoSectionKey = 'needs_attention' | 'today';

/** One Malaysia calendar day inside a section. */
export interface TodoDay {
  /** `yyyy-mm-dd` on the Malaysia calendar. */
  key: string;
  /** `Today`, `Yesterday` or `Tue 22 Sep`. */
  label: string;
  asks: StockAsk[];
}

export interface TodoSection {
  key: TodoSectionKey;
  label: string;
  days: TodoDay[];
}

export type AskSortId = 'asked_at' | 'customer' | 'product' | 'branch';
export interface AskSort {
  id: AskSortId;
  desc: boolean;
}

export const DEFAULT_ASK_SORT: AskSort = { id: 'asked_at', desc: false };

/** The Sort select's five choices; the value is `<id>:<asc|desc>`. */
export const ASK_SORT_OPTIONS: { value: string; label: string; sort: AskSort }[] = [
  { value: 'asked_at:asc', label: 'Oldest first', sort: { id: 'asked_at', desc: false } },
  { value: 'asked_at:desc', label: 'Newest first', sort: { id: 'asked_at', desc: true } },
  { value: 'customer:asc', label: 'Customer A to Z', sort: { id: 'customer', desc: false } },
  { value: 'product:asc', label: 'Product A to Z', sort: { id: 'product', desc: false } },
  { value: 'branch:asc', label: 'Branch', sort: { id: 'branch', desc: false } },
];

export function sortToValue(sort: AskSort): string {
  return `${sort.id}:${sort.desc ? 'desc' : 'asc'}`;
}

/** A stored sort that is not one of the five choices reads as the default. */
export function normalizeSort(sort: { id?: unknown; desc?: unknown } | null | undefined): AskSort {
  if (!sort) return DEFAULT_ASK_SORT;
  const hit = ASK_SORT_OPTIONS.find((o) => o.sort.id === sort.id && o.sort.desc === Boolean(sort.desc));
  return hit ? hit.sort : DEFAULT_ASK_SORT;
}

export interface BucketedTodo {
  counts: { open: number; needs_attention: number; done_today: number };
  sections: TodoSection[];
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

/** Malaysia calendar date of an instant, `yyyy-mm-dd`. */
function malaysiaDayKey(ms: number): string {
  return new Date(ms + MALAYSIA_OFFSET_MS).toISOString().slice(0, 10);
}

function compareBy(sort: AskSort): (a: StockAsk, b: StockAsk) => number {
  const text = (a: string | null | undefined, b: string | null | undefined) =>
    (a ?? '').localeCompare(b ?? '', undefined, { sensitivity: 'base' });
  return (a, b) => {
    let primary = 0;
    if (sort.id === 'customer') primary = text(a.customer_name, b.customer_name);
    else if (sort.id === 'product') primary = text(a.product_code, b.product_code);
    else if (sort.id === 'branch') primary = text(BRANCH_LABEL[a.branch] ?? a.branch, BRANCH_LABEL[b.branch] ?? b.branch);
    const tie = byCreated(a, b);
    const order = primary || tie;
    return sort.desc ? -order : order;
  };
}

function toDays(asks: StockAsk[], todayStart: string, sort: AskSort): TodoDay[] {
  const byDay = new Map<string, StockAsk[]>();
  for (const a of asks) {
    const key = malaysiaDayKey(utcMs(a.created_at));
    byDay.set(key, [...(byDay.get(key) ?? []), a]);
  }
  const cmp = compareBy(sort);
  return [...byDay.entries()]
    .sort(([x], [y]) => x.localeCompare(y)) // oldest day first
    .map(([key, rows]) => ({
      key,
      label: dayLabel(rows[0].created_at, todayStart),
      asks: [...rows].sort(cmp),
    }));
}

/**
 * Counts and sections from one payload. `Needs attention` (pinned) holds every open ask asked
 * before `today_start`, split by Malaysia day, oldest day first; `Today` holds the rest as one
 * day. `sort` orders the rows inside every day. A day with no open row is absent. Every branch
 * counts, `incoming` and `console` included (Q5 (a)).
 */
export function bucketTodo(payload: AskTodoPayload, sort: AskSort = DEFAULT_ASK_SORT): BucketedTodo {
  const start = utcMs(payload.today_start);
  const before = payload.open.filter((a) => utcMs(a.created_at) < start);
  const today = payload.open.filter((a) => utcMs(a.created_at) >= start);

  const sections: TodoSection[] = [];
  if (before.length) {
    sections.push({
      key: 'needs_attention',
      label: 'Needs attention',
      days: toDays(before, payload.today_start, sort),
    });
  }
  if (today.length) {
    sections.push({ key: 'today', label: 'Today', days: toDays(today, payload.today_start, sort) });
  }

  return {
    counts: {
      open: payload.open.length,
      needs_attention: before.length,
      done_today: payload.done_today.length,
    },
    sections,
    done: payload.done_today,
  };
}
