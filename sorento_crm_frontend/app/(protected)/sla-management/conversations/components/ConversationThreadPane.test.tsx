import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

/**
 * The Conversations inbox thread pane (UAC AC-N2 / AC-N3 / AC-N4 / AC-K1).
 *
 * It renders the SAME shared list the ticket drawer does, driven by
 * contact-keyed loaders. Stubbed here so the suite is about the wiring: the
 * media proxy reaching the list, reply gated on the permission, the contact-
 * keyed Note, the contact-keyed window feeding the composer, the per-bubble
 * reply quote, and the "Select a conversation" empty state.
 */
const contactThread = vi.fn();
const contactComments = vi.fn();
const contactWindow = vi.fn();
const replyMutateAsync = vi.fn();
const templateMutateAsync = vi.fn();
const mediaProxy = vi.fn();
const commentMutateAsync = vi.fn();

vi.mock('../hooks/useConversationsInbox', () => ({
  THREAD_POLL_MS: 10_000,
  THREAD_POLL_LIVE_MS: 60_000,
  contactThreadKey: (ref: string | null) => ['conversation-contact-thread', ref],
  useContactThread: (...a: unknown[]) => contactThread(...a),
  useContactComments: (...a: unknown[]) => contactComments(...a),
  useContactWindow: (...a: unknown[]) => contactWindow(...a),
  useContactThreadLoaders: () => ({
    loadPage: vi.fn().mockResolvedValue({
      items: [],
      has_more_older: false,
      has_more_newer: false,
      oldest_message_id: null,
      newest_message_id: null,
    }),
    searchMessages: vi.fn().mockResolvedValue([]),
  }),
  useContactMediaProxy: () => mediaProxy,
  useReplyToContact: () => ({ mutateAsync: replyMutateAsync, isPending: false }),
  useSendContactTemplate: () => ({ mutateAsync: templateMutateAsync, isPending: false }),
  useCreateContactComment: (ref: string | null) => ({
    mutateAsync: (input: unknown) => commentMutateAsync(ref, input),
  }),
  contactCommentsKey: (ref: string | null) => ['conversation-contact-comments', ref],
}));

const invalidateQueries = vi.fn();
vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries }),
}));

// AC-K1 / AC-K2: the live-thread subscriber, stubbed so this suite stays about
// the pane. The hook itself is tested in components/common/conversation.
interface LiveEventsArgs {
  contactIds: (string | null | undefined)[];
  enabled: boolean;
  onEvent: () => void;
  onReady?: () => void;
}
const conversationEvents = vi.fn<(options: LiveEventsArgs) => { connected: boolean }>();
vi.mock('@/components/common/conversation/useConversationEvents', () => ({
  useConversationEvents: (options: LiveEventsArgs) => conversationEvents(options),
}));

interface ChatListStubProps {
  items: unknown[];
  contactName?: string | null;
  comments?: unknown[];
  mediaProxy?: (url: string) => Promise<Response>;
}

vi.mock('@/components/common/RespondChatList', () => ({
  default: ({ items, contactName, comments = [], mediaProxy: proxy }: ChatListStubProps) => (
    <div
      data-testid="chat-list"
      data-contact={contactName ?? ''}
      data-notes={comments.length}
      data-has-media-proxy={proxy ? 'yes' : 'no'}
    >
      {items.length} message(s)
    </div>
  ),
}));

interface ComposerStubProps {
  canReply: boolean;
  notAvailableMessage?: string;
  snippetTrackingId?: string | null;
  showTemplateButton?: boolean;
  windowStateOverride?: { closed: boolean; template?: unknown } | null;
  templateSendAdapter?: (input: {
    template_id: string;
    params: Record<string, string>;
  }) => Promise<unknown>;
  sendAdapter?: (p: { text: string; files: File[] }) => Promise<unknown>;
  onSent?: () => void | Promise<unknown>;
  pendingBubble?: { add: (input: { text: string; files: { name: string }[] }) => string; remove: (key: string) => void };
}

