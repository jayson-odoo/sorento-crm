import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, within, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AgentConsole from './AgentConsole';

/**
 * AGENTIC-P3 slice 6 (PLAN-agentic-p3-writes-30oct.md, "Slice 6: visibility and chat formatting"), red first.
 *
 * Assumed response shapes (the plan names the fields, not the types):
 * - `turns[].actions: [{ id, status, decided_at, decided_by_name, steps: [{ summary, status, error,
 *   changes: [{ record, field, before, after }] }] }]`, shown under the reply of the turn that proposed it
 *   (V2), the status badge using the existing labels (Done / Partly done / Not changed / Cancelled).
 * - A change line reads `<field>: <before> -> <after>` (V2).
 * - `turns[].steps.tool_calls[].detail` is a plain-words string; the Steps disclosure shows it in place of the
 *   bare `<label>: <status> (<ms> ms)` line (V3). A call without `detail` keeps the old line.
 * - Agent replies render through WhatsAppText: `*bold*` becomes <strong>, `- ` bullet lines stay lines (V5).
 */

const postAgentTurn = vi.fn();
const getAgentConversation = vi.fn();
const newAgentConversation = vi.fn();
const confirmAgentAction = vi.fn();
const cancelAgentAction = vi.fn();

vi.mock('../services/agentConsoleService', async () => {
  const actual = await vi.importActual<typeof import('../services/agentConsoleService')>(
    '../services/agentConsoleService',
  );
  return {
    ...actual,
    postAgentTurn: (...a: unknown[]) => postAgentTurn(...a),
    getAgentConversation: (...a: unknown[]) => getAgentConversation(...a),
    newAgentConversation: (...a: unknown[]) => newAgentConversation(...a),
    confirmAgentAction: (...a: unknown[]) => confirmAgentAction(...a),
    cancelAgentAction: (...a: unknown[]) => cancelAgentAction(...a),
  };
});

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../../respond-contacts/services/respondContactOutboundService', () => ({
  getRespondContactsOutbound: vi.fn().mockResolvedValue({ data: [] }),
}));

const STORAGE_KEY = 'agent-console:last-contact';
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}/;

function turn(over: Record<string, unknown> = {}) {
  return {
    turn_id: 't1',
    text: 'what is on hand?',
    reply_text: 'plain reply',
    status: 'done',
    created_at: '2026-10-30T09:00:00Z',
    ...over,
  };
}

function load(turns: unknown[]) {
  getAgentConversation.mockResolvedValue({ conversation_id: 'cv1', turns, pending_action: null });
}

