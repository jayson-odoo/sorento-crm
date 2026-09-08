/**
 * The in-app chatbot console's media path (commit 2, chatbot growth r1 final): image and
 * voice through the real extractor.
 *
 * The service layer is mocked; the real HTTP contract (the real media pipeline, the
 * ledger, the RQ job) is proved by the backend's own
 * `tests/chatbot/test_console_media_turn.py`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatbotConsole from './ChatbotConsole';

const postConsoleTurn = vi.fn();
const getConsolePromptVersions = vi.fn();
const getConsoleMediaStatus = vi.fn();
const toastError = vi.fn();

vi.mock('../services/chatbotConsoleService', () => ({
  postConsoleTurn: (...args: unknown[]) => postConsoleTurn(...args),
  getConsolePromptVersions: (...args: unknown[]) => getConsolePromptVersions(...args),
  getConsoleMediaStatus: (...args: unknown[]) => getConsoleMediaStatus(...args),
}));

vi.mock('@/lib/toast', () => ({
  toast: {
    success: vi.fn(),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

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
const EMPTY_TRACE = { tool: null, args_short: null, crossdomain_rungs: [], reveals_dropped: [] };

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

function fileInput(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement;
}

function pngFile(name = 'photo.png'): File {
  return new File(['fake-bytes'], name, { type: 'image/png' });
}

beforeEach(() => {
  postConsoleTurn.mockReset();
  getConsolePromptVersions.mockReset();
  getConsolePromptVersions.mockResolvedValue([]);
  getConsoleMediaStatus.mockReset();
  toastError.mockReset();
  window.localStorage.clear();
  seedContact();
});

afterEach(() => cleanup());

describe('ChatbotConsole media - image, pending then done', () => {
  it('shows a status bubble, then the extracted text and the reply once the poll resolves', async () => {
    postConsoleTurn.mockResolvedValueOnce({
      turn_id: null,
      branch_kind: null,
      reply_text: '',
      quick_replies: [],
      send_messages: [],
      session_vars: null,
      trace_summary: EMPTY_TRACE,
      media_status: 'pending',
      media_id: 'job-1',
      media_text: null,
      media_error: null,
    });
    getConsoleMediaStatus.mockResolvedValueOnce({ status: 'pending', text: null, error: null });
    getConsoleMediaStatus.mockResolvedValueOnce({ status: 'done', text: 'SRTWC8517 label', error: null });
    postConsoleTurn.mockResolvedValueOnce({
      turn_id: 'turn-2',
      branch_kind: 'business_query',
      reply_text: 'SRTWC8517 is RM10.',
      quick_replies: [],
      send_messages: [],
      session_vars: {},
      trace_summary: EMPTY_TRACE,
      media_status: null,
      media_id: null,
      media_text: null,
      media_error: null,
    });

    renderConsole();
    fireEvent.change(fileInput(), { target: { files: [pngFile()] } });

    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Reading image...')).toBeInTheDocument();

    await waitFor(() => expect(getConsoleMediaStatus).toHaveBeenCalled(), { timeout: 6000 });
    expect(
      await screen.findByText('Read from image: SRTWC8517 label', undefined, { timeout: 8000 }),
    ).toBeInTheDocument();
    expect(await screen.findByText('SRTWC8517 is RM10.', undefined, { timeout: 8000 })).toBeInTheDocument();
    expect(postConsoleTurn).toHaveBeenCalledTimes(2);
    expect(postConsoleTurn.mock.calls[1][0]).toMatchObject({ text: 'SRTWC8517 label' });
  }, 15000);
});

describe('ChatbotConsole media - voice fallback', () => {
  it('offers no record button in an environment with no MediaRecorder, and the attach input still takes audio', async () => {
    renderConsole();
    // jsdom has no MediaRecorder / getUserMedia, so useVoiceRecorder reports unavailable
    // and the composer must not render a button that cannot work.
    expect(screen.queryByLabelText(/record a voice message/i)).not.toBeInTheDocument();
    expect(fileInput().accept).toContain('audio/*');
  });
});

describe('ChatbotConsole media - retry chip', () => {
  it('a failed extraction with no caption shows Retry, which resends the same attachment', async () => {
    postConsoleTurn.mockResolvedValueOnce({
      turn_id: null,
      branch_kind: null,
      reply_text: '',
      quick_replies: [],
      send_messages: [],
      session_vars: null,
      trace_summary: EMPTY_TRACE,
      media_status: 'failed',
      media_id: null,
      media_text: null,
      media_error: 'This contact’s media access refused the attachment (denied_gate).',
    });

    renderConsole();
    fireEvent.change(fileInput(), { target: { files: [pngFile()] } });

    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    const retryChip = await screen.findByRole('button', { name: 'Retry' });

    postConsoleTurn.mockResolvedValueOnce({
      turn_id: null,
      branch_kind: null,
      reply_text: '',
      quick_replies: [],
      send_messages: [],
      session_vars: null,
      trace_summary: EMPTY_TRACE,
      media_status: 'failed',
      media_id: null,
      media_text: null,
      media_error: 'still refused',
    });
    fireEvent.click(retryChip);

    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    expect(postConsoleTurn.mock.calls[1][0]).toMatchObject({
      media: { kind: 'image', filename: 'photo.png', mime: 'image/png' },
    });
  });
});
