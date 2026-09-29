/**
 * AC-ST113 (rewritten by AC-ST303) and AC-ST301, AC-ST302: `bucketTodo`, the ask -> landing
 * summary adapter and the asks field contract, with today_start = 2026-09-28T16:00Z (Malaysia
 * midnight of 29 Sep 2026). The server owns the boundary; nothing guesses a zone.
 */
import { describe, expect, it } from 'vitest';
import type { StockAsk } from '@/lib/stock-asks';
import {
  ASK_LANDING_FIELDS,
  askAnswerText,
  askToSummary,
  bucketTodo,
  type AskTodoPayload,
} from '@/lib/stock-asks-todo';
import { applyLandingFilters, sortLandingItems } from '@/app/(auth)/portal/lib/landing-fields';

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

const ASC = { key: 'created_at', dir: 'asc' } as const;

function shape(out: ReturnType<typeof bucketTodo>) {
  return out.sections.map((sec) => ({
    key: sec.key,
    label: sec.label,
    days: sec.days.map((d) => ({ ids: d.asks.map((a) => a.id) })),
  }));
}

describe('bucketTodo (AC-ST303)', () => {
  it('builds Needs attention then Today, ONE day group per section, oldest first, and counts', () => {
    const done = [ask('e', '2026-09-20T01:00:00Z', { state: 'done', done_at: '2026-09-29T02:00:00Z', done_by: 'Sean' })];
    const out = bucketTodo(payload([JUST_BEFORE, AT_START, YESTERDAY, LAST_WEEK], done), ASC);
    expect(out.counts).toEqual({ open: 4, needs_attention: 3, done_today: 1 });
    expect(shape(out)).toEqual([
      {
        key: 'needs_attention',
        label: 'Needs attention',
        // No per-day sub-groups: every open ask before today_start sits in one group, oldest first
        // (22 Sep 05:00Z, 27 Sep 20:00Z, 28 Sep 15:59Z).
        days: [{ ids: ['d', 'c', 'a'] }],
      },
      { key: 'today', label: 'Today', days: [{ ids: ['b'] }] },
    ]);
    expect(out.done.map((a) => a.id)).toEqual(['e']);
  });

  it('splits at today_start exactly: 15:59Z is Needs attention, 16:00Z is Today', () => {
    expect(shape(bucketTodo(payload([JUST_BEFORE]), ASC)).map((s) => s.key)).toEqual(['needs_attention']);
    expect(shape(bucketTodo(payload([AT_START]), ASC)).map((s) => s.key)).toEqual(['today']);
  });

  it('omits a section that has no open row', () => {
    expect(bucketTodo(payload([]), ASC).sections).toEqual([]);
    const out = bucketTodo(payload([LAST_WEEK, AT_START]), ASC);
    expect(out.sections.map((s) => [s.key, s.days.length])).toEqual([
      ['needs_attention', 1],
      ['today', 1],
    ]);
    expect(bucketTodo(payload([AT_START]), ASC).sections.map((s) => s.key)).toEqual(['today']);
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

describe('bucketTodo sort inside a section (AC-ST303, AC-ST304)', () => {
  const day = (id: string, hour: number, over: Partial<StockAsk> = {}) =>
    ask(id, `2026-09-29T0${hour}:00:00Z`, over);
  const rows = [
    day('r1', 1, { customer_name: 'Charlie' }),
    day('r2', 2, { customer_name: 'Alpha' }),
    day('r3', 3, { customer_name: 'Bravo' }),
  ];
  const ids = (sort?: { key: string; dir: 'asc' | 'desc' }) =>
    bucketTodo(payload(rows), sort as never).sections[0].days[0].asks.map((a) => a.id);

  it('the default sort is Created ascending: the oldest first', () => {
    expect(ids()).toEqual(['r1', 'r2', 'r3']);
    expect(ids({ key: 'created_at', dir: 'asc' })).toEqual(['r1', 'r2', 'r3']);
  });

  it('orders by customer A to Z and reverses on desc', () => {
    expect(ids({ key: 'customer_name', dir: 'asc' })).toEqual(['r2', 'r3', 'r1']);
    expect(ids({ key: 'customer_name', dir: 'desc' })).toEqual(['r1', 'r3', 'r2']);
    expect(ids({ key: 'created_at', dir: 'desc' })).toEqual(['r3', 'r2', 'r1']);
  });

  it('sorts inside a section only: Needs attention stays before Today whatever the sort', () => {
    const out = bucketTodo(payload([AT_START, LAST_WEEK, YESTERDAY]), { key: 'created_at', dir: 'desc' });
    expect(out.sections.map((s) => s.key)).toEqual(['needs_attention', 'today']);
    expect(out.sections[0].days[0].asks.map((a) => a.id)).toEqual(['c', 'd']);
  });
});

// ---- AC-ST301 -----------------------------------------------------------------------------

const ANSWER = 'SRT5674 x 50: yes, we have stock, please refer to your salesman to proceed.';

describe('askAnswerText (AC-ST301)', () => {
  it('strips the "CODE x Q:" prefix and upper-cases the first letter', () => {
    expect(askAnswerText(ask('t', '2026-09-29T01:00:00Z', { answer_summary: ANSWER }))).toBe(
      'Yes, we have stock, please refer to your salesman to proceed.',
    );
  });

  it.each([
    ['SRT-OLD x 1500: no stock and no incoming.', 'No stock and no incoming.'],
    ['CWCX604 x 300: the quantity is more than I can confirm.', 'The quantity is more than I can confirm.'],
    ['SRTW2000 x 150: no stock at the moment, ETA 19/10/2026.', 'No stock at the moment, ETA 19/10/2026.'],
  ])('reads %s as %s', (answer_summary, expected) => {
    expect(askAnswerText(ask('t', '2026-09-29T01:00:00Z', { answer_summary }))).toBe(expected);
  });

  it('returns an answer_summary without the prefix as it is', () => {
    expect(askAnswerText(ask('t', '2026-09-29T01:00:00Z', { answer_summary: 'answer' }))).toBe('answer');
    expect(askAnswerText(ask('t', '2026-09-29T01:00:00Z', { answer_summary: 'Already fine.' }))).toBe('Already fine.');
  });
});

describe('askToSummary (AC-ST301)', () => {
  it('maps an ask to the landing summary shape', () => {
    const row = ask('s1', '2026-09-29T01:00:00Z', {
      customer_name: 'Hock Lee Trading',
      contact_name: 'Ah Seng',
      product_code: 'SRT5674',
      quantity: 50,
      branch: 'in_stock',
      answer_summary: ANSWER,
      state: 'open',
    });
    expect(askToSummary(row)).toMatchObject({
      id: 's1',
      title: 'SRT5674 x 50',
      customer_name: 'Hock Lee Trading',
      contact_name: 'Ah Seng',
      created_at: '2026-09-29T01:00:00Z',
      status: 'open',
      answer: 'Yes, we have stock, please refer to your salesman to proceed.',
      branch: 'in_stock',
    });
  });

  it('carries a done ask as status done', () => {
    expect(askToSummary(ask('s2', '2026-09-29T01:00:00Z', { state: 'done' })).status).toBe('done');
  });
});

// ---- AC-ST302 -----------------------------------------------------------------------------

describe('ASK_LANDING_FIELDS (AC-ST302)', () => {
  it('is Customer (text), Answer (text), Asked (date), State (status)', () => {
    expect(ASK_LANDING_FIELDS.map((f) => [f.label, f.type])).toEqual([
      ['Customer', 'text'],
      ['Answer', 'text'],
      ['Asked', 'date'],
      ['State', 'status'],
    ]);
    expect(ASK_LANDING_FIELDS.find((f) => f.label === 'Customer')!.key).toBe('customer_name');
    expect(ASK_LANDING_FIELDS.find((f) => f.label === 'Asked')!.key).toBe('created_at');
  });

  const rowsOf = () => [
    ask('f1', '2026-09-29T03:00:00Z', { customer_name: 'Hock Lee Trading' }),
    ask('f2', '2026-09-27T03:00:00Z', { customer_name: 'Ah Huat Trading' }),
    ask('f3', '2026-09-28T03:00:00Z', { customer_name: 'Seri Indah Renovation' }),
    ask('f4', '2026-09-26T03:00:00Z', { customer_name: 'Hock Lee Trading' }),
  ].map((a) => askToSummary(a));

  it('a Customer filter keeps only that customer', () => {
    const kept = applyLandingFilters(rowsOf(), ASK_LANDING_FIELDS, { customer_name: 'Hock Lee Trading' });
    expect(kept.map((r) => r.id).sort()).toEqual(['f1', 'f4']);
  });

  it('sorts by Created oldest first and by Customer A to Z', () => {
    const oldest = sortLandingItems(rowsOf(), ASK_LANDING_FIELDS, { key: 'created_at', dir: 'asc' });
    expect(oldest.map((r) => r.id)).toEqual(['f4', 'f2', 'f3', 'f1']);
    const az = sortLandingItems(rowsOf(), ASK_LANDING_FIELDS, { key: 'customer_name', dir: 'asc' });
    expect(az.map((r) => r.customer_name)).toEqual([
      'Ah Huat Trading',
      'Hock Lee Trading',
      'Hock Lee Trading',
      'Seri Indah Renovation',
    ]);
  });
});
