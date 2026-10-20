/**
 * CHAT-CONSOLE-UX (AC-CX-1..16): the console composer works like WhatsApp.
 *
 * Reply is set from the bubble itself (swipe on touch, menu on desktop), voice is
 * tap-or-hold on a mic that is always there, and a pasted image stages with a preview
 * before Send. Every send still goes through the hook's `sendText` / `sendMedia`, so the
 * service mock below sees the same payloads the old dropdown and picker produced.
 *
 * jsdom has neither `MediaRecorder` nor `getUserMedia`; the voice cases install fakes.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen, waitFor, fireEvent, cleanup, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatbotConsole from './ChatbotConsole';
import { CONSOLE_GREETING_MESSAGES } from '../types/chatbotConsole.types';

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
  toast: { success: vi.fn(), error: (...args: unknown[]) => toastError(...args) },
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

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: ({ open, items }: { open: boolean; items: { name: string; url: string }[] }) =>
    open ? <div data-testid="attachment-preview" data-urls={items.map((i) => i.url).join(',')} /> : null,
}));

const EMPTY_TRACE = { tool: null, args_short: null, crossdomain_rungs: [], reveals_dropped: [] };

function turn(id: string, reply: string, messageId: string | null = null) {
  return {
    turn_id: id,
    branch_kind: 'business_query',
    reply_text: reply,
    quick_replies: [],
    send_messages: [],
    session_vars: {},
    trace_summary: EMPTY_TRACE,
    message_id: messageId,
  };
}

function mediaDone(reply = 'Got it.') {
  return { ...turn('tm', reply), media_status: 'done', media_id: 'm1', media_text: 'heard words', media_error: null };
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

function bubbleOf(text: string): HTMLElement {
  return screen.getByText(text).closest('[data-testid="message-bubble"]') as HTMLElement;
}

function touch(el: HTMLElement, type: 'pointerDown' | 'pointerMove' | 'pointerUp', x: number, y = 100) {
  fireEvent[type](el, { pointerType: 'touch', pointerId: 7, clientX: x, clientY: y, button: 0 });
}

async function replyViaMenu(text: string) {
  fireEvent.contextMenu(bubbleOf(text), { clientX: 20, clientY: 20 });
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Reply' }));
  await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
}

function fileInput(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement;
}

const png = (name = 'shot.png') => new File(['x'], name, { type: 'image/png' });

// ---- Fake recording stack (same shape as SharedConversationComposer.voice.test) ----

let tracks: { stop: ReturnType<typeof vi.fn> }[] = [];

class FakeRecorder {
  static isTypeSupported = (mime: string) => mime === 'audio/mp4';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  mimeType: string;
  constructor(_stream: unknown, options?: { mimeType?: string }) {
    this.mimeType = options?.mimeType ?? '';
  }
  start() {}
  stop() {
    this.ondataavailable?.({ data: new Blob(['audio-bytes'], { type: this.mimeType }) });
    this.onstop?.();
  }
}

function installRecordingStack({ deny = false }: { deny?: boolean } = {}) {
  tracks = [];
  const getUserMedia = vi.fn(async () => {
    if (deny) throw new Error('NotAllowedError');
    const track = { stop: vi.fn() };
    tracks.push(track);
    return { getTracks: () => [track] } as unknown as MediaStream;
  });
  Object.defineProperty(globalThis, 'MediaRecorder', { configurable: true, writable: true, value: FakeRecorder });
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    configurable: true,
    writable: true,
    value: { getUserMedia },
  });
}

function uninstallRecordingStack() {
  Reflect.deleteProperty(globalThis as Record<string, unknown>, 'MediaRecorder');
  Object.defineProperty(globalThis.navigator, 'mediaDevices', { configurable: true, writable: true, value: undefined });
}

function mic(): HTMLElement {
  return screen.getByRole('button', { name: /record voice message/i });
}

beforeEach(() => {
  postConsoleTurn.mockReset();
  getConsoleMediaStatus.mockReset();
  getConsolePromptVersions.mockReset();
  getConsolePromptVersions.mockResolvedValue([]);
  toastError.mockReset();
  window.localStorage.clear();
  window.localStorage.setItem('chatbot-console:last-contact', JSON.stringify({ id: 'ZZT-contact-1', label: 'Test Contact' }));
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    writable: true,
    value: (file: File) => `blob:staged/${file.name}`,
  });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, writable: true, value: vi.fn() });
});

afterEach(() => {
  cleanup();
  uninstallRecordingStack();
});

describe('reply from the bubble (AC-CX-1..6)', () => {
  it('AC-CX-6: there is no "Reply to" dropdown any more', async () => {
    postConsoleTurn.mockResolvedValueOnce(turn('t1', 'Which product do you mean?'));
    renderConsole();
    await send('price?');
    await screen.findByText('Which product do you mean?');
    expect(
      Array.from(document.querySelectorAll('[data-slot="searchable-select-trigger"]')).some((t) =>
        /reply to/i.test(`${t.getAttribute('aria-label') ?? ''} ${t.textContent ?? ''}`),
      ),
    ).toBe(false);
  });

  it('AC-CX-2/3: menu Reply on a bot bubble shows the bar and posts reply_to as n8n, then clears', async () => {
    postConsoleTurn
      .mockResolvedValueOnce(turn('t1', 'Which product do you mean?'))
      .mockResolvedValueOnce(turn('t2', 'Noted.'))
      .mockResolvedValueOnce(turn('t3', 'Done.'));
    renderConsole();
    await send('price?');
    await screen.findByText('Which product do you mean?');

    await replyViaMenu('Which product do you mean?');
    const bar = await screen.findByTestId('chatbot-console-reply-to');
    expect(within(bar).getByText('Which product do you mean?')).toBeInTheDocument();
    await waitFor(() => expect(document.activeElement).toBe(textarea()));

    await send('1 unit');
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    expect(postConsoleTurn.mock.calls[1][0].reply_to).toEqual({
      id: 'bot-t1-0',
      text: 'Which product do you mean?',
      source: 'n8n',
    });
    await screen.findByText('Noted.');
    expect(screen.queryByTestId('chatbot-console-reply-to')).not.toBeInTheDocument();

    await send('and 2');
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(3));
    expect(postConsoleTurn.mock.calls[2][0]).not.toHaveProperty('reply_to');
  });

  it('AC-CX-1: a touch swipe right on the customer bubble quotes it as the contact', async () => {
    postConsoleTurn
      .mockResolvedValueOnce(turn('t1', 'Which one?', 'console-abc123'))
      .mockResolvedValueOnce(turn('t2', 'Noted.'));
    renderConsole();
    await send('any WC with s trap?');
    await screen.findByText('Which one?');

    const bubble = bubbleOf('any WC with s trap?');
    touch(bubble, 'pointerDown', 10);
    touch(bubble, 'pointerMove', 40);
    touch(bubble, 'pointerMove', 90);
    touch(bubble, 'pointerUp', 90);

    const bar = await screen.findByTestId('chatbot-console-reply-to');
    expect(within(bar).getByText('any WC with s trap?')).toBeInTheDocument();
    await send('the second one');
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    expect(postConsoleTurn.mock.calls[1][0].reply_to).toEqual({
      id: 'console-abc123',
      text: 'any WC with s trap?',
      source: 'contact',
    });
  });

  it('AC-CX-4: Cancel drops the quote', async () => {
    postConsoleTurn.mockResolvedValueOnce(turn('t1', 'Which one?')).mockResolvedValueOnce(turn('t2', 'Ok.'));
    renderConsole();
    await send('hi');
    await screen.findByText('Which one?');
    await replyViaMenu('Which one?');
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel reply' }));
    expect(screen.queryByTestId('chatbot-console-reply-to')).not.toBeInTheDocument();
    await send('x');
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    expect(postConsoleTurn.mock.calls[1][0]).not.toHaveProperty('reply_to');
  });

  it('AC-CX-5: a greeting bubble offers Copy but no Reply', async () => {
    renderConsole();
    fireEvent.contextMenu(bubbleOf(CONSOLE_GREETING_MESSAGES[0]), { clientX: 20, clientY: 20 });
    expect(await screen.findByRole('menuitem', { name: 'Copy' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Reply' })).not.toBeInTheDocument();
  });
});

describe('voice (AC-CX-7..10)', () => {
  it('AC-CX-7: the mic is there without a recording stack and pressing it says why', async () => {
    renderConsole();
    fireEvent.pointerDown(mic(), { pointerId: 1, button: 0 });
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(String(toastError.mock.calls[0][0])).toMatch(/voice recording/i);
    expect(screen.queryByTestId('chatbot-console-recording')).not.toBeInTheDocument();
    expect(postConsoleTurn).not.toHaveBeenCalled();
  });

  it('AC-CX-8: tap opens the recording bar; Send posts the clip as audio media', async () => {
    installRecordingStack();
    postConsoleTurn.mockResolvedValueOnce(mediaDone());
    renderConsole();
    await waitFor(() => expect(mic()).toBeInTheDocument());
    fireEvent.pointerDown(mic(), { pointerId: 1, button: 0 });
    fireEvent.pointerUp(mic(), { pointerId: 1, button: 0 });
    const bar = await screen.findByTestId('chatbot-console-recording');
    expect(within(bar).getByText('0:00')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Send voice message' }));
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    expect(postConsoleTurn.mock.calls[0][0].media).toMatchObject({ kind: 'audio', mime: 'audio/mp4' });
    expect(screen.queryByTestId('chatbot-console-recording')).not.toBeInTheDocument();
    expect(tracks[0].stop).toHaveBeenCalled();
  });

  it('AC-CX-8: Delete discards the clip and releases the mic', async () => {
    installRecordingStack();
    renderConsole();
    fireEvent.pointerDown(mic(), { pointerId: 1, button: 0 });
    fireEvent.pointerUp(mic(), { pointerId: 1, button: 0 });
    await screen.findByTestId('chatbot-console-recording');
    fireEvent.click(screen.getByRole('button', { name: 'Delete recording' }));
    await waitFor(() => expect(screen.queryByTestId('chatbot-console-recording')).not.toBeInTheDocument());
    expect(tracks[0].stop).toHaveBeenCalled();
    expect(postConsoleTurn).not.toHaveBeenCalled();
  });

  it('AC-CX-9: hold then release sends', async () => {
    installRecordingStack();
    postConsoleTurn.mockResolvedValueOnce(mediaDone());
    renderConsole();
    const button = mic();
    fireEvent.pointerDown(button, { pointerId: 1, button: 0, clientX: 300 });
    await screen.findByTestId('chatbot-console-recording');
    await act(() => new Promise((r) => setTimeout(r, 450)));
    fireEvent.pointerUp(button, { pointerId: 1, button: 0, clientX: 300 });
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    expect(postConsoleTurn.mock.calls[0][0].media).toMatchObject({ kind: 'audio' });
  });

  it('AC-CX-9: hold and slide left cancels', async () => {
    installRecordingStack();
    renderConsole();
    const button = mic();
    fireEvent.pointerDown(button, { pointerId: 1, button: 0, clientX: 300 });
    await screen.findByTestId('chatbot-console-recording');
    await act(() => new Promise((r) => setTimeout(r, 450)));
    fireEvent.pointerMove(button, { pointerId: 1, clientX: 180 });
    fireEvent.pointerUp(button, { pointerId: 1, button: 0, clientX: 180 });
    await waitFor(() => expect(screen.queryByTestId('chatbot-console-recording')).not.toBeInTheDocument());
    expect(postConsoleTurn).not.toHaveBeenCalled();
    expect(tracks[0].stop).toHaveBeenCalled();
  });

  it('AC-CX-10: a denied microphone toasts and leaves the composer idle', async () => {
    installRecordingStack({ deny: true });
    renderConsole();
    fireEvent.pointerDown(mic(), { pointerId: 1, button: 0 });
    fireEvent.pointerUp(mic(), { pointerId: 1, button: 0 });
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(String(toastError.mock.calls[0][0])).toMatch(/microphone access is blocked/i);
    expect(screen.queryByTestId('chatbot-console-recording')).not.toBeInTheDocument();
    expect(mic()).not.toBeDisabled();
    expect(textarea()).not.toBeDisabled();
  });
});

describe('paste and staged attachments (AC-CX-11..15)', () => {
  it('AC-CX-11/12: a pasted image stages with a preview and Send posts it with the caption', async () => {
    postConsoleTurn.mockResolvedValueOnce(mediaDone('RM10.'));
    renderConsole();
    fireEvent.paste(textarea(), { clipboardData: { files: [png()] } });

    const staged = await screen.findByTestId('chatbot-console-staged');
    expect(within(staged).getByRole('img')).toHaveAttribute('src', 'blob:staged/shot.png');
    expect(postConsoleTurn).not.toHaveBeenCalled();

    fireEvent.click(within(staged).getByRole('button', { name: 'Preview shot.png' }));
    expect(await screen.findByTestId('attachment-preview')).toHaveAttribute('data-urls', 'blob:staged/shot.png');

    fireEvent.change(textarea(), { target: { value: 'price for this?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    expect(postConsoleTurn.mock.calls[0][0]).toMatchObject({
      text: 'price for this?',
      media: { kind: 'image', filename: 'shot.png', mime: 'image/png' },
    });
    expect(screen.queryByTestId('chatbot-console-staged')).not.toBeInTheDocument();
    expect(textarea().value).toBe('');
  });

  it('AC-CX-12: Send is enabled with a staged image and no text', async () => {
    renderConsole();
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();
    fireEvent.paste(textarea(), { clipboardData: { files: [png()] } });
    await screen.findByTestId('chatbot-console-staged');
    expect(screen.getByRole('button', { name: 'Send message' })).not.toBeDisabled();
  });

  it('AC-CX-13: a text paste stages nothing and is not prevented', () => {
    renderConsole();
    const event = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(event, 'clipboardData', { value: { files: [] } });
    textarea().dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
    expect(screen.queryByTestId('chatbot-console-staged')).not.toBeInTheDocument();
  });

  it('AC-CX-14: Remove clears the staged image', async () => {
    renderConsole();
    fireEvent.paste(textarea(), { clipboardData: { files: [png()] } });
    fireEvent.click(await screen.findByRole('button', { name: 'Remove shot.png' }));
    expect(screen.queryByTestId('chatbot-console-staged')).not.toBeInTheDocument();
  });

  it('AC-CX-15: a picked file stages instead of sending at once', async () => {
    postConsoleTurn.mockResolvedValueOnce(mediaDone());
    renderConsole();
    fireEvent.change(fileInput(), { target: { files: [png('photo.png')] } });
    await screen.findByTestId('chatbot-console-staged');
    expect(postConsoleTurn).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(1));
    expect(postConsoleTurn.mock.calls[0][0].media).toMatchObject({ kind: 'image', filename: 'photo.png' });
  });
});

describe('a quote rides a voice note or image too (Q2 (b), crew 20 Oct)', () => {
  it('a pasted image sent with a quote posts the same reply_to and shows the quote', async () => {
    postConsoleTurn.mockResolvedValueOnce(turn('t1', 'Which one?')).mockResolvedValueOnce(mediaDone());
    renderConsole();
    await send('any WC?');
    await screen.findByText('Which one?');
    await replyViaMenu('Which one?');
    fireEvent.paste(textarea(), { clipboardData: { files: [png()] } });
    await screen.findByTestId('chatbot-console-staged');
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    expect(postConsoleTurn.mock.calls[1][0]).toMatchObject({
      media: { kind: 'image' },
      reply_to: { id: 'bot-t1-0', text: 'Which one?', source: 'n8n' },
    });
    expect(screen.queryByTestId('chatbot-console-reply-to')).not.toBeInTheDocument();
    // The quote shows on the sent image bubble as well as the bot's own bubble.
    await waitFor(() => expect(screen.getAllByText('Which one?')).toHaveLength(2));
  });

  it('a voice note sent with a quote posts reply_to', async () => {
    installRecordingStack();
    postConsoleTurn.mockResolvedValueOnce(turn('t1', 'Which one?')).mockResolvedValueOnce(mediaDone());
    renderConsole();
    await send('any WC?');
    await screen.findByText('Which one?');
    await replyViaMenu('Which one?');
    fireEvent.pointerDown(mic(), { pointerId: 1, button: 0 });
    fireEvent.pointerUp(mic(), { pointerId: 1, button: 0 });
    await screen.findByTestId('chatbot-console-recording');
    fireEvent.click(screen.getByRole('button', { name: 'Send voice message' }));

    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    expect(postConsoleTurn.mock.calls[1][0]).toMatchObject({
      media: { kind: 'audio' },
      reply_to: { id: 'bot-t1-0', source: 'n8n' },
    });
  });
});

describe('voice under React StrictMode (next dev)', () => {
  it('records after the dev double mount: the remount must not read as unmounted', async () => {
    installRecordingStack();
    postConsoleTurn.mockResolvedValueOnce(mediaDone());
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <React.StrictMode>
        <QueryClientProvider client={client}>
          <ChatbotConsole />
        </QueryClientProvider>
      </React.StrictMode>,
    );
    fireEvent.pointerDown(mic(), { pointerId: 1, button: 0 });
    fireEvent.pointerUp(mic(), { pointerId: 1, button: 0 });
    await screen.findByTestId('chatbot-console-recording');
    expect(tracks[0].stop).not.toHaveBeenCalled();
  });
});

describe('review round: quote on the follow-up and Retry, reset hygiene, never-lost clip', () => {
  const QUOTE = { id: 'bot-t1-0', text: 'Which one?', source: 'n8n' };

  async function quoteThenPaste() {
    await send('any WC?');
    await screen.findByText('Which one?');
    await replyViaMenu('Which one?');
    fireEvent.paste(textarea(), { clipboardData: { files: [png()] } });
    await screen.findByTestId('chatbot-console-staged');
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
  }

  it('AC-CX-18: a pending quoted image carries the quote on the follow-up turn after the poll', async () => {
    postConsoleTurn
      .mockResolvedValueOnce(turn('t1', 'Which one?'))
      .mockResolvedValueOnce({ ...turn('tm', ''), turn_id: null, media_status: 'pending', media_id: 'job-1', media_text: null, media_error: null })
      .mockResolvedValueOnce(turn('t3', 'RM10.'));
    getConsoleMediaStatus.mockResolvedValueOnce({ status: 'done', text: 'SRTWC8517 label', error: null });
    renderConsole();
    await quoteThenPaste();

    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(3), { timeout: 8000 });
    expect(postConsoleTurn.mock.calls[1][0].reply_to).toEqual(QUOTE);
    expect(postConsoleTurn.mock.calls[2][0]).toMatchObject({ text: 'SRTWC8517 label', reply_to: QUOTE });
  }, 15000);

  it('AC-CX-18: Retry on a failed quoted image resends the quote', async () => {
    postConsoleTurn
      .mockResolvedValueOnce(turn('t1', 'Which one?'))
      .mockResolvedValueOnce({ ...turn('tm', ''), turn_id: null, media_status: 'failed', media_id: null, media_text: null, media_error: 'refused' })
      .mockResolvedValueOnce({ ...turn('tm2', ''), turn_id: null, media_status: 'failed', media_id: null, media_text: null, media_error: 'refused' });
    renderConsole();
    await quoteThenPaste();
    fireEvent.click(await screen.findByRole('button', { name: 'Retry' }));

    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(3));
    expect(postConsoleTurn.mock.calls[2][0]).toMatchObject({ media: { kind: 'image' }, reply_to: QUOTE });
  });

  it('Reset drops the quote and the staged image', async () => {
    postConsoleTurn.mockResolvedValueOnce(turn('t1', 'Which one?'));
    renderConsole();
    await send('any WC?');
    await screen.findByText('Which one?');
    await replyViaMenu('Which one?');
    fireEvent.paste(textarea(), { clipboardData: { files: [png()] } });
    await screen.findByTestId('chatbot-console-staged');

    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
    await waitFor(() => expect(screen.queryByTestId('chatbot-console-reply-to')).not.toBeInTheDocument());
    expect(screen.queryByTestId('chatbot-console-staged')).not.toBeInTheDocument();
  });

  it('a clip finished while another turn is in flight stages instead of vanishing', async () => {
    installRecordingStack();
    let release: (v: unknown) => void = () => {};
    postConsoleTurn
      .mockResolvedValueOnce({ ...turn('t1', 'Which one?'), quick_replies: ['The first'] })
      .mockReturnValueOnce(new Promise((r) => (release = r)));
    renderConsole();
    await send('any WC?');
    await screen.findByText('Which one?');
    fireEvent.pointerDown(mic(), { pointerId: 1, button: 0 });
    fireEvent.pointerUp(mic(), { pointerId: 1, button: 0 });
    await screen.findByTestId('chatbot-console-recording');
    // A chip starts a turn while the bar is up, then the bar's Send fires mid-turn.
    fireEvent.click(screen.getByRole('button', { name: 'The first' }));
    await waitFor(() => expect(postConsoleTurn).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole('button', { name: 'Send voice message' }));

    const staged = await screen.findByTestId('chatbot-console-staged');
    expect(within(staged).getByRole('button', { name: /^Remove voice-message-/ })).toBeInTheDocument();
    expect(toastError).toHaveBeenCalled();
    expect(postConsoleTurn).toHaveBeenCalledTimes(2);
    release(turn('t2', 'Ok.'));
  });

  it('a recorder that throws on start ends idle with a message', async () => {
    installRecordingStack();
    FakeRecorder.prototype.start = () => {
      throw new Error('NotSupportedError');
    };
    try {
      renderConsole();
      fireEvent.pointerDown(mic(), { pointerId: 1, button: 0 });
      fireEvent.pointerUp(mic(), { pointerId: 1, button: 0 });
      await waitFor(() => expect(toastError).toHaveBeenCalled());
      expect(screen.queryByTestId('chatbot-console-recording')).not.toBeInTheDocument();
      // Not wedged: the next press reaches the recorder again.
      toastError.mockReset();
      fireEvent.pointerDown(mic(), { pointerId: 2, button: 0 });
      await waitFor(() => expect(toastError).toHaveBeenCalled());
    } finally {
      FakeRecorder.prototype.start = function start() {};
    }
  });

  it('Enter or Space on the mic starts recording with the bar (keyboard users)', async () => {
    installRecordingStack();
    renderConsole();
    fireEvent.click(mic(), { detail: 0 });
    await screen.findByTestId('chatbot-console-recording');
    expect(screen.getByRole('button', { name: 'Send voice message' })).toBeInTheDocument();
  });
});
