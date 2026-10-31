/**
 * AGENTIC-UNIFY console: one conversation instead of Bot and Agent tabs.
 * UAC AC-1 to AC-7, AC-9 (pill word), AC-13, AC-14 (reload), AC-16, AC-20.
 * AC-21 (375 and 1280 layout) and AC-22 (no new on-screen explanation) are the browser pass, not vitest.
 *
 * Red first. Names this file relies on (the coder may rename them, then this file follows):
 *   - `getConsoleThread(contactRespondId, runId)` in `../services/chatbotConsoleService`, resolving to
 *     `{ turns, pending_action }` as `GET /console/thread` returns it.
 *   - `newAgentConversation(contactRespondId)`, `confirmAgentAction`, `cancelAgentAction` and
 *     `withdrawAgentStep` stay in `../services/agentConsoleService`.
 *   - The composer toggle has an accessible name containing "Agent"; the button that starts afresh is
 *     named "New conversation" (there is no Reset).
 * The services are mocked as the neighbouring specs do; the HTTP contract is the backend's
 * `tests/chatbot/agent/test_console_one_thread.py`.
 */
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatbotConsole from './ChatbotConsole';
import { routeReasonWords } from './RoutePill';

const postConsoleTurn = vi.fn();
const getConsolePromptVersions = vi.fn();
const getConsoleThread = vi.fn();
const confirmAgentAction = vi.fn();
const cancelAgentAction = vi.fn();
const withdrawAgentStep = vi.fn();
const newAgentConversation = vi.fn();
const getRespondContactsOutbound = vi.fn();
const getConsoleMediaStatus = vi.fn();
const toastError = vi.fn();

vi.mock('../services/chatbotConsoleService', () => ({
  postConsoleTurn: (...a: unknown[]) => postConsoleTurn(...a),
  getConsolePromptVersions: (...a: unknown[]) => getConsolePromptVersions(...a),
  getConsoleThread: (...a: unknown[]) => getConsoleThread(...a),
  getConsoleMediaStatus: (...a: unknown[]) => getConsoleMediaStatus(...a),
}));
vi.mock('../services/agentConsoleService', async () => {
  const actual = await vi.importActual<typeof import('../services/agentConsoleService')>(
    '../services/agentConsoleService',
  );
  return {
    ...actual,
    confirmAgentAction: (...a: unknown[]) => confirmAgentAction(...a),
    cancelAgentAction: (...a: unknown[]) => cancelAgentAction(...a),
    withdrawAgentStep: (...a: unknown[]) => withdrawAgentStep(...a),
    newAgentConversation: (...a: unknown[]) => newAgentConversation(...a),
  };
});
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: (...a: unknown[]) => toastError(...a) } }));
vi.mock('../../respond-contacts/services/respondContactOutboundService', () => ({
  getRespondContactsOutbound: (...a: unknown[]) => getRespondContactsOutbound(...a),
}));
vi.mock('../../chat-history/services/chatbotTurnService', () => ({
  getChatbotTurns: vi.fn().mockResolvedValue({ items: [], next_cursor: null, retry_available: false }),
}));

const CONTACT_KEY = 'chatbot-console:last-contact';
const STOCK = 'crm_inventory_stock_balance_list';

const EMPTY_STEPS = { rounds: 0, prompt_tokens: 0, completion_tokens: 0, cached_tokens: 0, tool_calls: [], reasoning: [] };
const AGENT_STEPS = {
  rounds: 1,
  prompt_tokens: 100,
  completion_tokens: 10,
  cached_tokens: 0,
  tool_calls: [{ name: STOCK, status: 'ok', ms: 14, detail: 'Read 12 units of stock', round: 1 }],
  reasoning: [{ round: 1, text: 'Checking the stock balance first.', final: false }],
};
const CHAT_ROUTE = { side: 'chat', reason: 'classified', score: 0.9, model: 'jev-1.14.0', ms: 300 };
const AGENT_ROUTE = { side: 'agent', reason: 'classified', score: 0.92, model: 'jev-1.14.0', ms: 412 };

function chatTurn(id: string, user: string, reply: string, at: string, extra: Record<string, unknown> = {}) {
  return {
    turn_id: id, side: 'chat', user_text: user, reply_text: reply, route: CHAT_ROUTE,
    steps: EMPTY_STEPS, actions: [], created_at: at, ...extra,
  };
}
function agentTurn(id: string, user: string, reply: string, at: string, extra: Record<string, unknown> = {}) {
  return {
    turn_id: id, side: 'agent', user_text: user, reply_text: reply, route: AGENT_ROUTE,
    steps: AGENT_STEPS, actions: [], created_at: at, ...extra,
  };
}
const thread = (turns: unknown[], pending: unknown = null) => ({ turns, pending_action: pending });

