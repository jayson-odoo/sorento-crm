import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, within, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AgentConsole from './AgentConsole';

/**
 * AGENTIC-REASONING-VIS (PLAN-agentic-reasoning-vis-30oct.md), red first.
 *
 * `steps.reasoning: [{ round, text }]` and `steps.tool_calls[].round` come from the turn's stored trace. Inside
 * the Steps disclosure each round with reasoning gets its own collapsed `Thinking (round N)` button, placed
 * before that round's tool calls; the text shows only once it is opened. The reply bubble never carries it.
 */

const postAgentTurn = vi.fn();
const getAgentConversation = vi.fn();

vi.mock('../services/agentConsoleService', async () => {
  const actual = await vi.importActual<typeof import('../services/agentConsoleService')>(
    '../services/agentConsoleService',
  );
  return {
    ...actual,
    postAgentTurn: (...a: unknown[]) => postAgentTurn(...a),
    getAgentConversation: (...a: unknown[]) => getAgentConversation(...a),
    newAgentConversation: vi.fn(),
    confirmAgentAction: vi.fn(),
    cancelAgentAction: vi.fn(),
  };
});

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../../respond-contacts/services/respondContactOutboundService', () => ({
  getRespondContactsOutbound: vi.fn().mockResolvedValue({ data: [] }),
}));

const STORAGE_KEY = 'agent-console:last-contact';
const THOUGHT_1 = 'Look up the stock balance for the code first.';
const THOUGHT_2 = 'The balance is 12, so answer with that figure.';

const STEPS = {
  rounds: 2,
  prompt_tokens: 300,
  completion_tokens: 30,
  cached_tokens: 0,
  tool_calls: [
    { name: 'crm_inventory_stock_balance_list', status: 'ok', ms: 40, detail: 'Stock balance (query: ZZT1): 1 row', round: 1 },
  ],
  reasoning: [
    { round: 1, text: THOUGHT_1 },
    { round: 2, text: THOUGHT_2 },
  ],
};

function turn(over: Record<string, unknown> = {}) {
  return {
    turn_id: 't1',
    text: 'what is on hand?',
    reply_text: 'There are 12 units.',
    status: 'done',
    created_at: '2026-10-30T09:00:00Z',
    ...over,
  };
}

function renderConsole() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AgentConsole />
    </QueryClientProvider>,
  );
}