vi.mock('@/components/common/conversation/SharedConversationComposer', () => ({
  default: ({
    canReply,
    notAvailableMessage,
    snippetTrackingId,
    showTemplateButton,
    windowStateOverride,
    templateSendAdapter,
    sendAdapter,
    onSent,
    pendingBubble,
  }: ComposerStubProps) =>
    canReply ? (
      <div
        data-testid="inbox-composer"
        data-window-closed={String(!!windowStateOverride?.closed)}
        data-has-template={String(windowStateOverride?.template != null)}
        // Undefined means the composer's own default (shown), which is what the
        // inbox now wants.
        data-template-button={String(showTemplateButton !== false)}
      >
        <button
          type="button"
          data-testid="inbox-composer-send"
          data-snippet-tracking-id={snippetTrackingId ?? ''}
          // Mirrors the real composer's handleSend (M6-01): the pending bubble
          // goes up before the request, comes down once `onSent` settles (or
          // right away on failure) - the real composer catches a failed send
          // and toasts, so the stub swallows it the same way.
          onClick={() => {
            const key = pendingBubble?.add({ text: 'hello', files: [] });
            void sendAdapter
              ?.({ text: 'hello', files: [] })
              .then(async () => {
                const settled = onSent?.();
                if (settled && typeof (settled as PromiseLike<unknown>)?.then === 'function') {
                  await settled;
                }
              })
              .catch(() => undefined)
              .finally(() => {
                if (key) pendingBubble?.remove(key);
              });
          }}
        >
          Send
        </button>
        <button
          type="button"
          data-testid="inbox-composer-template"
          onClick={() =>
            void templateSendAdapter?.({ template_id: 'tpl-1', params: { '1': 'Aisyah' } })
          }
        >
          Send template
        </button>
      </div>
    ) : (
      <p data-testid="inbox-composer-unavailable">{notAvailableMessage}</p>
    ),
}));

vi.mock('@/components/common/conversation/InternalCommentComposer', () => ({
  default: ({
    onSubmit,
  }: {
    onSubmit: (p: { body: string; mentionedUserIds: string[] }) => Promise<unknown>;
  }) => (
    <button
      type="button"
      data-testid="inbox-note-submit"
      onClick={() => void onSubmit({ body: 'internal note', mentionedUserIds: [] })}
    >
      Add note
    </button>
  ),
}));

const toastSuccess = vi.fn();
vi.mock('@/lib/toast', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a) } }));

import ConversationThreadPane from './ConversationThreadPane';
import type { ConversationInboxItem } from '../services/conversationsInboxService';

function contact(over: Partial<ConversationInboxItem> = {}): ConversationInboxItem {
  return {
    contact_ref: '10025531',
    respond_io_id: '10025531',
    phone: '+60123456789',
    name: 'Aisyah Rahman',
    last_message_at: '2026-08-15T02:11:03',
    last_message_snippet: 'Yes please',
    last_message_direction: 'incoming',
    mentioned_at: null,
    open_ticket_count: 1,
    my_open_ticket_count: 1,
    my_open_ticket_id: 'tkt-1',
    ...over,
  };
}

function queryState(over: Record<string, unknown> = {}) {
  return {
    data: { items: [{ messageId: 1, traffic: 'incoming', message: { type: 'text', text: 'hi' } }] },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  contactThread.mockReset().mockReturnValue(queryState());
  contactComments.mockReset().mockReturnValue({ data: [], isLoading: false, isError: false });
  contactWindow.mockReset().mockReturnValue({
    data: { window: { open: true, expires_at: null }, chat_template: { configured: false } },
    isLoading: false,
    isError: false,
  });
  replyMutateAsync.mockReset().mockResolvedValue({ sent_as: 'text', stamped_ticket_id: 'tkt-1' });
  templateMutateAsync.mockReset().mockResolvedValue({ ok: true, stamped_ticket_id: 'tkt-1' });
  commentMutateAsync.mockReset().mockResolvedValue({ id: 'c1' });
  toastSuccess.mockReset();
  invalidateQueries.mockReset();
  conversationEvents.mockReset().mockReturnValue({ connected: false });
});