/** A turn response from `POST /console/turn`. */
function turnResponse(reply: string, over: Record<string, unknown> = {}) {
  return {
    turn_id: 't-live', branch_kind: 'business_query', reply_text: reply, quick_replies: [], send_messages: [],
    session_vars: {}, trace_summary: { tool: null, args_short: null, crossdomain_rungs: [], reveals_dropped: [] },
    route: CHAT_ROUTE, ...over,
  };
}
function agentResponse(reply: string, over: Record<string, unknown> = {}) {
  return turnResponse(reply, {
    turn_id: 'a-live', branch_kind: null, route: AGENT_ROUTE,
    agent: { turn_id: 'a-live', status: 'answered', pending_action: null, steps: AGENT_STEPS, actions: [] },
    ...over,
  });
}

function renderConsole() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChatbotConsole />
    </QueryClientProvider>,
  );
}
const box = () => screen.getByPlaceholderText('Ask, or attach voice/image') as HTMLTextAreaElement;
function send(text: string) {
  fireEvent.change(box(), { target: { value: text } });
  fireEvent.keyDown(box(), { key: 'Enter' });
}
const bubbleOf = (text: string): HTMLElement =>
  screen.getAllByText(text)[0].closest('[data-testid="message-bubble"]') as HTMLElement;

/** The composer's Agent toggle: any switch, checkbox or button named "Agent" that is not a route pill. */
function agentToggle(): HTMLElement {
  const found = ['switch', 'checkbox', 'button']
    .flatMap((role) => screen.queryAllByRole(role, { name: /agent/i }))
    .filter((el) => !el.closest('[data-testid="message-bubble"]'));
  expect(found.length, 'an Agent toggle in the composer').toBeGreaterThan(0);
  return found[0];
}
const isOn = (el: HTMLElement) =>
  el.getAttribute('aria-pressed') === 'true' ||
  el.getAttribute('aria-checked') === 'true' ||
  ['on', 'checked'].includes(el.getAttribute('data-state') ?? '');
const isDisabled = (el: HTMLElement) => el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true';
const threadCalls = () => getConsoleThread.mock.calls.map((c) => JSON.stringify(c));

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  [postConsoleTurn, getConsolePromptVersions, getConsoleThread, confirmAgentAction, cancelAgentAction,
    withdrawAgentStep, newAgentConversation, getRespondContactsOutbound, getConsoleMediaStatus, toastError].forEach((m) => m.mockReset());
  getConsolePromptVersions.mockResolvedValue([]);
  getConsoleThread.mockResolvedValue(thread([]));
  newAgentConversation.mockResolvedValue({ conversation_id: 'cv-new' });
  getRespondContactsOutbound.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 20 }, empty: true });
  window.localStorage.clear();
  window.localStorage.setItem(CONTACT_KEY, JSON.stringify({ id: 'ZZT-contact-1', label: 'Test Contact' }));
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, writable: true, value: (f: File) => `blob:staged/${f.name}` });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, writable: true, value: vi.fn() });
});
afterEach(() => cleanup());

// ------------------------------------------------------------------ AC-1

describe('AC-1: no tabs, one thread in the order it happened', () => {
  it('has no tabs, and the Bot/Agent screens no longer exist', () => {
    renderConsole();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(fs.existsSync(path.resolve(__dirname, 'ChatbotConsoleTabs.tsx'))).toBe(false);
    expect(fs.existsSync(path.resolve(__dirname, 'AgentConsole.tsx'))).toBe(false);
  });

  it('shows chat and agent turns interleaved in time order', async () => {
    getConsoleThread.mockResolvedValue(
      thread([
        chatTurn('c1', 'is SRT-1 in stock', 'First: chat answer.', '2026-10-31T09:00:00Z'),
        agentTurn('a1', 'why did sales drop', 'Second: agent answer.', '2026-10-31T09:01:00Z'),
        chatTurn('c2', 'thanks', 'Third: chat answer.', '2026-10-31T09:02:00Z'),
      ]),
    );
    renderConsole();
    await screen.findByText('Second: agent answer.');
    const text = screen.getByTestId('chatbot-console-thread').textContent ?? '';
    const at = ['is SRT-1 in stock', 'First: chat answer.', 'why did sales drop', 'Second: agent answer.', 'thanks', 'Third: chat answer.']
      .map((s) => text.indexOf(s));
    expect(at.every((i) => i >= 0)).toBe(true);
    expect([...at].sort((a, b) => a - b)).toEqual(at);
  });
});

// ------------------------------------------------------------------ AC-2 and the Forced word

