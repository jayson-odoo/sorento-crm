/**
 * The agent's behaviour inside the one console, carried over from the old Agent tab specs: a working
 * indicator while a turn runs, WhatsApp formatting of an agent reply (sent and reloaded), a refused
 * decision or withdraw shown in words inline, Undo reading the thread again, and a bubble keeping its
 * rounds, tool chips and limit text after a reload. Services are mocked as in ChatbotConsole.oneThread.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatbotConsole from './ChatbotConsole';
import { ActionRefusedError } from '../services/agentConsoleService';

const postConsoleTurn = vi.fn();
const getConsoleThread = vi.fn();
const confirmAgentAction = vi.fn();
const withdrawAgentStep = vi.fn();

vi.mock('../services/chatbotConsoleService', () => ({
  postConsoleTurn: (...a: unknown[]) => postConsoleTurn(...a),
  getConsolePromptVersions: vi.fn().mockResolvedValue([]),
  getConsoleThread: (...a: unknown[]) => getConsoleThread(...a),
  getConsoleMediaStatus: vi.fn(),
}));
vi.mock('../services/agentConsoleService', async () => {
  const actual = await vi.importActual<typeof import('../services/agentConsoleService')>('../services/agentConsoleService');
  return {
    ...actual,
    confirmAgentAction: (...a: unknown[]) => confirmAgentAction(...a),
    cancelAgentAction: vi.fn(),
    withdrawAgentStep: (...a: unknown[]) => withdrawAgentStep(...a),
    newAgentConversation: vi.fn().mockResolvedValue({ conversation_id: 'cv' }),
  };
});
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../respond-contacts/services/respondContactOutboundService', () => ({
  getRespondContactsOutbound: vi.fn().mockResolvedValue({ data: [] }),
}));
vi.mock('../../chat-history/services/chatbotTurnService', () => ({
  getChatbotTurns: vi.fn().mockResolvedValue({ items: [], next_cursor: null, retry_available: false }),
}));

const AGENT_ROUTE = { side: 'agent', reason: 'classified', score: 0.9, model: 'jev-1.14.0', ms: 100 };
const EMPTY_STEPS = { rounds: 0, prompt_tokens: 0, completion_tokens: 0, cached_tokens: 0, tool_calls: [], reasoning: [] };
const SUMMARY = 'Approve purchase request PR-1 for Example Trading.';
const inAMinute = () => new Date(Date.now() + 60_000).toISOString().replace('Z', '');

function agentTurn(over: Record<string, unknown> = {}) {
  return {
    turn_id: 't1', side: 'agent', user_text: 'what is on hand?', reply_text: 'There are 12 units.',
    route: AGENT_ROUTE, steps: EMPTY_STEPS, actions: [], created_at: '2026-10-30T09:00:00Z', ...over,
  };
}
const thread = (turns: unknown[], pending: unknown = null) => ({ turns, pending_action: pending });
function renderConsole() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChatbotConsole />
    </QueryClientProvider>,
  );
}
function send(text: string) {
  const box = screen.getByPlaceholderText('Ask, or attach voice/image');
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: 'Enter' });
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  [postConsoleTurn, getConsoleThread, confirmAgentAction, withdrawAgentStep].forEach((m) => m.mockReset());
  getConsoleThread.mockResolvedValue(thread([]));
  window.localStorage.clear();
  window.localStorage.setItem('chatbot-console:last-contact', JSON.stringify({ id: 'ZZT-1', label: 'Test Contact' }));
});
afterEach(() => cleanup());

describe('a turn that is running', () => {
  it('shows the working indicator until the reply lands, with the question already in the thread', async () => {
    let finish: (v: unknown) => void = () => {};
    postConsoleTurn.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    renderConsole();
    send('stock of SRTWT7445?');
    expect(await screen.findByTestId('chatbot-console-typing')).toBeInTheDocument();
    expect(screen.getByText('stock of SRTWT7445?')).toBeInTheDocument();
    finish({
      turn_id: 'a9', branch_kind: null, reply_text: 'There are 12 units.', quick_replies: [], send_messages: [],
      session_vars: null, trace_summary: {}, route: AGENT_ROUTE,
      agent: { turn_id: 'a9', status: 'limited', limit_hit: 'rounds', rounds: 2, pending_action: null, actions: [],
        steps: { ...EMPTY_STEPS, rounds: 2, tool_calls: [{ name: 'crm_inventory_stock_balance_list', status: 'ok', ms: 10, round: 1 }] } },
    });
    expect(await screen.findByText('There are 12 units.')).toBeInTheDocument();
    expect(screen.queryByTestId('chatbot-console-typing')).not.toBeInTheDocument();
    const meta = screen.getByTestId('agent-reply-meta');
    expect(meta).toHaveTextContent('2 rounds');
    expect(meta).toHaveTextContent('Stock balance: ok');
    expect(meta).toHaveTextContent('Stopped: rounds limit');
  });
});

describe('agent replies are formatted like chat (WhatsApp text)', () => {
  it('renders *bold* as strong and keeps bullet and numbered lines, on a reloaded turn', async () => {
    getConsoleThread.mockResolvedValue(
      thread([agentTurn({ reply_text: '*Stock on hand*\n- SRTWT7445: 12 units\n- SRTWT7446: 4 units\n1. First\n2. Second' })]),
    );
    renderConsole();
    const bold = await screen.findByText('Stock on hand');
    expect(bold.closest('strong')).not.toBeNull();
    const text = screen.getByTestId('chatbot-console-thread').textContent ?? '';
    expect(text).not.toContain('*Stock on hand*');
    for (const line of ['- SRTWT7445: 12 units', '- SRTWT7446: 4 units', '1. First', '2. Second']) expect(text).toContain(line);
  });

  it('formats a reply that has just been sent', async () => {
    postConsoleTurn.mockResolvedValue({
      turn_id: 'a9', branch_kind: null, reply_text: 'There are *12* units.', quick_replies: [], send_messages: [],
      session_vars: null, trace_summary: {}, route: AGENT_ROUTE,
      agent: { turn_id: 'a9', status: 'answered', pending_action: null, steps: EMPTY_STEPS, actions: [] },
    });
    renderConsole();
    send('stock?');
    expect((await screen.findByText('12')).closest('strong')).not.toBeNull();
  });
});

describe('a reloaded agent bubble keeps its chips', () => {
  it('shows rounds, tool chips and the stop reason from the stored steps and limit', async () => {
    getConsoleThread.mockResolvedValue(
      thread([
        agentTurn({
          steps: { ...EMPTY_STEPS, rounds: 3, tool_calls: [{ name: 'crm_report_ask', status: 'ok', ms: 5, round: 1 }] },
          rounds: 3, limit_hit: 'seconds',
        }),
      ]),
    );
    renderConsole();
    const meta = await screen.findByTestId('agent-reply-meta');
    expect(meta).toHaveTextContent('3 rounds');
    expect(meta).toHaveTextContent('Sales report: ok');
    expect(meta).toHaveTextContent('Stopped: time limit');
  });

  it('has no Steps disclosure for a turn that stored none', async () => {
    getConsoleThread.mockResolvedValue(thread([agentTurn()]));
    renderConsole();
    await screen.findByText('There are 12 units.');
    expect(screen.queryByTestId('agent-steps')).not.toBeInTheDocument();
  });
});

describe('decisions and withdraws', () => {
  const withWaiting = (extra: Record<string, unknown> = {}) =>
    thread([
      agentTurn({
        actions: [
          {
            id: 'a1', status: 'executed', decided_at: '2026-10-30T09:01:00Z', decided_by_name: 'Agent User',
            steps: [{ summary: SUMMARY, status: 'done', error: null, changes: [], waiting: { commit_at: inAMinute(), window_seconds: 60 }, ...extra }],
          },
        ],
      }),
    ]);

  it('a refused decision shows its reason in words inline', async () => {
    getConsoleThread.mockResolvedValue(
      thread([agentTurn({ turn_id: 't1' })], { id: 'a1', turn_id: 't1', lines: ['Mark it done', 'And this'], expires_at: '2099-01-01T00:00:00Z' }),
    );
    confirmAgentAction.mockRejectedValue(new ActionRefusedError('expired'));
    renderConsole();
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm 2 changes' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This proposal expired. Ask again to get a fresh one.');
  });

  it('Undo withdraws that step and then reads the thread again', async () => {
    getConsoleThread.mockResolvedValueOnce(withWaiting());
    getConsoleThread.mockResolvedValue(thread([agentTurn({ actions: [{ id: 'a1', status: 'executed', decided_at: null, decided_by_name: null, steps: [{ summary: SUMMARY, status: 'withdrawn', error: null, changes: [], waiting: null }] }] })]));
    withdrawAgentStep.mockResolvedValue({ action_id: 'a1', status: 'executed', reply_text: 'Withdrawn.', steps: [] });
    renderConsole();
    fireEvent.click(await screen.findByRole('button', { name: /undo/i }));
    await waitFor(() => expect(withdrawAgentStep).toHaveBeenCalledWith('ZZT-1', 'a1', 0));
    await waitFor(() => expect(screen.queryByTestId('agent-step-waiting')).toBeNull());
    expect(getConsoleThread.mock.calls.length).toBeGreaterThan(1);
  });

  it('a refused withdraw shows the reason in words inline', async () => {
    getConsoleThread.mockResolvedValue(withWaiting());
    withdrawAgentStep.mockRejectedValue(new ActionRefusedError('applied'));
    renderConsole();
    fireEvent.click(await screen.findByRole('button', { name: /undo/i }));
    expect(await within(document.body).findByText('That change already applied, so it can no longer be withdrawn.')).toBeTruthy();
  });
});