describe('ConversationThreadPane', () => {
  it('empty state before a conversation is picked', () => {
    render(<ConversationThreadPane contact={null} canReply />);
    expect(screen.getByTestId('thread-pane-empty')).toHaveTextContent('Select a conversation');
    expect(screen.queryByTestId('chat-list')).toBeNull();
  });

  it('renders the shared list with the contact-scoped media proxy (AC-N4)', () => {
    render(<ConversationThreadPane contact={contact()} canReply />);
    const list = screen.getByTestId('chat-list');
    expect(list).toHaveAttribute('data-contact', 'Aisyah Rahman');
    expect(list).toHaveAttribute('data-has-media-proxy', 'yes');
  });

  it('loading and error states', () => {
    contactThread.mockReturnValue(queryState({ data: undefined, isLoading: true }));
    const { unmount } = render(<ConversationThreadPane contact={contact()} canReply />);
    expect(screen.getByTestId('thread-loading')).toBeDefined();
    unmount();

    const refetch = vi.fn();
    contactThread.mockReturnValue(
      queryState({
        data: undefined,
        isError: true,
        error: new Error('Failed to load the conversation.'),
        refetch,
      }),
    );
    render(<ConversationThreadPane contact={contact()} canReply />);
    expect(screen.getByTestId('thread-error')).toHaveTextContent('Failed to load the conversation.');
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }));
    expect(refetch).toHaveBeenCalled();
  });

  it('replies through the contact route and says the send was counted (AC-N2)', async () => {
    render(<ConversationThreadPane contact={contact()} canReply />);

    fireEvent.click(screen.getByTestId('inbox-composer-send'));

    await waitFor(() =>
      expect(replyMutateAsync).toHaveBeenCalledWith({ text: 'hello', files: [] }),
    );
    expect(toastSuccess).toHaveBeenCalledWith(
      'Sent - counted as the reply to your open enquiry.',
    );
  });

  it('shows the pending bubble while the send is in flight and drops it after the refetch (AC-B1 / AC-B2)', async () => {
    let finishSend: (value: { sent_as: string; stamped_ticket_id: string | null }) => void = () => {};
    replyMutateAsync.mockReturnValue(
      new Promise((resolve) => {
        finishSend = resolve;
      }),
    );
    const refetch = vi.fn().mockResolvedValue({});
    contactThread.mockReturnValue(queryState({ refetch }));
    render(<ConversationThreadPane contact={contact()} canReply />);
    expect(screen.getByTestId('chat-list')).toHaveTextContent('1 message(s)');

    fireEvent.click(screen.getByTestId('inbox-composer-send'));

    await waitFor(() => expect(screen.getByTestId('chat-list')).toHaveTextContent('2 message(s)'));
    expect(refetch).not.toHaveBeenCalled();

    await act(async () => {
      finishSend({ sent_as: 'text', stamped_ticket_id: 'tkt-1' });
    });

    await waitFor(() => expect(screen.getByTestId('chat-list')).toHaveTextContent('1 message(s)'));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('a failed send takes the pending bubble down again (AC-B3)', async () => {
    replyMutateAsync.mockRejectedValue(new Error('Respond is down'));
    render(<ConversationThreadPane contact={contact()} canReply />);

    fireEvent.click(screen.getByTestId('inbox-composer-send'));

    await waitFor(() => expect(replyMutateAsync).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByTestId('chat-list')).toHaveTextContent('1 message(s)'));
  });

  it('an unstamped send still succeeds, quietly', async () => {
    replyMutateAsync.mockResolvedValue({ sent_as: 'text', stamped_ticket_id: null });
    render(<ConversationThreadPane contact={contact({ my_open_ticket_count: 0, my_open_ticket_id: null })} canReply />);

    fireEvent.click(screen.getByTestId('inbox-composer-send'));

    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Sent.'));
  });

  it('without the reply permission the composer says so instead of sending', () => {
    render(<ConversationThreadPane contact={contact()} canReply={false} />);
    expect(screen.getByTestId('inbox-composer-unavailable')).toHaveTextContent(
      'You do not have permission to reply to contacts.',
    );
    expect(screen.queryByTestId('inbox-composer-send')).toBeNull();
  });

  it('Note posts against the CONTACT, no ticket involved (AC-N3)', async () => {
    render(<ConversationThreadPane contact={contact()} canReply />);

    fireEvent.click(screen.getByTestId('inbox-composer-mode-note'));
    fireEvent.click(screen.getByTestId('inbox-note-submit'));

    await waitFor(() =>
      expect(commentMutateAsync).toHaveBeenCalledWith('10025531', {
        body: 'internal note',
        mentioned_user_ids: [],
      }),
    );
  });

  it('Note is offered even with no open enquiry of the viewer (AC-N3 gap closure)', async () => {
    render(
      <ConversationThreadPane
        contact={contact({ my_open_ticket_count: 0, my_open_ticket_id: null })}
        canReply
      />,
    );
    const note = screen.getByTestId('inbox-composer-mode-note');
    expect(note).not.toBeDisabled();

    fireEvent.click(note);
    fireEvent.click(screen.getByTestId('inbox-note-submit'));

    await waitFor(() =>
      expect(commentMutateAsync).toHaveBeenCalledWith('10025531', expect.anything()),
    );
  });

  it('Note is offered to a viewer who cannot reply - reading is the only gate', () => {
    render(<ConversationThreadPane contact={contact()} canReply={false} />);
    fireEvent.click(screen.getByTestId('inbox-composer-mode-note'));
    expect(screen.getByTestId('inbox-note-submit')).toBeDefined();
  });

  // ---- AC-N3 gap closure: window, template, quoted reply ------------------

  it('feeds the contact-keyed window into the composer and offers Send template', () => {
    contactWindow.mockReturnValue({
      data: {
        window: { open: false, expires_at: null },
        chat_template: { configured: true, slots: [] },
      },
      isLoading: false,
      isError: false,
    });
    render(<ConversationThreadPane contact={contact()} canReply />);

    const composer = screen.getByTestId('inbox-composer');
    expect(composer).toHaveAttribute('data-window-closed', 'true');
    expect(composer).toHaveAttribute('data-has-template', 'true');
    expect(composer).toHaveAttribute('data-template-button', 'true');
  });

  it('assumes an OPEN window until the live Respond read lands', () => {
    contactWindow.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    render(<ConversationThreadPane contact={contact()} canReply />);
    expect(screen.getByTestId('inbox-composer')).toHaveAttribute('data-window-closed', 'false');
  });

  it('sends a template through the contact-keyed route', async () => {
    render(<ConversationThreadPane contact={contact()} canReply />);

    fireEvent.click(screen.getByTestId('inbox-composer-template'));

    await waitFor(() =>
      expect(templateMutateAsync).toHaveBeenCalledWith({
        template_id: 'tpl-1',
        params: { '1': 'Aisyah' },
      }),
    );
  });

  // Outbound reply-to was removed on 2026-08-16 (Respond's send API has no
  // reply-to, so the ">" quote was theatre). Nothing here offers a per-bubble
  // Reply, and a send carries text + files only. Inbound quoted context is
  // untouched - it lives in RespondChatList and has its own suite.
  it('a send carries text and files only, with no quote reference', async () => {
    render(<ConversationThreadPane contact={contact()} canReply />);

    fireEvent.click(screen.getByTestId('inbox-composer-send'));

    await waitFor(() =>
      expect(replyMutateAsync).toHaveBeenCalledWith({ text: 'hello', files: [] }),
    );
  });

  // ---- AC-K1 / AC-K2: live thread ----------------------------------------

  it('AC-K2: no stream until a conversation is open, one for it once there is', () => {
    const { unmount } = render(<ConversationThreadPane contact={null} canReply />);
    expect(conversationEvents).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: false }),
    );
    unmount();

    conversationEvents.mockClear();
    render(<ConversationThreadPane contact={contact()} canReply />);
    expect(conversationEvents).toHaveBeenCalledWith(
      expect.objectContaining({ contactIds: ['10025531'], enabled: true }),
    );
  });

  it('AC-K1: a poke refetches the thread, the notes and the list row', () => {
    render(<ConversationThreadPane contact={contact()} canReply />);
    const { onEvent } = conversationEvents.mock.calls.at(-1)![0];
    invalidateQueries.mockClear();

    onEvent();

    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['conversation-contact-thread', '10025531'],
    });
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['conversation-contact-comments', '10025531'],
    });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['conversations-inbox'] });
  });

  it('AC-K1: the thread poll relaxes while the stream is connected', () => {
    conversationEvents.mockReturnValue({ connected: true });
    render(<ConversationThreadPane contact={contact()} canReply />);
    expect(contactThread).toHaveBeenCalledWith('10025531', { refetchIntervalMs: 60_000 });
  });

  it('AC-K1: the fast poll is the fallback while the stream is down', () => {
    render(<ConversationThreadPane contact={contact()} canReply />);
    expect(contactThread).toHaveBeenCalledWith('10025531', { refetchIntervalMs: 10_000 });
  });

  it('offers a way back to the list at phone width', () => {
    const onBack = vi.fn();
    render(<ConversationThreadPane contact={contact()} canReply onBack={onBack} />);
    const back = screen.getByTestId('thread-back');
    // Desktop shows both panes, so the control is mobile-only.
    expect(back.getAttribute('class') ?? '').toContain('lg:hidden');
    fireEvent.click(back);
    expect(onBack).toHaveBeenCalled();
  });
});