describe('AC-2: the route pill on every reply', () => {
  it('shows Chat on a chat reply and Agent on an agent reply, each opening to reason, score, model and time', async () => {
    getConsoleThread.mockResolvedValue(
      thread([
        chatTurn('c1', 'q1', 'Chat reply.', '2026-10-31T09:00:00Z'),
        agentTurn('a1', 'q2', 'Agent reply.', '2026-10-31T09:01:00Z'),
      ]),
    );
    renderConsole();
    await screen.findByText('Agent reply.');
    expect(within(bubbleOf('Chat reply.')).getByRole('button', { name: 'Chat' })).toBeInTheDocument();
    fireEvent.click(within(bubbleOf('Agent reply.')).getByRole('button', { name: 'Agent' }));
    expect(await screen.findByText('Reason')).toBeInTheDocument();
    expect(screen.getByText('Classified')).toBeInTheDocument();
    expect(screen.getByText('0.92')).toBeInTheDocument();
    expect(screen.getByText('jev-1.14.0')).toBeInTheDocument();
    expect(screen.getByText('412 ms')).toBeInTheDocument();
  });

  it('words the reason forced as Forced', () => {
    expect(routeReasonWords('forced')).toBe('Forced');
  });
});

// ------------------------------------------------------------------ AC-3

