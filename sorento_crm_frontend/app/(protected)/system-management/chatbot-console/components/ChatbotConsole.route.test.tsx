/**
 * AGENTIC-P2-ROUTE V3: the console shows which side answered (Agent or Chat) as a pill under
 * the answer; activating it opens a popover with Reason, Score, Model and Time.
 * Red first: the response carries `route`, nothing renders it yet.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatbotConsole from './ChatbotConsole';

const postConsoleTurn = vi.fn();
const getConsolePromptVersions = vi.fn();

vi.mock('../services/chatbotConsoleService', () => ({
  postConsoleTurn: (...args: unknown[]) => postConsoleTurn(...args),
  getConsolePromptVersions: (...args: unknown[]) => getConsolePromptVersions(...args),
  getConsoleMediaStatus: vi.fn(),
  getConsoleThread: vi.fn().mockResolvedValue({ turns: [], pending_action: null }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../respond-contacts/services/respondContactOutboundService', () => ({
  getRespondContactsOutbound: vi.fn().mockResolvedValue({
    data: [],
    pagination: { total: 0, page: 1, limit: 20 },
    empty: true,
    counts: { enabled: 0, disabled: 0, total: 0 },
  }),
}));
vi.mock('../../chat-history/services/chatbotTurnService', () => ({
  getChatbotTurns: vi.fn().mockResolvedValue({ items: [], next_cursor: null, retry_available: false }),
}));

function turn(reply: string, route?: Record<string, unknown>, extra: Record<string, unknown> = {}) {
  return {
    turn_id: 't1',
    branch_kind: 'business_query',
    reply_text: reply,
    quick_replies: [],
    send_messages: [],
    session_vars: {},
    trace_summary: { tool: null, args_short: null, crossdomain_rungs: [], reveals_dropped: [] },
    ...(route ? { route } : {}),
    ...extra,
  };
}

function renderConsole() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChatbotConsole />
    </QueryClientProvider>,
  );
}

async function sendAndGetBubble(reply: string): Promise<HTMLElement> {
  const box = screen.getByPlaceholderText('Ask, or attach voice/image');
  fireEvent.change(box, { target: { value: 'why did sales drop' } });
  fireEvent.keyDown(box, { key: 'Enter' });
  await screen.findByText(reply);
  return screen.getAllByText(reply)[0].closest('[data-testid="message-bubble"]') as HTMLElement;
}

const pill = (bubble: HTMLElement, name: 'Agent' | 'Chat') =>
  within(bubble).getByRole('button', { name });

beforeEach(() => {
  postConsoleTurn.mockReset();
  getConsolePromptVersions.mockReset();
  getConsolePromptVersions.mockResolvedValue([]);
  window.localStorage.clear();
  window.localStorage.setItem(
    'chatbot-console:last-contact',
    JSON.stringify({ id: 'ZZT-contact-1', label: 'Test Contact' }),
  );
});
afterEach(() => cleanup());

describe('ChatbotConsole - route pill (V3)', () => {
  it('shows an Agent pill on an agent-routed answer, with the agent reply text', async () => {
    postConsoleTurn.mockResolvedValue(
      turn('', { side: 'agent', reason: 'classified', score: 0.92, model: 'jev-1.14.0', ms: 412 }, {
        reply_text: 'Selangor fell because two dealers paused.',
        agent: { turn_id: 'a1', status: 'answered', pending_action: null },
      }),
    );
    renderConsole();
    const bubble = await sendAndGetBubble('Selangor fell because two dealers paused.');
    expect(pill(bubble, 'Agent')).toBeInTheDocument();
  });

  it('shows a Chat pill on a bot-routed answer', async () => {
    postConsoleTurn.mockResolvedValue(
      turn('Stock is 12.', { side: 'chat', reason: 'classified', score: 0.88, model: 'jev-1.14.0', ms: 300 }),
    );
    renderConsole();
    const bubble = await sendAndGetBubble('Stock is 12.');
    expect(pill(bubble, 'Chat')).toBeInTheDocument();
    expect(within(bubble).queryByRole('button', { name: 'Agent' })).not.toBeInTheDocument();
  });

  it('renders no pill when the response has no route', async () => {
    postConsoleTurn.mockResolvedValue(turn('Stock is 12.'));
    renderConsole();
    const bubble = await sendAndGetBubble('Stock is 12.');
    expect(within(bubble).queryByRole('button', { name: 'Agent' })).not.toBeInTheDocument();
    expect(within(bubble).queryByRole('button', { name: 'Chat' })).not.toBeInTheDocument();
  });

  it('clicking the pill opens the popover with reason, score, model and time', async () => {
    postConsoleTurn.mockResolvedValue(
      turn('Stock is 12.', { side: 'chat', reason: 'low_confidence', score: 0.6234, model: 'jev-1.14.0', ms: 412 }),
    );
    renderConsole();
    const bubble = await sendAndGetBubble('Stock is 12.');
    fireEvent.click(pill(bubble, 'Chat'));
    expect(await screen.findByText('Reason')).toBeInTheDocument();
    expect(screen.getByText('Low confidence')).toBeInTheDocument();
    expect(screen.getByText('Score')).toBeInTheDocument();
    expect(screen.getByText('0.62')).toBeInTheDocument();
    expect(screen.getByText('Model')).toBeInTheDocument();
    expect(screen.getByText('jev-1.14.0')).toBeInTheDocument();
    expect(screen.getByText('Time')).toBeInTheDocument();
    expect(screen.getByText('412 ms')).toBeInTheDocument();
  });

  it('the keyboard opens it too', async () => {
    postConsoleTurn.mockResolvedValue(
      turn('Stock is 12.', { side: 'chat', reason: 'classified', score: 0.9, model: 'jev-1.14.0', ms: 100 }),
    );
    renderConsole();
    const bubble = await sendAndGetBubble('Stock is 12.');
    const button = pill(bubble, 'Chat');
    button.focus();
    fireEvent.keyDown(button, { key: 'Enter' });
    fireEvent.click(button);
    expect(await screen.findByText('Reason')).toBeInTheDocument();
  });

  it('a null score reads as a dash', async () => {
    postConsoleTurn.mockResolvedValue(
      turn('Stock is 12.', { side: 'chat', reason: 'media', score: null, model: null, ms: null }),
    );
    renderConsole();
    const bubble = await sendAndGetBubble('Stock is 12.');
    fireEvent.click(pill(bubble, 'Chat'));
    await screen.findByText('Reason');
    expect(screen.getByText('Media')).toBeInTheDocument();
    expect(screen.getAllByText('-').length).toBeGreaterThanOrEqual(1);
  });

  it.each([
    ['classified', 'Classified'],
    ['low_confidence', 'Low confidence'],
    ['open_question', 'Open question'],
    ['media', 'Media'],
    ['daily_cap', 'Daily cap'],
    ['pending_action', 'Pending action'],
    ['router_failed:timeout', 'Router failed'],
    ['not_eligible:switch_off', 'Not eligible'],
  ])('reason %s reads as %s', async (reason, words) => {
    postConsoleTurn.mockResolvedValue(
      turn('Stock is 12.', { side: 'chat', reason, score: 0.9, model: 'jev-1.14.0', ms: 100 }),
    );
    renderConsole();
    const bubble = await sendAndGetBubble('Stock is 12.');
    fireEvent.click(pill(bubble, 'Chat'));
    expect(await screen.findByText(words)).toBeInTheDocument();
  });
});

describe('ChatbotConsole - route popover placement (375 px browser pass)', () => {
  it('renders the popover outside the thread scroll container so it can flip above the pill', async () => {
    postConsoleTurn.mockResolvedValue(
      turn('Stock is 12.', { side: 'chat', reason: 'classified', score: 0.9, model: 'jev-1.14.0', ms: 412 }),
    );
    renderConsole();
    const bubble = await sendAndGetBubble('Stock is 12.');
    fireEvent.click(pill(bubble, 'Chat'));
    const reason = await screen.findByText('Reason');
    const popover = reason.closest('[data-slot="popover-content"]') as HTMLElement;
    expect(popover).toBeTruthy();
    expect(document.body).toContainElement(popover);
    const thread = screen.getByTestId('chatbot-console-thread');
    expect(thread.contains(popover)).toBe(false);
  });
});
