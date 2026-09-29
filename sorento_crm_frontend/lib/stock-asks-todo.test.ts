/**
 * AC-ST113: `bucketTodo` and its labels, with today_start = 2026-09-28T16:00Z
 * (Malaysia midnight of 29 Sep 2026). The server owns the boundary; nothing guesses a zone.
 */
import { describe, expect, it } from 'vitest';
import type { StockAsk } from '@/lib/stock-asks';
import { ageLabel, bucketTodo, dayLabel, type AskTodoPayload } from '@/lib/stock-asks-todo';

const TODAY_START = '2026-09-28T16:00:00Z';

function ask(id: string, created_at: string, over: Partial<StockAsk> = {}): StockAsk {
  return {
    id,
    customer_name: `Customer ${id}`,
    contact_name: 'Ah Seng',
    product_code: `SRT-${id}`,
    product_name: null,
    quantity: 10,
    branch: 'in_stock',
    answer_summary: 'answer',
    notified_agent: true,
    notify_skip_reason: null,
    state: 'open',
    note: null,
    created_at,
    updated_at: null,
    ...over,
  };
}

const JUST_BEFORE = ask('a', '2026-09-28T15:59:00Z');
const AT_START = ask('b', '2026-09-28T16:00:00Z');
const YESTERDAY = ask('c', '2026-09-27T20:00:00Z');
const LAST_WEEK = ask('d', '2026-09-22T05:00:00Z');

function payload(open: StockAsk[], done_today: StockAsk[] = []): AskTodoPayload {
  return { today_start: TODAY_START, open, done_today, truncated: false };
}

describe('bucketTodo', () => {
  it('splits needs attention from today exactly at today_start and counts them', () => {
    const done = [ask('e', '2026-09-20T01:00:00Z', { state: 'done', done_at: '2026-09-29T02:00:00Z', done_by: 'Sean' })];
    const out = bucketTodo(payload([JUST_BEFORE, AT_START, YESTERDAY, LAST_WEEK], done));
    expect(out.counts).toEqual({ open: 4, needs_attention: 3, done_today: 1 });
    const byKey = Object.fromEntries(out.groups.map((g) => [g.key, g.asks.map((a) => a.id)]));
    expect(byKey.needs_attention).toEqual(expect.arrayContaining(['a', 'c', 'd']));
    expect(byKey.needs_attention).toHaveLength(3);
    expect(byKey.today).toEqual(['b']);
    expect(out.done.map((a) => a.id)).toEqual(['e']);
  });

  it('lists Needs attention before Today, with their headings', () => {
    const out = bucketTodo(payload([AT_START, JUST_BEFORE]));
    expect(out.groups.map((g) => g.label)).toEqual(['Needs attention', 'Today']);
  });

  it('omits a group with no rows', () => {
    expect(bucketTodo(payload([AT_START])).groups.map((g) => g.key)).toEqual(['today']);
    expect(bucketTodo(payload([JUST_BEFORE])).groups.map((g) => g.key)).toEqual(['needs_attention']);
    expect(bucketTodo(payload([])).groups).toEqual([]);
  });

  it('orders Needs attention oldest first and Today newest first', () => {
    const t1 = ask('t1', '2026-09-28T17:00:00Z');
    const t2 = ask('t2', '2026-09-29T02:00:00Z');
    const t3 = ask('t3', '2026-09-28T20:00:00Z');
    const out = bucketTodo(payload([JUST_BEFORE, LAST_WEEK, YESTERDAY, t1, t2, t3]));
    const byKey = Object.fromEntries(out.groups.map((g) => [g.key, g.asks.map((a) => a.id)]));
    expect(byKey.needs_attention).toEqual(['d', 'c', 'a']);
    expect(byKey.today).toEqual(['t2', 't3', 't1']);
  });

  it('treats a created_at with no zone as UTC (the backend sends naive UTC)', () => {
    const out = bucketTodo(payload([ask('n1', '2026-09-28T15:59:00'), ask('n2', '2026-09-28T16:00:00')]));
    expect(out.counts.needs_attention).toBe(1);
    expect(out.groups.find((g) => g.key === 'today')!.asks.map((a) => a.id)).toEqual(['n2']);
  });
});

describe('day and age labels', () => {
  it('labels an ask from the Malaysia day before today Yesterday', () => {
    expect(dayLabel(YESTERDAY.created_at, TODAY_START)).toBe('Yesterday');
    expect(dayLabel(JUST_BEFORE.created_at, TODAY_START)).toBe('Yesterday');
  });

  it('labels an earlier day with its weekday, date and month on the Malaysia calendar', () => {
    // 22 Sep 2026 is a Tuesday (the UAC text says "Mon 22 Sep"; the calendar wins).
    expect(dayLabel(LAST_WEEK.created_at, TODAY_START)).toBe('Tue 22 Sep');
  });

  it('labels a row from today Today', () => {
    expect(dayLabel(AT_START.created_at, TODAY_START)).toBe('Today');
  });

  it('gives an age on a needs-attention row and none on today', () => {
    expect(ageLabel(YESTERDAY.created_at, TODAY_START)).toBe('Yesterday');
    expect(ageLabel(LAST_WEEK.created_at, TODAY_START)).toMatch(/^\d+ days ago$/);
    expect(ageLabel(AT_START.created_at, TODAY_START)).toBe('');
  });
});