async function openSteps() {
  const disclosure = await screen.findByTestId('agent-steps');
  fireEvent.click(within(disclosure).getByRole('button', { name: 'Steps' }));
  return disclosure;
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ id: 'ZZT-1', label: 'Test Contact' }));
  postAgentTurn.mockReset();
  getAgentConversation.mockReset();
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe('the agent reasoning in Steps', () => {
  it('shows one collapsed Thinking per round, opened on demand', async () => {
    getAgentConversation.mockResolvedValue({ conversation_id: 'cv1', turns: [turn({ steps: STEPS })], pending_action: null });
    renderConsole();
    const disclosure = await openSteps();

    const first = within(disclosure).getByRole('button', { name: 'Thinking (round 1)' });
    const second = within(disclosure).getByRole('button', { name: 'Thinking (round 2)' });
    expect(first).toHaveAttribute('aria-expanded', 'false');
    expect(second).toHaveAttribute('aria-expanded', 'false');
    expect(disclosure).not.toHaveTextContent(THOUGHT_1);

    fireEvent.click(first);
    expect(first).toHaveAttribute('aria-expanded', 'true');
    expect(disclosure).toHaveTextContent(THOUGHT_1);
    expect(disclosure).not.toHaveTextContent(THOUGHT_2);
  });

  it("puts a round's thinking before that round's tool calls", async () => {
    getAgentConversation.mockResolvedValue({ conversation_id: 'cv1', turns: [turn({ steps: STEPS })], pending_action: null });
    renderConsole();
    const disclosure = await openSteps();
    const text = disclosure.textContent ?? '';
    const r1 = text.indexOf('Thinking (round 1)');
    const call = text.indexOf('Stock balance (query: ZZT1): 1 row');
    const r2 = text.indexOf('Thinking (round 2)');
    expect(r1).toBeGreaterThan(-1);
    expect(r1).toBeLessThan(call);
    expect(call).toBeLessThan(r2);
  });

  it('never shows the reasoning in the reply bubble', async () => {
    getAgentConversation.mockResolvedValue({ conversation_id: 'cv1', turns: [turn({ steps: STEPS })], pending_action: null });
    renderConsole();
    const disclosure = await openSteps();
    fireEvent.click(within(disclosure).getByRole('button', { name: 'Thinking (round 1)' }));
    const reply = screen.getByText('There are 12 units.');
    expect(reply.closest('p')).not.toHaveTextContent(THOUGHT_1);
  });

  it('keeps long reasoning wrapped inside the console', async () => {
    const long = `${'word '.repeat(400)}end`;
    getAgentConversation.mockResolvedValue({
      conversation_id: 'cv1',
      turns: [turn({ steps: { ...STEPS, reasoning: [{ round: 1, text: long }] } })],
      pending_action: null,
    });
    renderConsole();
    const disclosure = await openSteps();
    fireEvent.click(within(disclosure).getByRole('button', { name: 'Thinking (round 1)' }));
    const body = within(disclosure).getByTestId('agent-reasoning-text');
    expect(body.className).toMatch(/whitespace-pre-wrap/);
    expect(body.className).toMatch(/break-words/);
  });

  it('shows the thinking of a turn that has just been sent', async () => {
    getAgentConversation.mockResolvedValue({ conversation_id: 'cv1', turns: [], pending_action: null });
    postAgentTurn.mockResolvedValue({
      turn_id: 't9',
      conversation_id: 'cv1',
      reply_text: 'There are 12 units.',
      status: 'answered',
      limit_hit: null,
      rounds: 2,
      usage: { prompt_tokens: 300, completion_tokens: 30, cached_tokens: 0, calls: 2 },
      tool_calls: [],
      steps: STEPS,
    });
    renderConsole();
    fireEvent.change(await screen.findByLabelText('Message'), { target: { value: 'stock?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    const disclosure = await openSteps();
    expect(within(disclosure).getByRole('button', { name: 'Thinking (round 2)' })).toBeInTheDocument();
  });

  it("labels the forced final answer's thinking as such and puts it after the round's calls", async () => {
    const steps = {
      ...STEPS,
      rounds: 1,
      reasoning: [
        { round: 1, text: THOUGHT_1, final: false },
        { round: 1, text: THOUGHT_2, final: true },
      ],
    };
    getAgentConversation.mockResolvedValue({ conversation_id: 'cv1', turns: [turn({ steps })], pending_action: null });
    renderConsole();
    const disclosure = await openSteps();
    expect(within(disclosure).queryByRole('button', { name: 'Thinking (round 2)' })).toBeNull();
    const text = disclosure.textContent ?? '';
    const call = text.indexOf('Stock balance (query: ZZT1): 1 row');
    const final = text.indexOf('Thinking (final answer)');
    expect(text.indexOf('Thinking (round 1)')).toBeLessThan(call);
    expect(final).toBeGreaterThan(call);
  });

  it('an older turn without reasoning keeps the plain Steps list', async () => {
    const older = {
      rounds: 1,
      prompt_tokens: 10,
      completion_tokens: 1,
      cached_tokens: 0,
      tool_calls: [{ name: 'crm_inventory_stock_balance_list', status: 'ok', ms: 40, detail: 'Stock balance: 1 row' }],
    };
    getAgentConversation.mockResolvedValue({ conversation_id: 'cv1', turns: [turn({ steps: older })], pending_action: null });
    renderConsole();
    const disclosure = await openSteps();
    expect(within(disclosure).queryByRole('button', { name: /Thinking/ })).toBeNull();
    expect(disclosure).toHaveTextContent('Stock balance: 1 row');
  });
});