describe('AC-3: steps and reasoning inside an agent bubble', () => {
  it('a reloaded agent turn shows Steps with its reasoning and tool line', async () => {
    getConsoleThread.mockResolvedValue(thread([agentTurn('a1', 'stock?', 'There are 12 units.', '2026-10-31T09:00:00Z')]));
    renderConsole();
    await screen.findByText('There are 12 units.');
    const bubble = bubbleOf('There are 12 units.');
    fireEvent.click(within(bubble).getByRole('button', { name: 'Steps' }));
    expect(within(bubble).getByText('Read 12 units of stock')).toBeInTheDocument();
    const thinking = within(bubble).getByRole('button', { name: 'Thinking (round 1)' });
    expect(thinking).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(thinking);
    expect(thinking).toHaveAttribute('aria-expanded', 'true');
    expect(within(bubble).getByText('Checking the stock balance first.')).toBeInTheDocument();
  });

  it('a turn the router chose (not forced) shows its steps too', async () => {
    postConsoleTurn.mockResolvedValue(agentResponse('Selangor fell.'));
    renderConsole();
    send('why did Selangor sales drop');
    await screen.findByText('Selangor fell.');
    fireEvent.click(within(bubbleOf('Selangor fell.')).getByRole('button', { name: 'Steps' }));
    expect(within(bubbleOf('Selangor fell.')).getByText('Read 12 units of stock')).toBeInTheDocument();
  });

  it('a chat turn has no Steps disclosure', async () => {
    getConsoleThread.mockResolvedValue(thread([chatTurn('c1', 'q', 'Chat reply.', '2026-10-31T09:00:00Z')]));
    renderConsole();
    await screen.findByText('Chat reply.');
    expect(within(bubbleOf('Chat reply.')).queryByRole('button', { name: 'Steps' })).not.toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ AC-4

describe('AC-4: write cards in the thread', () => {
  const PROPOSAL = {
    id: 'act-1', turn_id: 'a1', lines: ['Mark ask SRTWT7445 done'], expires_at: '2099-01-01T00:00:00Z',
  };
  const proposingTurn = () =>
    agentTurn('a1', 'mark it done', 'I will mark ask SRTWT7445 done when you confirm.', '2026-10-31T09:00:00Z');

  it('shows Confirm and Cancel on a waiting proposal; Confirm calls the same service and shows the outcome', async () => {
    getConsoleThread.mockResolvedValue(thread([proposingTurn()], PROPOSAL));
    confirmAgentAction.mockResolvedValue({
      action_id: 'act-1', status: 'executed', reply_text: 'Done. I made these changes:\n1. Mark ask SRTWT7445 done', steps: [],
    });
    renderConsole();
    const confirm = await screen.findByRole('button', { name: 'Confirm change' });
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();
    expect(screen.getByTestId('agent-proposal')).toBeInTheDocument();

    fireEvent.click(confirm);

    await waitFor(() => expect(confirmAgentAction).toHaveBeenCalledWith('ZZT-contact-1', 'act-1'));
    expect(await screen.findByTestId('agent-action-outcome')).toHaveTextContent('Done');
  });

  it('Cancel calls the cancel service', async () => {
    getConsoleThread.mockResolvedValue(thread([proposingTurn()], PROPOSAL));
    cancelAgentAction.mockResolvedValue({ action_id: 'act-1', status: 'cancelled', reply_text: 'Cancelled. Nothing was changed.', steps: [] });
    renderConsole();
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(cancelAgentAction).toHaveBeenCalledWith('ZZT-contact-1', 'act-1'));
    expect(await screen.findByText('Cancelled. Nothing was changed.')).toBeInTheDocument();
  });

  it('a running grace countdown shows with Undo, and Undo withdraws that step', async () => {
    const commitAt = new Date(Date.now() + 10 * 60_000).toISOString().replace('Z', '');
    getConsoleThread.mockResolvedValue(
      thread([
        agentTurn('a1', 'mark it done', 'Marked.', '2026-10-31T09:00:00Z', {
          actions: [{
            id: 'act-9', status: 'executed', decided_at: null, decided_by_name: 'ZZT Operator',
            steps: [{ summary: 'Mark ask SRTWT7445 done', status: 'done', error: null, changes: [], waiting: { commit_at: commitAt, window_seconds: 600 } }],
          }],
        }),
      ]),
    );
    withdrawAgentStep.mockResolvedValue({ action_id: 'act-9', status: 'executed', reply_text: 'Withdrawn.', steps: [] });
    renderConsole();
    expect(await screen.findByTestId('agent-step-waiting')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    await waitFor(() => expect(withdrawAgentStep).toHaveBeenCalledWith('ZZT-contact-1', 'act-9', 0));
  });
});

// ------------------------------------------------------------------ AC-5

describe('AC-5: everything the Bot tab had stays', () => {
  it('keeps attach, trace link, prompt version, quick replies and the composer', async () => {
    postConsoleTurn
      .mockResolvedValueOnce(turnResponse('Which product?', { turn_id: 't9', prompt_version: 18, quick_replies: ['Pump A'] }))
      .mockResolvedValueOnce(turnResponse('Pump A is 12.'));
    renderConsole();
    expect(screen.getAllByRole('button', { name: 'Attach image or audio' }).length).toBeGreaterThan(0);
    send('price?');
    await screen.findByText('Which product?');
    const bubble = bubbleOf('Which product?');
    expect(within(bubble).getByRole('link', { name: 'trace' }).getAttribute('href')).toContain('t9');
    expect(within(bubble).getByTestId('chatbot-console-prompt-pill')).toHaveTextContent('v18');
    fireEvent.click(within(bubble).getByRole('button', { name: 'Pump A' }));
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    expect(postConsoleTurn.mock.calls[1][0]).toMatchObject({ text: 'Pump A' });
  });
});

// ------------------------------------------------------------------ AC-6

describe('AC-6: a trace link on an agent turn, and unique bubble keys', () => {
  it('an agent bubble has a trace link to its own turn', async () => {
    getConsoleThread.mockResolvedValue(thread([agentTurn('agent-turn-77', 'q', 'Agent reply.', '2026-10-31T09:00:00Z')]));
    renderConsole();
    await screen.findByText('Agent reply.');
    const link = within(bubbleOf('Agent reply.')).getByRole('link', { name: 'trace' });
    expect(link.getAttribute('href')).toContain('agent-turn-77');
  });

  it('two busy agent replies without a turn id do not collide on a React key', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const busy = {
      turn_id: null, branch_kind: null, reply_text: 'The agent is busy with an earlier message for this contact. Try again in a moment.',
      quick_replies: [], send_messages: [], session_vars: null, trace_summary: {}, route: AGENT_ROUTE,
    };
    postConsoleTurn.mockResolvedValue(busy);
    renderConsole();
    send('first');
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    await screen.findByText(/agent is busy/i);
    send('second');
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getAllByText(/agent is busy/i)).toHaveLength(2));
    const keyWarnings = spy.mock.calls.filter((c) => /same key|unique "key"/i.test(String(c[0])));
    expect(keyWarnings).toEqual([]);
    spy.mockRestore();
  });
});

// ------------------------------------------------------------------ AC-7 / AC-9

describe('AC-7: the Agent toggle', () => {
  it('has an accessible name containing Agent and starts off', () => {
    renderConsole();
    expect(isOn(agentToggle())).toBe(false);
  });

  it('on: the next message is forced to the agent, then the toggle switches itself off', async () => {
    postConsoleTurn
      .mockResolvedValueOnce(agentResponse('Forced answer.', { route: { ...AGENT_ROUTE, reason: 'forced', score: null, model: null, ms: null } }))
      .mockResolvedValueOnce(turnResponse('Plain answer.'));
    renderConsole();
    fireEvent.click(agentToggle());
    expect(isOn(agentToggle())).toBe(true);

    send('stock of SRTWT7445?');
    await screen.findByText('Forced answer.');
    expect(postConsoleTurn.mock.calls[0][0]).toMatchObject({ force_agent: true, text: 'stock of SRTWT7445?' });
    await waitFor(() => expect(isOn(agentToggle())).toBe(false));

    send('and now?');
    await screen.findByText('Plain answer.');
    expect(postConsoleTurn.mock.calls[1][0].force_agent).toBeFalsy();
  });

  it('off: a message is not forced', async () => {
    postConsoleTurn.mockResolvedValue(turnResponse('Plain answer.'));
    renderConsole();
    send('hello');
    await screen.findByText('Plain answer.');
    expect(postConsoleTurn.mock.calls[0][0].force_agent).toBeFalsy();
  });

  it('is disabled while an attachment is staged', async () => {
    renderConsole();
    expect(isDisabled(agentToggle())).toBe(false);
    fireEvent.paste(box(), { clipboardData: { files: [new File(['x'], 'shot.png', { type: 'image/png' })] } });
    await screen.findByTestId('chatbot-console-staged');
    expect(isDisabled(agentToggle())).toBe(true);
  });

  it('a forced reply wears the Agent pill, which opens to the reason Forced', async () => {
    postConsoleTurn.mockResolvedValue(
      agentResponse('Forced answer.', { route: { side: 'agent', reason: 'forced', score: null, model: null, ms: null } }),
    );
    renderConsole();
    fireEvent.click(agentToggle());
    send('hello');
    await screen.findByText('Forced answer.');
    fireEvent.click(within(bubbleOf('Forced answer.')).getByRole('button', { name: 'Agent' }));
    expect(await screen.findByText('Forced')).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ AC-13

describe('AC-13: one New conversation button starts both sides afresh', () => {
  it('there is no Reset; New conversation starts a new agent conversation and a new run', async () => {
    postConsoleTurn.mockResolvedValue(turnResponse('Plain answer.'));
    renderConsole();
    expect(screen.queryByRole('button', { name: 'Reset' })).not.toBeInTheDocument();
    send('first');
    await screen.findByText('Plain answer.');
    const firstRun = postConsoleTurn.mock.calls[0][0].run_id;

    fireEvent.click(screen.getByRole('button', { name: 'New conversation' }));

    await waitFor(() => expect(newAgentConversation).toHaveBeenCalledWith('ZZT-contact-1'));
    await waitFor(() => expect(screen.queryByText('Plain answer.')).not.toBeInTheDocument());
    send('second');
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    expect(postConsoleTurn.mock.calls[1][0].run_id).not.toBe(firstRun);
  });
});

// ------------------------------------------------------------------ AC-14 (reload)

describe('AC-14: after a reload the thread is back', () => {
  it('asks for the thread with the contact and the run it was talking in', async () => {
    postConsoleTurn.mockResolvedValue(turnResponse('Plain answer.'));
    const first = renderConsole();
    send('first');
    await screen.findByText('Plain answer.');
    const run = postConsoleTurn.mock.calls[0][0].run_id as string;
    first.unmount();
    getConsoleThread.mockClear();
    getConsoleThread.mockResolvedValue(thread([chatTurn('c1', 'first', 'Plain answer.', '2026-10-31T09:00:00Z')]));

    renderConsole();

    await screen.findByText('Plain answer.');
    expect(threadCalls().some((c) => c.includes('ZZT-contact-1') && c.includes(run))).toBe(true);
  });

  it('a waiting proposal from the read can still be confirmed after a reload', async () => {
    getConsoleThread.mockResolvedValue(
      thread(
        [agentTurn('a1', 'mark it', 'I will mark it done when you confirm.', '2026-10-31T09:00:00Z')],
        { id: 'act-1', turn_id: 'a1', lines: ['Mark it done'], expires_at: '2099-01-01T00:00:00Z' },
      ),
    );
    confirmAgentAction.mockResolvedValue({ action_id: 'act-1', status: 'executed', reply_text: 'Done.', steps: [] });
    renderConsole();
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm change' }));
    await waitFor(() => expect(confirmAgentAction).toHaveBeenCalledWith('ZZT-contact-1', 'act-1'));
  });

  it('shows a loading skeleton until the read lands, then drops it', async () => {
    let finish: (v: unknown) => void = () => {};
    getConsoleThread.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    renderConsole();
    expect(await screen.findByRole('status', { name: 'Loading the conversation' })).toBeInTheDocument();
    expect(box()).toBeInTheDocument();

    finish(thread([chatTurn('c1', 'q', 'Old answer.', '2026-10-31T09:00:00Z')]));

    await screen.findByText('Old answer.');
    expect(screen.queryByRole('status', { name: 'Loading the conversation' })).not.toBeInTheDocument();
  });

  it('a message sent before the first read lands loses nothing: old turns and a waiting Confirm still appear', async () => {
    let finish: (v: unknown) => void = () => {};
    getConsoleThread.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    postConsoleTurn.mockResolvedValue(turnResponse('Fresh reply.'));
    renderConsole();
    send('sent too early');
    await screen.findByText('Fresh reply.');

    finish(
      thread(
        [
          chatTurn('c1', 'old question', 'Old answer.', '2026-10-31T08:00:00Z'),
          agentTurn('a1', 'mark it', 'I will mark it done when you confirm.', '2026-10-31T08:01:00Z'),
        ],
        { id: 'act-1', turn_id: 'a1', lines: ['Mark it done'], expires_at: '2099-01-01T00:00:00Z' },
      ),
    );

    await screen.findByText('Old answer.');
    expect(screen.getByText('old question')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Confirm change' })).toBeInTheDocument();
    expect(screen.getByText('sent too early')).toBeInTheDocument();
    expect(screen.getByText('Fresh reply.')).toBeInTheDocument();
  });

  it('a stored turn with no reply text adds no "(no reply)" line', async () => {
    getConsoleThread.mockResolvedValue(
      thread([
        chatTurn('c1', 'still running', '', '2026-10-31T09:00:00Z'),
        chatTurn('c2', 'done one', 'Real answer.', '2026-10-31T09:01:00Z'),
      ]),
    );
    renderConsole();
    await screen.findByText('Real answer.');
    expect(screen.queryByText('(no reply)')).not.toBeInTheDocument();
  });

  it('files the bot sent come back under the reply after a reload', async () => {
    getConsoleThread.mockResolvedValue(
      thread([
        chatTurn('c1', 'send me the sheet', 'Here it is.', '2026-10-31T09:00:00Z', {
          attachments: [{ url: 'https://files.example.invalid/sheet.pdf', filename: 'sheet.pdf', mimeType: 'application/pdf', attachmentType: 'document' }],
        }),
      ]),
    );
    renderConsole();
    await screen.findByText('Here it is.');
    expect(within(bubbleOf('Here it is.')).getByText('sheet.pdf')).toBeInTheDocument();
  });
});

describe('AC-14: the bot session survives a reload', () => {
  const SESSION = {
    focus: { customers: [] },
    open_question: { kind: 'customer_pick', options: [{ position: 1, label: 'Customer A' }], expects: 'pick', payload: {} },
    ideation: null,
    access_levels: [],
    contains_flyer: false,
  };

  async function firstTurnThenReload() {
    postConsoleTurn.mockResolvedValueOnce(turnResponse('Which customer?', { session_vars: SESSION }));
    const first = renderConsole();
    send('price?');
    await screen.findByText('Which customer?');
    const run = postConsoleTurn.mock.calls[0][0].run_id as string;
    first.unmount();
    getConsoleThread.mockResolvedValue({
      ...thread([chatTurn('c1', 'price?', 'Which customer?', '2026-10-31T09:00:00Z')]),
      // A server that hands the session back on the read, as well as whatever the page stored itself.
      session_vars: SESSION,
    });
    renderConsole();
    await screen.findByText('Which customer?');
    return run;
  }

  it('the next message after a reload sends the same session_vars for that contact and run, not {}', async () => {
    const run = await firstTurnThenReload();
    postConsoleTurn.mockResolvedValueOnce(turnResponse('Customer A it is.'));

    send('the first one');

    await screen.findByText('Customer A it is.');
    const body = postConsoleTurn.mock.calls[1][0];
    expect(body.contact_respond_id).toBe('ZZT-contact-1');
    expect(body.run_id).toBe(run);
    expect(body.session_vars).toEqual(SESSION);
  });

  it('a new conversation clears them', async () => {
    await firstTurnThenReload();
    fireEvent.click(screen.getByRole('button', { name: 'New conversation' }));
    await waitFor(() => expect(newAgentConversation).toHaveBeenCalled());
    postConsoleTurn.mockResolvedValueOnce(turnResponse('Fresh.'));

    send('hello again');

    await screen.findByText('Fresh.');
    expect(postConsoleTurn.mock.calls[1][0].session_vars).toEqual({});
  });
});

// ------------------------------------------------------------------ AC-16

describe('AC-16: switching contact shows that contact thread', () => {
  it('loads the other contact thread and drops the first one', async () => {
    getConsoleThread.mockImplementation(async (contact: unknown) =>
      JSON.stringify(contact).includes('ZZT-contact-2')
        ? thread([chatTurn('c2', 'second contact question', 'Second contact answer.', '2026-10-31T09:00:00Z')])
        : thread([chatTurn('c1', 'first contact question', 'First contact answer.', '2026-10-31T09:00:00Z')]),
    );
    getRespondContactsOutbound.mockResolvedValue({
      data: [{ respond_io_id: 'ZZT-contact-2', name: 'Second Contact', phone_number: null }],
      pagination: { total: 1, page: 1, limit: 20 },
      empty: false,
    });
    renderConsole();
    await screen.findByText('First contact answer.');

    const trigger = document.querySelectorAll('[data-slot="searchable-select-trigger"]')[0];
    fireEvent.click(trigger);
    fireEvent.click(await screen.findByText('Second Contact'));

    await screen.findByText('Second contact answer.');
    expect(screen.queryByText('First contact answer.')).not.toBeInTheDocument();
    expect(threadCalls().some((c) => c.includes('ZZT-contact-2'))).toBe(true);
  });
});

// ------------------------------------------------------------------ AC-20

describe('AC-20: a contact without the agent still gets chat, with the pill saying why', () => {
  const NOT_ELIGIBLE = { side: 'chat', reason: 'not_eligible:switch_off', score: null, model: null, ms: null };

  it('loads with no error banner and shows the reason on the pill', async () => {
    getConsoleThread.mockResolvedValue(
      thread([chatTurn('c1', 'q', 'Chat reply.', '2026-10-31T09:00:00Z', { route: NOT_ELIGIBLE })]),
    );
    renderConsole();
    await screen.findByText('Chat reply.');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(toastError).not.toHaveBeenCalled();
    fireEvent.click(within(bubbleOf('Chat reply.')).getByRole('button', { name: 'Chat' }));
    expect(await screen.findByText('Not eligible')).toBeInTheDocument();
  });

  it('a send answers as chat with no error', async () => {
    postConsoleTurn.mockResolvedValue(turnResponse('Chat reply.', { route: NOT_ELIGIBLE }));
    renderConsole();
    send('hello');
    await screen.findByText('Chat reply.');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(toastError).not.toHaveBeenCalled();
  });
});

// ------------------------------------------------------------------ AC-16 (in flight)

describe('AC-16: a reply in flight for the first contact never lands in the second', () => {
  const MARK_A = 'ZZTMARKERA';
  const SESSION_A = {
    focus: { customers: [{ canonical_code: MARK_A }] }, open_question: null, ideation: null, access_levels: [], contains_flyer: false,
  };

  it('keeps A reply, A session and the stored last contact out of B', async () => {
    getConsoleThread.mockImplementation(async (contact: unknown) =>
      JSON.stringify(contact).includes('ZZT-contact-2')
        ? thread([chatTurn('c2', 'second question', 'Second answer.', '2026-10-31T09:00:00Z')])
        : thread([]),
    );
    getRespondContactsOutbound.mockResolvedValue({
      data: [{ respond_io_id: 'ZZT-contact-2', name: 'Second Contact', phone_number: null }],
      pagination: { total: 1, page: 1, limit: 20 },
      empty: false,
    });
    let finishA: (v: unknown) => void = () => {};
    postConsoleTurn.mockReturnValueOnce(new Promise((resolve) => (finishA = resolve)));
    renderConsole();
    send('question for A');
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));

    fireEvent.click(document.querySelectorAll('[data-slot="searchable-select-trigger"]')[0]);
    fireEvent.click(await screen.findByText('Second Contact'));
    await screen.findByText('Second answer.');

    finishA(turnResponse('A reply that is late.', { session_vars: SESSION_A }));
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    await new Promise((r) => setTimeout(r, 50));

    expect(screen.queryByText('A reply that is late.')).not.toBeInTheDocument();
    expect(screen.getByText('Second answer.')).toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem(CONTACT_KEY) ?? '{}').id).toBe('ZZT-contact-2');
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i) as string;
      if (key.includes('ZZT-contact-2')) expect(window.localStorage.getItem(key)).not.toContain(MARK_A);
    }
    postConsoleTurn.mockResolvedValueOnce(turnResponse('B reply.'));
    send('question for B');
    await screen.findByText('B reply.');
    const body = postConsoleTurn.mock.calls[1][0];
    expect(body.contact_respond_id).toBe('ZZT-contact-2');
    expect(JSON.stringify(body.session_vars)).not.toContain(MARK_A);
  });
});

