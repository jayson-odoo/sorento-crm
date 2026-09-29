/**
 * Sales asks as a salesperson's to-do list (lane SALES-ASKS-TODO): the payload both mounts
 * (portal Customer asks, CRM Sales > Customer asks) receive, and the pure functions that turn it
 * into sections and into the landing toolbar's shapes. The server owns the day boundary
 * (`today_start`); nothing here guesses a timezone.
 *
 * Rules (owner rulings, plan section 0b and 0c):
 * - Q3 grouping: one `Needs attention` section (open, asked before `today_start`), then `Today`.
 * - Q4 overdue: needs attention = open and asked before `today_start`.
 * - Q5: every branch counts, `incoming` and `console` included.
 */
import type { StockAsk } from '@/lib/stock-asks';
import {
  applyLandingFilters,
  sortLandingItems,
  type LandingField,
  type LandingFilters,
  type LandingSort,
} from '@/app/(auth)/portal/lib/landing-fields';
import type { PortalSubmissionSummary } from '@/app/(auth)/portal/lib/portal-client';

export interface AskTodoPayload {
  /** Malaysia midnight of today, as a UTC instant ("2026-09-28T16:00:00Z"). */
  today_start: string;
  /** state open, every branch, oldest first, capped at 500. */
  open: StockAsk[];
  /** state done with `done_at >= today_start`, newest first. */
  done_today: StockAsk[];
  truncated: boolean;
  /** CRM only: whose list this is. null when the caller is linked to no sales agent. */
  agent?: { code: string; name: string } | null;
}

/** One line of the Agent select (`GET /api/v1/sales/customer-asks/agents`). */
export interface AskAgentSummary {
  /** The filter key, never shown. */
  agent_id: string;
  code: string;
  name: string;
  open: number;
  needs_attention: number;
}

/** The chat around one ask (`GET .../customer-asks/{id}/conversation`). */
export interface AskConversationMessage {
  id: number;
  direction: 'in' | 'out';
  text: string;
  /** Naive UTC, like every backend datetime. */
  at: string;
}
export interface AskConversation {
  messages: AskConversationMessage[];
  /** The outgoing message that carries the ask's answer, when there is one. */
  ask_message_id: number | null;
  /** The contact's row id (respond_contacts.id), only for the CRM's "Open in Conversations" link (`?contact=` on the conversations page); absent on an empty answer. */
  contact_id?: string | null;
}

export type TodoSectionKey = 'needs_attention' | 'today';

/** One day group inside a section. Since the reshape a section holds exactly one. */
export interface TodoDay {
  key: string;
  label: string;
  asks: StockAsk[];
}

export interface TodoSection {
  key: TodoSectionKey;
  label: string;
  days: TodoDay[];
}

export interface BucketedTodo {
  counts: { open: number; needs_attention: number; done_today: number };
  sections: TodoSection[];
  done: StockAsk[];
}

// ---- the landing toolbar's view of an ask ------------------------------------------------

/** The landing summary shape plus the asks' own extra keys the field table reads. */
export type AskSummary = PortalSubmissionSummary & {
  contact_name: string | null;
  answer: string;
  branch: string;
};

/** "SRT5674 x 50: yes, we have stock" -> "Yes, we have stock". Without the prefix, as it is. */
export function askAnswerText(ask: Pick<StockAsk, 'answer_summary'>): string {
  const text = ask.answer_summary ?? '';
  const stripped = text.replace(/^\s*\S+ x \d+:\s*/, '');
  if (stripped === text) return text;
  return stripped.charAt(0).toUpperCase() + stripped.slice(1);
}

export function askProductText(ask: Pick<StockAsk, 'product_code' | 'quantity'>): string {
  return `${ask.product_code} x ${ask.quantity}`;
}

export function askToSummary(ask: StockAsk): AskSummary {
  return {
    id: ask.id,
    kind: 'customer_asks',
    title: askProductText(ask),
    reference: null,
    status: ask.state,
    is_editable: false,
    is_draft: false,
    created_at: ask.created_at,
    customer_name: ask.customer_name,
    contact_name: ask.contact_name,
    answer: askAnswerText(ask),
    branch: ask.branch,
  };
}

