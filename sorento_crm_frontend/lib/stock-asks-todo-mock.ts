/**
 * PHASE 1 MOCK (lane SALES-ASKS-TODO): an in-memory store standing in for the to-do backend so the
 * UI can be tuned with no server. Both mounts' services (`services/stockAskService.ts` and
 * `app/(auth)/portal/lib/customer-asks-service.ts`) read and write this one store behind a
 * `PHASE1_MOCK` flag. Phase 2 deletes this file and flips the flag; nothing else imports it.
 *
 * The store mutates on Done / Reopen / Note, so the mock feels live. Times are seeded relative
 * to "now", so the seeded day always reads: 2 asks needing attention (2 days old, yesterday),
 * 3 from today, 1 done today, one incoming-branch ask that must NOT appear, one console ask.
 */
import type { StockAsk, StockAskPage, StockAskPatch } from '@/lib/stock-asks';
import type { AskAgentSummary, AskTodoPayload } from '@/lib/stock-asks-todo';

const DAY_MS = 86_400_000;
const MIN_MS = 60_000;
const HOUR_MS = 3_600_000;
const MALAYSIA_OFFSET_MS = 8 * HOUR_MS;

interface MockAsk extends StockAsk {
  agent_id: string;
}

const ME = { agent_id: 'mock-sean', code: 'SEAN I', name: 'Sean Ibrahim' };
const AMY = { agent_id: 'mock-amy', code: 'AMY L', name: 'Amy Lee' };

function iso(ms: number): string {
  return new Date(ms).toISOString();
}

function malaysiaMidnightMs(now: number): number {
  return Math.floor((now + MALAYSIA_OFFSET_MS) / DAY_MS) * DAY_MS - MALAYSIA_OFFSET_MS;
}

let seq = 0;
function ask(
  agent: { agent_id: string; code: string },
  createdMs: number,
  o: Partial<MockAsk> & Pick<MockAsk, 'customer_name' | 'contact_name' | 'product_code' | 'quantity' | 'branch' | 'answer_summary'>,
): MockAsk {
  seq += 1;
  return {
    id: `mock-ask-${String(seq).padStart(3, '0')}`,
    product_name: null,
    notified_agent: true,
    notify_skip_reason: null,
    state: 'open',
    source: 'live',
    note: null,
    created_at: iso(createdMs),
    updated_at: null,
    done_at: null,
    done_by: null,
    agent_id: agent.agent_id,
    agent_code: agent.code,
    ...o,
  };
}

function seed(todayStart: number): MockAsk[] {
  return [
    ask(ME, todayStart - 2 * DAY_MS + 11 * HOUR_MS, {
      customer_name: 'Hock Lee Trading',
      contact_name: 'Ah Seng',
      product_code: 'SRT5674',
      product_name: 'Soft rubber tile 5674',
      quantity: 50,
      branch: 'too_big',
      answer_summary: 'Only 12 in stock, 50 asked. Salesman to confirm a partial or a wait.',
    }),
    ask(ME, todayStart - DAY_MS + 15 * HOUR_MS, {
      customer_name: 'Kim Hong Hardware',
      contact_name: 'Mei Ling',
      product_code: 'BLT2210',
      product_name: 'Hex bolt 2210',
      quantity: 20,
      branch: 'no_incoming',
      answer_summary: 'Out of stock and nothing incoming.',
    }),
    ask(ME, todayStart + 10 * MIN_MS, {
      customer_name: 'Lim Brothers Sdn Bhd',
      contact_name: 'Jason Lim',
      product_code: 'CRT8801',
      product_name: 'Ceramic tile 8801',
      quantity: 100,
      branch: 'in_stock',
      answer_summary: '340 in stock at the main warehouse, 100 available now.',
    }),
    ask(ME, todayStart + 25 * MIN_MS, {
      customer_name: 'Hock Lee Trading',
      contact_name: 'Ah Seng',
      product_code: 'SRT5674',
      product_name: 'Soft rubber tile 5674',
      quantity: 30,
      branch: 'in_stock',
      answer_summary: '12 in stock, 30 asked. Enough for a first delivery.',
      notified_agent: false,
      notify_skip_reason: 'send_failed',
    }),
    ask(ME, todayStart + 40 * MIN_MS, {
      customer_name: 'Ah Huat Trading',
      contact_name: 'Huat',
      product_code: 'PLT1042',
      product_name: 'Plastic pallet 1042',
      quantity: 10,
      branch: 'in_stock',
      answer_summary: 'In stock, 10 available.',
      source: 'console',
      notified_agent: false,
      notify_skip_reason: null,
    }),
    ask(ME, todayStart - 3 * HOUR_MS, {
      customer_name: 'Tan Hardware Sdn Bhd',
      contact_name: 'Mr Tan',
      product_code: 'GLV0310',
      product_name: 'Work glove 0310',
      quantity: 200,
      branch: 'in_stock',
      answer_summary: '620 in stock, 200 available.',
      state: 'done',
      done_at: iso(todayStart + 5 * MIN_MS),
      done_by: ME.name,
      note: 'Called, will collect Thursday',
    }),
    // Must NOT appear on the to-do: the incoming branch is not the agent's to chase.
    ask(ME, todayStart + 15 * MIN_MS, {
      customer_name: 'Tan Hardware Sdn Bhd',
      contact_name: 'Mr Tan',
      product_code: 'SRT5674',
      product_name: 'Soft rubber tile 5674',
      quantity: 200,
      branch: 'incoming',
      answer_summary: 'A shipment of 800 lands next week.',
      notified_agent: false,
      notify_skip_reason: 'not_notified_branch',
    }),
    ask(AMY, todayStart - DAY_MS + 10 * HOUR_MS, {
      customer_name: 'Bright Lighting',
      contact_name: 'Daniel',
      product_code: 'LED330',
      product_name: 'LED panel 330',
      quantity: 60,
      branch: 'too_big',
      answer_summary: 'Only 24 in stock, 60 asked.',
    }),
    ask(AMY, todayStart + 30 * MIN_MS, {
      customer_name: 'Bright Lighting',
      contact_name: 'Daniel',
      product_code: 'LED331',
      product_name: 'LED panel 331',
      quantity: 12,
      branch: 'in_stock',
      answer_summary: '90 in stock, 12 available.',
    }),
  ];
}

