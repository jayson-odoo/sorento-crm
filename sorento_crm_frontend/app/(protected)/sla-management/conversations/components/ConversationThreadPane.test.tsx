import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

/**
 * The Conversations inbox thread pane (UAC AC-N2 / AC-N3 / AC-N4).
 *
 * It renders the SAME shared list the ticket drawer does, driven by
 * contact-keyed loaders. Stubbed here so the suite is about the wiring: the
 * media proxy reaching the list, reply gated on the permission, Note gated on
 * the viewer holding exactly one open enquiry for the contact, and the
 * "Select a conversation" empty state.
 */
const contactThread = vi.fn();
const contactComments = vi.fn();
const replyMutateAsync = vi.fn();
const mediaProxy = vi.fn();
const commentMutateAsync = vi.fn();

vi.mock('../hooks/useConversationsInbox', () => ({
  useContactThread: (...a: unknown[]) => contactThread(...a),
  useContactComments: (...a: unknown[]) => contactComments(...a),
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
  contactCommentsKey: (ref: string | null) => ['conversation-contact-comments', ref],
}));

vi.mock(
  '@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTicketComments',
  () => ({
    useCreateTicketComment: (id: string) => ({
      mutateAsync: (input: unknown) => commentMutateAsync(id, input),
    }),
  }),
);

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock('@/components/common/RespondChatList', () => ({
  default: ({
    items,
    contactName,
    comments = [],
    mediaProxy: proxy,
  }: {
    items: unknown[];
    contactName?: string | null;
    comments?: unknown[];
    mediaProxy?: (url: string) => Promise<Response>;
  }) => (
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

vi.mock('@/components/common/conversation/SharedConversationComposer', () => ({
  default: ({
    canReply,
    notAvailableMessage,
    snippetTrackingId,
    sendAdapter,
  }: {
    canReply: boolean;
    notAvailableMessage?: string;
    snippetTrackingId?: string | null;
    sendAdapter?: (p: { text: string; files: File[] }) => Promise<unknown>;
  }) =>
    canReply ? (
      <button
        type="button"
        data-testid="inbox-composer-send"
        data-snippet-tracking-id={snippetTrackingId ?? ''}
        onClick={() => void sendAdapter?.({ text: 'hello', files: [] })}
      >
        Send
      </button>
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
vi.mock('sonner', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a) } }));

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
  replyMutateAsync.mockReset().mockResolvedValue({ sent_as: 'text', stamped_ticket_id: 'tkt-1' });
  commentMutateAsync.mockReset().mockResolvedValue({ id: 'c1' });
  toastSuccess.mockReset();
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

  it('Note posts against the open enquiry the viewer owns', async () => {
    render(<ConversationThreadPane contact={contact()} canReply />);

    fireEvent.click(screen.getByTestId('inbox-composer-mode-note'));
    fireEvent.click(screen.getByTestId('inbox-note-submit'));

    await waitFor(() =>
      expect(commentMutateAsync).toHaveBeenCalledWith('tkt-1', {
        body: 'internal note',
        mentioned_user_ids: [],
      }),
    );
  });

  it('Note is unavailable without exactly one open enquiry of the viewer', () => {
    render(
      <ConversationThreadPane
        contact={contact({ my_open_ticket_count: 2, my_open_ticket_id: null })}
        canReply
      />,
    );
    const note = screen.getByTestId('inbox-composer-mode-note');
    expect(note).toBeDisabled();

    fireEvent.click(note);
    expect(screen.queryByTestId('inbox-note-submit')).toBeNull();
    expect(screen.getByTestId('inbox-composer-send')).toBeDefined();
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
