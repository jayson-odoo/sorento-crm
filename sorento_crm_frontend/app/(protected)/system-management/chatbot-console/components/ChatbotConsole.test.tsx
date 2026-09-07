/**
 * The in-app chatbot console (Slice D final, chatbot growth r1), text turns.
 *
 * The service layer (`chatbotConsoleService`) is mocked - the hook and the component are
 * what's under test here; the real HTTP contract is proved by the backend's own
 * `tests/chatbot/test_console_turn_endpoint.py`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatbotConsole from './ChatbotConsole';

const postConsoleTurn = vi.fn();
const getConsolePromptVersions = vi.fn();
const toastError = vi.fn();

vi.mock('../services/chatbotConsoleService', () => ({
  postConsoleTurn: (...args: unknown[]) => postConsoleTurn(...args),
  getConsolePromptVersions: (...args: unknown[]) => getConsolePromptVersions(...args),
  getConsoleMediaStatus: vi.fn(),
}));

vi.mock('@/lib/toast', () => ({
  toast: {
    success: vi.fn(),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

// The contact picker's OWN service is never exercised in these specs - the contact is
// seeded straight into localStorage before render, so the hook's bootstrap effect never
// reaches it. Mocked anyway so an accidental interaction cannot make a real network call.
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

const CONTACT_STORAGE_KEY = 'chatbot-console:last-contact';

function seedContact(id = 'ZZT-contact-1', label = 'Test Contact') {
  window.localStorage.setItem(CONTACT_STORAGE_KEY, JSON.stringify({ id, label }));
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

beforeEach(() => {
  postConsoleTurn.mockReset();
  getConsolePromptVersions.mockReset();
  getConsolePromptVersions.mockResolvedValue([]);
  toastError.mockReset();
  window.localStorage.clear();
  seedContact();
});

afterEach(() => cleanup());

describe('ChatbotConsole - sending a turn', () => {
  it('renders the reply, each send_messages bubble, and the branch_kind pill', async () => {
    postConsoleTurn.mockResolvedValue({
      turn_id: 'turn-1',
      branch_kind: 'not_supported',
      reply_text: 'Sorry, we cannot help with that here.',
      quick_replies: [],
      send_messages: ['A second line the lane composed separately.'],
      session_vars: { pending: null },
      trace_summary: { tool: null, args_short: null, crossdomain_rungs: [], reveals_dropped: [] },
    });

    renderConsole();
    fireEvent.change(textarea(), { target: { value: 'can I submit a goods receive here' } });
    fireEvent.keyDown(textarea(), { key: 'Enter' });

    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Sorry, we cannot help with that here.')).toBeInTheDocument();
    expect(await screen.findByText('A second line the lane composed separately.')).toBeInTheDocument();
    expect(screen.getByText('not_supported')).toBeInTheDocument();
  });

  it('a quick reply chip sends its own text as the next turn', async () => {
    postConsoleTurn.mockResolvedValueOnce({
      turn_id: 'turn-1',
      branch_kind: 'clarify_menu',
      reply_text: 'Which product?',
      quick_replies: ['SRTWC8517', 'SRTWC9000'],
      send_messages: [],
      session_vars: {},
      trace_summary: { tool: null, args_short: null, crossdomain_rungs: [], reveals_dropped: [] },
    });
    postConsoleTurn.mockResolvedValueOnce({
      turn_id: 'turn-2',
      branch_kind: 'business_query',
      reply_text: 'SRTWC8517 is RM10.',
      quick_replies: [],
      send_messages: [],
      session_vars: {},
      trace_summary: { tool: null, args_short: null, crossdomain_rungs: [], reveals_dropped: [] },
    });

    renderConsole();
    fireEvent.change(textarea(), { target: { value: 'price for a product' } });
    fireEvent.keyDown(textarea(), { key: 'Enter' });
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));

    const chip = await screen.findByRole('button', { name: 'SRTWC8517' });
    fireEvent.click(chip);

    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    expect(postConsoleTurn.mock.calls[1][0]).toMatchObject({ text: 'SRTWC8517' });
    expect(await screen.findByText('SRTWC8517 is RM10.')).toBeInTheDocument();
  });
});

describe('ChatbotConsole - composer keyboard', () => {
  it('Enter sends the message', async () => {
    postConsoleTurn.mockResolvedValue({
      turn_id: 't1',
      branch_kind: null,
      reply_text: 'ok',
      quick_replies: [],
      send_messages: [],
      session_vars: {},
      trace_summary: { tool: null, args_short: null, crossdomain_rungs: [], reveals_dropped: [] },
    });
    renderConsole();
    fireEvent.change(textarea(), { target: { value: 'hello' } });
    fireEvent.keyDown(textarea(), { key: 'Enter' });

    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    expect(postConsoleTurn.mock.calls[0][0]).toMatchObject({ text: 'hello' });
  });

  it('Shift+Enter inserts a newline instead of sending', async () => {
    renderConsole();
    fireEvent.change(textarea(), { target: { value: 'hello' } });
    fireEvent.keyDown(textarea(), { key: 'Enter', shiftKey: true });

    // Give any accidental async send a chance to fire before asserting it did not.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(postConsoleTurn).not.toHaveBeenCalled();
  });
});

describe('ChatbotConsole - reset', () => {
  it('clears the thread back to the two greeting lines and rotates run_id', async () => {
    postConsoleTurn.mockResolvedValue({
      turn_id: 't1',
      branch_kind: null,
      reply_text: 'first reply',
      quick_replies: [],
      send_messages: [],
      session_vars: {},
      trace_summary: { tool: null, args_short: null, crossdomain_rungs: [], reveals_dropped: [] },
    });
    renderConsole();
    fireEvent.change(textarea(), { target: { value: 'hello' } });
    fireEvent.keyDown(textarea(), { key: 'Enter' });
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    const firstRunId = postConsoleTurn.mock.calls[0][0].run_id as string;
    expect(await screen.findByText('first reply')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /reset/i }));

    expect(screen.queryByText('first reply')).not.toBeInTheDocument();
    expect(
      screen.getByText('Sorento chat console (dry run, nothing reaches WhatsApp).'),
    ).toBeInTheDocument();
    expect(screen.getByText('Type a message to test the bot.')).toBeInTheDocument();

    fireEvent.change(textarea(), { target: { value: 'again' } });
    fireEvent.keyDown(textarea(), { key: 'Enter' });
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    const secondRunId = postConsoleTurn.mock.calls[1][0].run_id as string;
    expect(secondRunId).not.toBe(firstRunId);
  });
});

describe('ChatbotConsole - errors', () => {
  it('toasts the extracted error message and never renders a bot bubble for it', async () => {
    postConsoleTurn.mockRejectedValue(new Error('This contact has no chatbot turn to borrow a session from.'));
    renderConsole();
    fireEvent.change(textarea(), { target: { value: 'hello' } });
    fireEvent.keyDown(textarea(), { key: 'Enter' });

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        'This contact has no chatbot turn to borrow a session from.',
      ),
    );
  });
});

describe('ChatbotConsole - prompt version select', () => {
  it('passes the picked version id as prompt_version_id on the next turn', async () => {
    getConsolePromptVersions.mockResolvedValue([
      { id: 'v-2', version: 2, label: null, chars: 120, base: 'compact' },
      { id: 'v-1', version: 1, label: 'production', chars: 100, base: 'compact' },
    ]);
    postConsoleTurn.mockResolvedValue({
      turn_id: 't1',
      branch_kind: null,
      reply_text: 'ok',
      quick_replies: [],
      send_messages: [],
      session_vars: {},
      trace_summary: { tool: null, args_short: null, crossdomain_rungs: [], reveals_dropped: [] },
    });

    renderConsole();
    await waitFor(() => expect(getConsolePromptVersions).toHaveBeenCalled());

    const triggers = document.querySelectorAll('[data-slot="searchable-select-trigger"]');
    // [0] = contact, [1] = prompt version.
    fireEvent.click(triggers[1]);
    const option = await screen.findByText('v2 \u00b7 compact');
    fireEvent.click(option);

    fireEvent.change(textarea(), { target: { value: 'hello' } });
    fireEvent.keyDown(textarea(), { key: 'Enter' });

    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    expect(postConsoleTurn.mock.calls[0][0]).toMatchObject({ prompt_version_id: 'v-2' });
  });
});

const PROMPT_STORAGE_KEY = 'chatbot-console:prompt-version';

const VERSIONS = [
  { id: 'v-19', version: 19, label: 'production', chars: 35301, base: 'compact' as const },
  { id: 'v-18', version: 18, label: null, chars: 53704, base: 'full' as const },
  { id: 'v-17', version: 17, label: null, chars: 34513, base: 'compact' as const },
  { id: 'v-16', version: 16, label: null, chars: 52919, base: 'full' as const },
];

function okTurn(promptVersion: number | null) {
  return {
    turn_id: 't1',
    branch_kind: 'business_query',
    reply_text: 'ok',
    quick_replies: [],
    send_messages: [],
    session_vars: {},
    trace_summary: { tool: null, args_short: null, crossdomain_rungs: [], reveals_dropped: [] },
    prompt_version: promptVersion,
  };
}

function promptTrigger(): Element {
  // [0] = contact, [1] = prompt version.
  return document.querySelectorAll('[data-slot="searchable-select-trigger"]')[1];
}

describe('ChatbotConsole - item 6, the prompt version defaults to the newest FULL body', () => {
  it('a fresh load pins the newest full version, not the newest overall and not the label', async () => {
    getConsolePromptVersions.mockResolvedValue(VERSIONS);
    postConsoleTurn.mockResolvedValue(okTurn(18));
    renderConsole();

    await waitFor(() => expect(promptTrigger().textContent).toContain('v18 \u00b7 full'));

    fireEvent.change(textarea(), { target: { value: 'hello' } });
    fireEvent.keyDown(textarea(), { key: 'Enter' });
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    expect(postConsoleTurn.mock.calls[0][0]).toMatchObject({ prompt_version_id: 'v-18' });
  });

  it('the option label reads version, base and label, never a UUID', async () => {
    getConsolePromptVersions.mockResolvedValue(VERSIONS);
    renderConsole();
    await waitFor(() => expect(promptTrigger().textContent).toContain('v18'));
    fireEvent.click(promptTrigger());
    expect(await screen.findByText('v19 \u00b7 compact \u00b7 production')).toBeInTheDocument();
    expect(screen.queryByText(/v-19/)).not.toBeInTheDocument();
  });

  it('a stored explicit choice is restored when it still exists', async () => {
    window.localStorage.setItem(PROMPT_STORAGE_KEY, JSON.stringify({ id: 'v-17' }));
    getConsolePromptVersions.mockResolvedValue(VERSIONS);
    renderConsole();
    await waitFor(() => expect(promptTrigger().textContent).toContain('v17 \u00b7 compact'));
  });

  it('a stored choice for a version that no longer exists falls back to the default', async () => {
    window.localStorage.setItem(PROMPT_STORAGE_KEY, JSON.stringify({ id: 'v-gone' }));
    getConsolePromptVersions.mockResolvedValue(VERSIONS);
    renderConsole();
    await waitFor(() => expect(promptTrigger().textContent).toContain('v18 \u00b7 full'));
  });

  it('picking a version persists it for the next visit', async () => {
    getConsolePromptVersions.mockResolvedValue(VERSIONS);
    renderConsole();
    await waitFor(() => expect(promptTrigger().textContent).toContain('v18'));
    fireEvent.click(promptTrigger());
    fireEvent.click(await screen.findByText('v16 \u00b7 full'));
    await waitFor(() =>
      expect(JSON.parse(window.localStorage.getItem(PROMPT_STORAGE_KEY) as string)).toEqual({ id: 'v-16' }),
    );
  });
});

describe('ChatbotConsole - item 6, the version pill', () => {
  it('a bot bubble wears the version its turn ran; user bubbles and null wear none', async () => {
    getConsolePromptVersions.mockResolvedValue(VERSIONS);
    postConsoleTurn.mockResolvedValueOnce(okTurn(18)).mockResolvedValueOnce(okTurn(null));
    renderConsole();
    await waitFor(() => expect(promptTrigger().textContent).toContain('v18'));

    fireEvent.change(textarea(), { target: { value: 'hello' } });
    fireEvent.keyDown(textarea(), { key: 'Enter' });
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    const pills = await screen.findAllByTestId('chatbot-console-prompt-pill');
    expect(pills).toHaveLength(1);
    expect(pills[0].textContent).toBe('v18');

    fireEvent.change(textarea(), { target: { value: 'again' } });
    fireEvent.keyDown(textarea(), { key: 'Enter' });
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    await screen.findByText('again');
    expect(screen.getAllByTestId('chatbot-console-prompt-pill')).toHaveLength(1);
  });
});