export interface MockAskStore {
  /** `agent`: undefined = mine, 'all' = every agent, otherwise an agent_id. */
  todo(agent?: string): AskTodoPayload;
  agents(): AskAgentSummary[];
  patch(askId: string, patch: StockAskPatch, actor: string): StockAsk;
  /** The #1333 paged list (mine only): the portal badge and its Show done history. */
  list(params: { page: number; limit: number; q?: string; state?: string }): StockAskPage;
}

function createStore(): MockAskStore {
  const now = Date.now();
  const todayStart = malaysiaMidnightMs(now);
  const asks = seed(todayStart);

  const strip = ({ agent_id: _agentId, ...rest }: MockAsk, withAgent: boolean): StockAsk =>
    withAgent ? { ...rest } : { ...rest, agent_code: undefined };
  const isOpen = (a: MockAsk) => a.state === 'open' && a.branch !== 'incoming';
  const attention = (a: MockAsk) => Date.parse(a.created_at) < todayStart;

  return {
    todo(agent) {
      const scope = asks.filter((a) => (agent === 'all' ? true : a.agent_id === (agent ?? ME.agent_id)));
      const withAgent = agent === 'all';
      const chosen = [ME, AMY].find((x) => x.agent_id === (agent ?? ME.agent_id));
      return {
        today_start: iso(todayStart),
        open: scope
          .filter(isOpen)
          .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at))
          .map((a) => strip(a, withAgent)),
        done_today: scope
          .filter((a) => a.state === 'done' && a.done_at && Date.parse(a.done_at) >= todayStart)
          .sort((a, b) => Date.parse(b.done_at ?? '') - Date.parse(a.done_at ?? ''))
          .map((a) => strip(a, withAgent)),
        truncated: false,
        agent: agent === 'all' || !chosen ? null : { code: chosen.code, name: chosen.name },
      };
    },
    agents() {
      return [ME, AMY].map((ag) => {
        const open = asks.filter((a) => a.agent_id === ag.agent_id && isOpen(a));
        return {
          agent_id: ag.agent_id,
          code: ag.code,
          name: ag.name,
          open: open.length,
          needs_attention: open.filter(attention).length,
        };
      });
    },
    patch(askId, patch, actor) {
      const row = asks.find((a) => a.id === askId);
      if (!row) throw new Error('Ask not found');
      const at = iso(Date.now());
      if (patch.state === 'done' && row.state !== 'done') {
        row.state = 'done';
        row.done_at = at;
        row.done_by = actor;
      } else if (patch.state === 'open' && row.state !== 'open') {
        row.state = 'open';
        row.done_at = null;
        row.done_by = null;
      }
      if (patch.note !== undefined) row.note = patch.note || null;
      row.updated_at = at;
      return strip(row, false);
    },
    list({ page, limit, q, state }) {
      const needle = q?.trim().toLowerCase();
      const rows = asks
        .filter((a) => a.agent_id === ME.agent_id)
        .filter((a) => !state || a.state === state)
        .filter(
          (a) =>
            !needle ||
            [a.customer_name, a.contact_name, a.product_code].some((v) => v?.toLowerCase().includes(needle)),
        )
        .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
      const start = (page - 1) * limit;
      return {
        data: rows.slice(start, start + limit).map((a) => strip(a, false)),
        pagination: { total: rows.length, page, limit },
      };
    },
  };
}

let store: MockAskStore | null = null;

/** PHASE 1 MOCK: one store per browser session, shared by both mounts' services. */
export function getMockAskStore(): MockAskStore {
  if (!store) store = createStore();
  return store;
}