function renderConsole() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AgentConsole />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ id: 'ZZT-1', label: 'Test Contact' }));
  postAgentTurn.mockReset();
  newAgentConversation.mockReset();
  getAgentConversation.mockReset();
  confirmAgentAction.mockReset();
  cancelAgentAction.mockReset();
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe('agent replies are formatted like chat mode (V5)', () => {
  it('renders *bold* as <strong> and keeps the bullet lines and the numbered list', async () => {
    load([
      turn({
        reply_text: '*Stock on hand*\n- SRTWT7445: 12 units\n- SRTWT7446: 4 units\n1. First\n2. Second',
      }),
    ]);
    renderConsole();

    const bold = await screen.findByText('Stock on hand');
    expect(bold.closest('strong')).not.toBeNull();
    expect(screen.getByTestId('agent-console-thread')).not.toHaveTextContent('*Stock on hand*');
    const thread = screen.getByTestId('agent-console-thread');
    for (const line of ['- SRTWT7445: 12 units', '- SRTWT7446: 4 units', '1. First', '2. Second']) {
      expect(thread.textContent).toContain(line);
    }
  });

  it('formats a reply that has just been sent, not only reloaded history', async () => {
    load([]);
    postAgentTurn.mockResolvedValue({
      turn_id: 't9',
      conversation_id: 'cv1',
      reply_text: 'There are *12* units.',
      status: 'answered',
      limit_hit: null,
      rounds: 1,
      usage: { prompt_tokens: 1, completion_tokens: 1, cached_tokens: 0, calls: 1 },
      tool_calls: [],
    });
    renderConsole();
    fireEvent.change(await screen.findByLabelText('Message'), { target: { value: 'stock?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    const bold = await screen.findByText('12');
    expect(bold.closest('strong')).not.toBeNull();
  });
});

describe('what was changed survives a reload (V2)', () => {
  const executed = {
    id: 'a1',
    status: 'executed',
    decided_at: '2026-10-30T09:05:00Z',
    decided_by_name: 'Fake Admin',
    steps: [
      {
        summary: 'Mark done on the ask for SRTWT7445 from Fake Trading',
        status: 'done',
        error: null,
        changes: [
          { record: 'SRTWT7445 for Fake Trading', field: 'Status', before: 'Open', after: 'Done' },
          { record: 'SRTWT7445 for Fake Trading', field: 'Note', before: 'none', after: 'Called the customer' },
        ],
      },
    ],
  };

  it('shows the status badge, each step summary and its Field: before -> after lines after a fresh load', async () => {
    load([turn({ reply_text: 'I have prepared the change.', actions: [executed] })]);
    renderConsole();

    const block = await screen.findByTestId('agent-actions');
    expect(within(block).getByText('Done')).toBeInTheDocument();
    expect(block).toHaveTextContent('Mark done on the ask for SRTWT7445 from Fake Trading');
    expect(block).toHaveTextContent('Status: Open -> Done');
    expect(block).toHaveTextContent('Note: none -> Called the customer');
    expect(block.textContent).not.toMatch(UUID);
  });

  it('shows a partly done action with the failed step error and no changes for it', async () => {
    load([
      turn({
        actions: [
          {
            id: 'a2',
            status: 'partial',
            decided_at: '2026-10-30T09:06:00Z',
            decided_by_name: 'Fake Admin',
            steps: [
              executed.steps[0],
              { summary: 'Mark done on the ask for SRTWT7446', status: 'failed', error: 'Stock ask not found.', changes: [] },
            ],
          },
        ],
      }),
    ]);
    renderConsole();

    const block = await screen.findByTestId('agent-actions');
    expect(within(block).getByText('Partly done')).toBeInTheDocument();
    expect(block).toHaveTextContent('Stock ask not found.');
    expect(block).toHaveTextContent('Status: Open -> Done');
  });

  it('shows a cancelled action as Cancelled with no change lines', async () => {
    load([
      turn({
        actions: [
          {
            id: 'a3',
            status: 'cancelled',
            decided_at: '2026-10-30T09:07:00Z',
            decided_by_name: 'Fake Admin',
            steps: [{ summary: 'Mark done on the ask for SRTWT7447', status: 'proposed', error: null, changes: [] }],
          },
        ],
      }),
    ]);
    renderConsole();

    const block = await screen.findByTestId('agent-actions');
    expect(within(block).getByText('Cancelled')).toBeInTheDocument();
    expect(block).toHaveTextContent('Mark done on the ask for SRTWT7447');
    expect(block.textContent).not.toContain('->');
  });

  it('shows nothing extra for a turn with no actions', async () => {
    load([turn({ reply_text: 'just an answer', actions: [] })]);
    renderConsole();

    await screen.findByText('just an answer');
    expect(screen.queryByTestId('agent-actions')).not.toBeInTheDocument();
  });
});

describe('the Steps disclosure speaks plain words (V3)', () => {
  const steps = {
    rounds: 2,
    prompt_tokens: 100,
    completion_tokens: 20,
    cached_tokens: 0,
    tool_calls: [
      { name: 'crm_customer_asks_list', status: 'ok', ms: 20, detail: 'Your customer asks: 2 rows' },
      { name: 'crm_customer_ask_update', status: 'denied', ms: 3, detail: 'Change an ask: refused, that ask is not yours' },
      { name: 'crm_report_ask', status: 'ok', ms: 120 },
    ],
  };

  it('shows each call detail when opened, and a call without detail keeps the old line', async () => {
    load([turn({ steps })]);
    renderConsole();

    const disclosure = await screen.findByTestId('agent-steps');
    fireEvent.click(within(disclosure).getByRole('button', { name: 'Steps' }));

    expect(disclosure).toHaveTextContent('Your customer asks: 2 rows');
    expect(disclosure).toHaveTextContent('Change an ask: refused, that ask is not yours');
    expect(disclosure).toHaveTextContent('Sales report: ok (120 ms)'); // no detail: unchanged
    expect(disclosure.textContent).not.toMatch(UUID);
  });
});
