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

const ASC = { id: 'asked_at', desc: false } as const;

function shape(out: ReturnType<typeof bucketTodo>) {
  return out.sections.map((sec) => ({
    key: sec.key,
    label: sec.label,
    days: sec.days.map((d) => ({ label: d.label, ids: d.asks.map((a) => a.id) })),
  }));
}

describe('bucketTodo (AC-ST113)', () => {
  it('builds Needs attention then Today, day groups oldest day first, and counts', () => {
    const done = [ask('e', '2026-09-20T01:00:00Z', { state: 'done', done_at: '2026-09-29T02:00:00Z', done_by: 'Sean' })];
    const out = bucketTodo(payload([JUST_BEFORE, AT_START, YESTERDAY, LAST_WEEK], done), ASC);
    expect(out.counts).toEqual({ open: 4, needs_attention: 3, done_today: 1 });
    expect(shape(out)).toEqual([
      {
        key: 'needs_attention',
        label: 'Needs attention',
        days: [
          { label: 'Tue 22 Sep', ids: ['d'] }, // the older day comes BEFORE Yesterday
          { label: 'Yesterday', ids: ['c', 'a'] }, // 20:00Z (04:00 MYT) then 15:59Z (23:59 MYT)
        ],
      },
      { key: 'today', label: 'Today', days: [{ label: 'Today', ids: ['b'] }] },
    ]);
    expect(out.done.map((a) => a.id)).toEqual(['e']);
  });

  it('splits at today_start exactly: 15:59Z is Needs attention, 16:00Z is Today', () => {
    expect(shape(bucketTodo(payload([JUST_BEFORE]), ASC)).map((s) => s.key)).toEqual(['needs_attention']);
    expect(shape(bucketTodo(payload([AT_START]), ASC)).map((s) => s.key)).toEqual(['today']);
  });

  it('omits a section and a day that has no open row', () => {
    expect(bucketTodo(payload([]), ASC).sections).toEqual([]);
    const out = bucketTodo(payload([LAST_WEEK, AT_START]), ASC);
    expect(out.sections.map((s) => s.days.map((d) => d.label))).toEqual([['Tue 22 Sep'], ['Today']]);
  });

  it('treats a created_at with no zone as UTC (the backend sends naive UTC)', () => {
    const out = bucketTodo(payload([ask('n1', '2026-09-28T15:59:00'), ask('n2', '2026-09-28T16:00:00')]), ASC);
    expect(out.counts.needs_attention).toBe(1);
    expect(shape(out).find((s) => s.key === 'today')!.days[0].ids).toEqual(['n2']);
  });

  it('counts an incoming and a console ask like any other (Q5 (a))', () => {
    const out = bucketTodo(
      payload([ask('i', '2026-09-29T01:00:00Z', { branch: 'incoming' }), ask('k', '2026-09-29T02:00:00Z', { source: 'console' })]),
      ASC,
    );
    expect(out.counts.open).toBe(2);
  });
});

describe('bucketTodo sort inside a day (AC-ST113)', () => {
  const day = (id: string, hour: number, over: Partial<StockAsk> = {}) =>
    ask(id, `2026-09-29T0${hour}:00:00Z`, over);
  const rows = [
    day('r1', 1, { customer_name: 'Charlie', product_code: 'SRT-B', branch: 'no_incoming' }),
    day('r2', 2, { customer_name: 'Alpha', product_code: 'SRT-C', branch: 'in_stock' }),
    day('r3', 3, { customer_name: 'Bravo', product_code: 'SRT-A', branch: 'too_big' }),
  ];
  const ids = (sort: { id: 'asked_at' | 'customer' | 'product' | 'branch'; desc: boolean }) =>
    bucketTodo(payload(rows), sort).sections[0].days[0].asks.map((a) => a.id);

  it('asked_at ascending is the default and puts the oldest first', () => {
    expect(ids({ id: 'asked_at', desc: false })).toEqual(['r1', 'r2', 'r3']);
    expect(bucketTodo(payload(rows)).sections[0].days[0].asks.map((a) => a.id)).toEqual(['r1', 'r2', 'r3']);
  });

  it('orders by customer A to Z, by product, and by branch label', () => {
    expect(ids({ id: 'customer', desc: false })).toEqual(['r2', 'r3', 'r1']);
    expect(ids({ id: 'product', desc: false })).toEqual(['r3', 'r1', 'r2']);
    // Branch labels: In stock, No stock no incoming, Too big.
    expect(ids({ id: 'branch', desc: false })).toEqual(['r2', 'r1', 'r3']);
  });

  it('desc reverses each order', () => {
    expect(ids({ id: 'asked_at', desc: true })).toEqual(['r3', 'r2', 'r1']);
    expect(ids({ id: 'customer', desc: true })).toEqual(['r1', 'r3', 'r2']);
  });

  it('sorts inside a day only: an older day stays before a newer day whatever the sort', () => {
    const out = bucketTodo(payload([LAST_WEEK, YESTERDAY, JUST_BEFORE]), { id: 'asked_at', desc: true });
    const days = out.sections[0].days;
    expect(days.map((d) => d.label)).toEqual(['Tue 22 Sep', 'Yesterday']);
    expect(days[1].asks.map((a) => a.id)).toEqual(['a', 'c']);
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