// ------------------------------------------------------------------ AC-4: a proposal straight after the turn

describe('AC-4: Confirm shows right after the turn that made it, no reload', () => {
  const PENDING = { id: 'act-1', turn_id: 'a-live', lines: ['Mark it done'], expires_at: '2099-01-01T00:00:00Z' };

  it('a routed agent turn whose response carries pending_action shows Confirm and Cancel at once', async () => {
    // The re-read after a turn never lands here, so Confirm can only come from the turn's own response.
    getConsoleThread.mockResolvedValueOnce(thread([])).mockReturnValue(new Promise(() => {}));
    postConsoleTurn.mockResolvedValue(
      agentResponse('I will mark it done when you confirm.', {
        agent: { turn_id: 'a-live', status: 'answered', pending_action: PENDING, steps: AGENT_STEPS, actions: [] },
      }),
    );
    renderConsole();
    await waitFor(() => expect(getConsoleThread).toHaveBeenCalledTimes(1));
    await new Promise((r) => setTimeout(r, 20)); // the first read has landed
    send('mark it done');
    await screen.findByText('I will mark it done when you confirm.');
    expect(await screen.findByRole('button', { name: 'Confirm change' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();
  });

  it('a first read that lands after the turn does not wipe the proposal the turn made', async () => {
    let landLate: (v: unknown) => void = () => {};
    getConsoleThread
      .mockReturnValueOnce(new Promise((resolve) => (landLate = resolve)))
      .mockReturnValue(new Promise(() => {}));
    postConsoleTurn.mockResolvedValue(
      agentResponse('I will mark it done when you confirm.', {
        agent: { turn_id: 'a-live', status: 'answered', pending_action: PENDING, steps: AGENT_STEPS, actions: [] },
      }),
    );
    renderConsole();
    send('mark it done');
    await screen.findByRole('button', { name: 'Confirm change' });

    landLate(thread([])); // read from before the turn: no proposal on it

    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByRole('button', { name: 'Confirm change' })).toBeInTheDocument();
  });

  it('a slow voice note routed to the agent shows Confirm after the follow-up turn, no reload', async () => {
    // The re-read after a turn never lands here, so Confirm can only come from the turn's own response.
    getConsoleThread.mockResolvedValueOnce(thread([])).mockReturnValue(new Promise(() => {}));
    postConsoleTurn
      .mockResolvedValueOnce({
        turn_id: null, branch_kind: null, reply_text: '', quick_replies: [], send_messages: [], session_vars: null,
        trace_summary: {}, media_status: 'pending', media_id: 'job-1', media_text: null, media_error: null,
      })
      .mockResolvedValueOnce(
        agentResponse('I will mark it done when you confirm.', {
          agent: { turn_id: 'a-live', status: 'answered', pending_action: PENDING, steps: AGENT_STEPS, actions: [] },
        }),
      );
    getConsoleMediaStatus.mockResolvedValue({ status: 'done', text: 'mark it done', error: null });
    renderConsole();
    await waitFor(() => expect(getConsoleThread).toHaveBeenCalledTimes(1));
    await new Promise((r) => setTimeout(r, 20)); // the first read has landed
    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, {
      target: { files: [new File(['x'], 'note.ogg', { type: 'audio/ogg' })] },
    });
    await screen.findByTestId('chatbot-console-staged');
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    expect(await screen.findByRole('button', { name: 'Confirm change' }, { timeout: 8000 })).toBeInTheDocument();
    expect(postConsoleTurn.mock.calls[1][0]).toMatchObject({ text: 'mark it done' });
  }, 15000);
});

// ------------------------------------------------------------------ AC-7: chips and attachments

describe('AC-7: the toggle with chips, voice and attachments', () => {
  it('a quick-reply chip honours a toggle that is on, then turns it off', async () => {
    postConsoleTurn
      .mockResolvedValueOnce(turnResponse('Which product?', { quick_replies: ['Pump A'] }))
      .mockResolvedValueOnce(agentResponse('Pump A is 12.'));
    renderConsole();
    send('price?');
    await screen.findByText('Which product?');
    fireEvent.click(agentToggle());
    expect(isOn(agentToggle())).toBe(true);

    fireEvent.click(within(bubbleOf('Which product?')).getByRole('button', { name: 'Pump A' }));

    await screen.findByText('Pump A is 12.');
    expect(postConsoleTurn.mock.calls[1][0]).toMatchObject({ text: 'Pump A', force_agent: true });
    await waitFor(() => expect(isOn(agentToggle())).toBe(false));
  });

  it('an attachment goes to the bot and leaves the toggle off afterwards', async () => {
    postConsoleTurn.mockResolvedValueOnce({
      ...turnResponse('Read it.'), media_status: 'done', media_id: 'm1', media_text: 'a label', media_error: null,
    });
    renderConsole();
    fireEvent.click(agentToggle());
    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, {
      target: { files: [new File(['x'], 'shot.png', { type: 'image/png' })] },
    });
    await screen.findByTestId('chatbot-console-staged');
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    await screen.findByText('Read it.');
    const body = postConsoleTurn.mock.calls[0][0];
    expect(body.media).toMatchObject({ kind: 'image' });
    expect(body.force_agent).toBeFalsy();
    await waitFor(() => expect(screen.queryByTestId('chatbot-console-staged')).not.toBeInTheDocument());
    expect(isOn(agentToggle())).toBe(false);
  });

  it('a voice note goes to the bot and leaves the toggle off afterwards', async () => {
    postConsoleTurn.mockResolvedValueOnce({
      ...turnResponse('Heard it.'), media_status: 'done', media_id: 'm2', media_text: 'hello', media_error: null,
    });
    renderConsole();
    fireEvent.click(agentToggle());
    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, {
      target: { files: [new File(['x'], 'note.ogg', { type: 'audio/ogg' })] },
    });
    await screen.findByTestId('chatbot-console-staged');
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    await screen.findByText('Heard it.');
    expect(postConsoleTurn.mock.calls[0][0].media).toMatchObject({ kind: 'audio' });
    expect(postConsoleTurn.mock.calls[0][0].force_agent).toBeFalsy();
    await waitFor(() => expect(screen.queryByTestId('chatbot-console-staged')).not.toBeInTheDocument());
    expect(isOn(agentToggle())).toBe(false);
  });
});
