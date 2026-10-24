/**
 * QUOTED-REPLY AC-QR-19: the console's reply control. Since CHAT-CONSOLE-UX it is the bubble's
 * own menu (and swipe) rather than a dropdown; the `reply_to` payload is unchanged.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatbotConsole from './ChatbotConsole';
import { CONSOLE_GREETING_MESSAGES } from '../types/chatbotConsole.types';

const postConsoleTurn = vi.fn();
const getConsolePromptVersions = vi.fn();

vi.mock('../services/chatbotConsoleService', () => ({
  postConsoleTurn: (...args: unknown[]) => postConsoleTurn(...args),
  getConsolePromptVersions: (...args: unknown[]) => getConsolePromptVersions(...args),
  getConsoleMediaStatus: vi.fn(),
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

function turn(id: string, reply: string, extra: string[] = []) {
  return {
    turn_id: id,
    branch_kind: 'business_query',
    reply_text: reply,
    quick_replies: [],
    send_messages: extra,
    session_vars: {},
    trace_summary: { tool: null, args_short: null, crossdomain_rungs: [], reveals_dropped: [] },
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

function textarea(): HTMLTextAreaElement {
  return screen.getByPlaceholderText('Ask, or attach voice/image') as HTMLTextAreaElement;
}

async function send(text: string) {
  fireEvent.change(textarea(), { target: { value: text } });
  fireEvent.keyDown(textarea(), { key: 'Enter' });
}

/** The bubble's own menu (right-click; long-press on a phone) - the reply action since
 * CHAT-CONSOLE-UX replaced the "Reply to" dropdown. */
function bubbleOf(text: string): HTMLElement {
  return screen.getAllByText(text)[0].closest('[data-testid="message-bubble"]') as HTMLElement;
}

async function menuItemsOf(text: string): Promise<string[]> {
  fireEvent.contextMenu(bubbleOf(text), { clientX: 20, clientY: 20 });
  const items = (await screen.findAllByRole('menuitem')).map((i) => i.textContent ?? '');
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  return items;
}

async function replyTo(text: string) {
  fireEvent.contextMenu(bubbleOf(text), { clientX: 20, clientY: 20 });
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Reply' }));
  await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
}

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

describe('ChatbotConsole - Reply to control (AC-QR-19)', () => {
  it('offers Reply on every bot bubble of a turn, never on a greeting or an unacknowledged send', async () => {
    postConsoleTurn
      .mockResolvedValueOnce(turn('t1', 'Which product do you mean?'))
      .mockResolvedValueOnce(turn('t2', 'Stock is 12 on hand.', ['Anything else?']));
    renderConsole();
    await send('first');
    await screen.findByText('Which product do you mean?');
    await send('second');
    await screen.findByText('Anything else?');

    for (const text of ['Anything else?', 'Stock is 12 on hand.', 'Which product do you mean?']) {
      expect(await menuItemsOf(text)).toContain('Reply');
    }
    // Greeting lines are never quotable.
    for (const greeting of CONSOLE_GREETING_MESSAGES) {
      expect(await menuItemsOf(greeting)).not.toContain('Reply');
    }
    // A user bubble the server did not acknowledge (no message_id) has nothing to quote.
    expect(await menuItemsOf('first')).not.toContain('Reply');
  });

  it('sending after choosing a bubble posts reply_to {id, text} with the typed text', async () => {
    postConsoleTurn
      .mockResolvedValueOnce(turn('t1', 'Which product do you mean?'))
      .mockResolvedValueOnce(turn('t2', 'Noted.'));
    renderConsole();
    await send('price?');
    await screen.findByText('Which product do you mean?');

    await replyTo('Which product do you mean?');
    await send('1 unit');

    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    const payload = postConsoleTurn.mock.calls[1][0];
    expect(payload.text).toBe('1 unit');
    expect(payload.reply_to).toEqual({ id: 'bot-t1-0', text: 'Which product do you mean?', source: 'n8n' });
  });

  it('the user bubble shows the quoted text and the typed text', async () => {
    postConsoleTurn
      .mockResolvedValueOnce(turn('t1', 'Which product do you mean?'))
      .mockResolvedValueOnce(turn('t2', 'Noted.'));
    renderConsole();
    await send('price?');
    await screen.findByText('Which product do you mean?');

    await replyTo('Which product do you mean?');
    await send('1 unit');

    const typed = await screen.findByText('1 unit');
    const userBubble = typed.closest('[data-role="user"], [data-testid*="user"], div') as HTMLElement;
    // The quote is rendered inside the same bubble as the typed text.
    let node: HTMLElement | null = typed;
    let found = false;
    while (node && node !== document.body) {
      if (within(node).queryByText('Which product do you mean?') && within(node).queryByText('1 unit')) {
        // Must not be the whole thread: the bot bubble's own copy would also match there.
        if (within(node).queryAllByText('Which product do you mean?').length === 1) found = true;
        break;
      }
      node = node.parentElement;
    }
    expect(userBubble).toBeTruthy();
    expect(found).toBe(true);
  });

  it('clears the reply after the send, so the next send carries no reply_to', async () => {
    postConsoleTurn
      .mockResolvedValueOnce(turn('t1', 'Which product do you mean?'))
      .mockResolvedValueOnce(turn('t2', 'Noted.'))
      .mockResolvedValueOnce(turn('t3', 'Done.'));
    renderConsole();
    await send('price?');
    await screen.findByText('Which product do you mean?');

    await replyTo('Which product do you mean?');
    await send('1 unit');
    await screen.findByText('Noted.');

    // The "Replying to" bar is gone.
    expect(screen.queryByTestId('chatbot-console-reply-to')).not.toBeInTheDocument();

    await send('and 2 units');
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(3));
    expect(postConsoleTurn.mock.calls[2][0]).not.toHaveProperty('reply_to');
  });

  it('with nothing chosen the request has no reply_to key', async () => {
    postConsoleTurn.mockResolvedValueOnce(turn('t1', 'Which product do you mean?'));
    renderConsole();
    await send('price?');
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    expect(postConsoleTurn.mock.calls[0][0]).not.toHaveProperty('reply_to');
  });
});
