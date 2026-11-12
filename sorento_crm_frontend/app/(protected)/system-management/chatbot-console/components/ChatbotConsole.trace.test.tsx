/**
 * TRACE-SIDEBAR (owner, 11 Nov 2026): the "trace" link under a console reply opens the shared
 * turn trace drawer over the console, in the same tab. No new tab, no navigation, the thread
 * stays where it was, Escape closes the drawer.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatbotConsole from './ChatbotConsole';

const postConsoleTurn = vi.fn();
const getChatbotTurn = vi.fn();
const push = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/system-management/chatbot-console',
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('../services/chatbotConsoleService', () => ({
  postConsoleTurn: (...args: unknown[]) => postConsoleTurn(...args),
  getConsolePromptVersions: vi.fn().mockResolvedValue([]),
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
  getChatbotTurn: (...args: unknown[]) => getChatbotTurn(...args),
}));

const TURN_ID = 'abcd1234-0000-4000-8000-000000000001';

function renderConsole() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChatbotConsole />
    </QueryClientProvider>,
  );
}

async function sendOne(): Promise<HTMLElement> {
  const box = screen.getByPlaceholderText('Ask, or attach voice/image');
  fireEvent.change(box, { target: { value: 'stock for SRT100' } });
  fireEvent.keyDown(box, { key: 'Enter' });
  await screen.findByText('Stock: 5');
  return screen.getAllByText('Stock: 5')[0].closest('[data-testid="message-bubble"]') as HTMLElement;
}

beforeEach(() => {
  postConsoleTurn.mockReset();
  getChatbotTurn.mockReset();
  push.mockReset();
  // Never resolves: the drawer shows its loading state under the turn title.
  getChatbotTurn.mockReturnValue(new Promise(() => {}));
  postConsoleTurn.mockResolvedValue({
    turn_id: TURN_ID,
    branch_kind: 'business_query',
    reply_text: 'Stock: 5',
    quick_replies: [],
    send_messages: [],
    session_vars: {},
    trace_summary: { tool: null, args_short: null, crossdomain_rungs: [], reveals_dropped: [] },
  });
  window.localStorage.clear();
  window.localStorage.setItem(
    'chatbot-console:last-contact',
    JSON.stringify({ id: 'ZZT-contact-1', label: 'Test Contact' }),
  );
});
afterEach(() => cleanup());

describe('Chatbot Console trace opens the turn trace drawer in place (TRACE-SIDEBAR)', () => {
  it('renders trace as a button, never a new-tab link', async () => {
    renderConsole();
    const bubble = await sendOne();
    expect(within(bubble).getByRole('button', { name: 'trace' })).toBeTruthy();
    expect(document.querySelector('a[target="_blank"]')).toBeNull();
    expect(document.querySelector('a[href*="chat-history"]')).toBeNull();
  });

  it('clicking trace opens the drawer for that turn without leaving the page', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    renderConsole();
    const bubble = await sendOne();
    fireEvent.click(within(bubble).getByRole('button', { name: 'trace' }));

    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText('Turn #abcd')).toBeTruthy();
    expect(getChatbotTurn).toHaveBeenCalledWith(TURN_ID);
    expect(openSpy).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
    // The console thread is still on the page under the drawer.
    expect(screen.getAllByText('Stock: 5').length).toBeGreaterThan(0);
    openSpy.mockRestore();
  });

  it('Escape closes the drawer and keeps the thread', async () => {
    renderConsole();
    const bubble = await sendOne();
    fireEvent.click(within(bubble).getByRole('button', { name: 'trace' }));
    const drawer = await screen.findByRole('dialog');
    fireEvent.keyDown(drawer, { key: 'Escape' });
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getAllByText('Stock: 5').length).toBeGreaterThan(0);
  });
});