/**
 * The asks kind's field contract for `LandingToolbar` (Filter and Sort share it). The date field
 * is keyed `created_at`; its label is the word the Sort button prints.
 */
export const ASK_LANDING_FIELDS: LandingField[] = [
  { key: 'customer_name', label: 'Customer', type: 'text' },
  // Keyed `title` (the `CODE x Q` line of the summary), so Product filters and sorts by it.
  { key: 'title', label: 'Product', type: 'text' },
  { key: 'answer', label: 'Answer', type: 'text' },
  { key: 'created_at', label: 'Created', type: 'date' },
  { key: 'status', label: 'State', type: 'status' },
];

/** Oldest waits at the top. */
export const DEFAULT_ASK_SORT: LandingSort = { key: 'created_at', dir: 'asc' };

/** A stored or persisted sort that names no field of this kind reads as the default. */
export function normalizeAskSort(sort: { key?: unknown; dir?: unknown } | null | undefined): LandingSort {
  const key = sort?.key === 'asked_at' ? 'created_at' : sort?.key;
  if (typeof key !== 'string' || !ASK_LANDING_FIELDS.some((f) => f.key === key)) return DEFAULT_ASK_SORT;
  return { key, dir: sort?.dir === 'desc' ? 'desc' : 'asc' };
}

/** The remembered-preference row's `sorting[0]` <-> the toolbar's sort. */
export function askSortFromSorting(sorting: { id: string; desc?: boolean }[] | undefined): LandingSort {
  const first = sorting?.[0];
  return normalizeAskSort(first ? { key: first.id, dir: first.desc ? 'desc' : 'asc' } : null);
}

export function askSortToSorting(sort: LandingSort): { id: string; desc: boolean }[] {
  return [{ id: sort.key, desc: sort.dir === 'desc' }];
}

/**
 * The payload narrowed by the toolbar's filters and, on the portal, the landing search box.
 * Rows only leave; `today_start`, `truncated` and `agent` stay.
 */
export function filterTodoPayload(
  payload: AskTodoPayload,
  filters: LandingFilters,
  search = '',
): AskTodoPayload {
  const needle = search.trim().toLowerCase();
  const keep = (rows: StockAsk[]) => {
    const summaries = rows.map(askToSummary);
    const ids = new Set(applyLandingFilters(summaries, ASK_LANDING_FIELDS, filters).map((s) => s.id));
    return rows.filter(
      (a) =>
        ids.has(a.id) &&
        (!needle ||
          [a.customer_name, a.contact_name, a.product_code].some((v) => v?.toLowerCase().includes(needle))),
    );
  };
  return { ...payload, open: keep(payload.open), done_today: keep(payload.done_today) };
}

// ---- grouping ----------------------------------------------------------------------------

/** Backend datetimes are naive UTC; treat a string with no zone as UTC. */
export function utcMs(value: string): number {
  return Date.parse(/(Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`);
}

function ordered(asks: StockAsk[], sort: LandingSort): StockAsk[] {
  const byId = new Map(asks.map((a) => [a.id, a]));
  return sortLandingItems(asks.map(askToSummary), ASK_LANDING_FIELDS, sort).map((s) => byId.get(s.id)!);
}

/**
 * Counts and sections from one payload. `Needs attention` (pinned) holds every open ask asked
 * before `today_start`, `Today` the rest; `sort` orders the rows inside each. An empty section is
 * absent. Every branch counts (Q5 (a)).
 */
export function bucketTodo(payload: AskTodoPayload, sort: LandingSort = DEFAULT_ASK_SORT): BucketedTodo {
  const start = utcMs(payload.today_start);
  const before = payload.open.filter((a) => utcMs(a.created_at) < start);
  const today = payload.open.filter((a) => utcMs(a.created_at) >= start);

  const section = (key: TodoSectionKey, label: string, asks: StockAsk[]): TodoSection => ({
    key,
    label,
    days: [{ key, label, asks: ordered(asks, sort) }],
  });

  const sections: TodoSection[] = [];
  if (before.length) sections.push(section('needs_attention', 'Needs attention', before));
  if (today.length) sections.push(section('today', 'Today', today));

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
