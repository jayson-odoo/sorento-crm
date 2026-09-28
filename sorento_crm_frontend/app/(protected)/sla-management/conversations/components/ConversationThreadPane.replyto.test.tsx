/**
 * Reply-to in the contact conversation view (#1317, owner answer 3): the SLA
 * Conversations inbox pane carries the same bubble menu and swipe as ticket
 * resolving, through the real RespondChatList. A Note never quotes; Reply from
 * a bubble while on Note switches back to Reply, where the quote is waiting.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { openBubbleMenu, swipeRight } from '@/test-utils/replyGestures';
import type { ConversationInboxItem } from '../services/conversationsInboxService';

const QUESTION = {
  messageId: 1_786_000_001_000_000,
  traffic: 'incoming',
  message: { type: 'text', text: 'When is my delivery?' },
  status: [],
};

vi.mock('../hooks/useConversationsInbox', () => ({
  THREAD_POLL_MS: 10_000,
  THREAD_POLL_LIVE_MS: 60_000,
  contactThreadKey: (ref: string | null) => ['conversation-contact-thread', ref],
  contactCommentsKey: (ref: string | null) => ['conversation-contact-comments', ref],
  useContactThread: () => ({
    data: { items: [QUESTION] },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
  useContactComments: () => ({ data: [] }),
  useContactWindow: () => ({ data: undefined }),
  useContactThreadLoaders: () => ({ loadPage: vi.fn(), searchMessages: vi.fn() }),
  useContactMediaProxy: () => vi.fn(),
  useReplyToContact: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSendContactTemplate: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateContactComment: () => ({ mutateAsync: vi.fn() }),
}));

vi.mock('@/components/common/conversation/useConversationThread', () => ({
  useConversationThread: () => ({
    items: [QUESTION],
    jumpToMessage: vi.fn(),
    addPending: vi.fn(),
    removePending: vi.fn(),
    search: undefined,
  }),
}));

vi.mock('@/components/common/conversation/useConversationEvents', () => ({
  useConversationEvents: () => ({ connected: false }),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/components/common/conversation/InternalCommentComposer', () => ({
  default: () => <div data-testid="note-composer" />,
}));

type Target = { excerpt: string; senderLabel: string };
vi.mock('@/components/common/conversation/SharedConversationComposer', () => ({
  default: (props: { replyTo?: Target | null; onClearReplyTo?: () => void }) => (
    <div data-testid="inbox-composer">
      {props.replyTo && (
        <span data-testid="composer-quote">
          {props.replyTo.senderLabel}: {props.replyTo.excerpt}
        </span>
      )}
      <button type="button" onClick={() => props.onClearReplyTo?.()}>
        cancel reply
      </button>
    </div>
  ),
}));

import ConversationThreadPane from './ConversationThreadPane';

const CONTACT = {
  contact_ref: 'c-1',
  respond_io_id: '10025531',
  name: 'Mr Loo',
  phone: '+60123',
  my_open_ticket_id: null,
} as unknown as ConversationInboxItem;

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ConversationThreadPane reply-to (#1317)', () => {
  it('right click offers Reply, Copy; Reply puts the quote in the Reply composer', async () => {
    render(<ConversationThreadPane contact={CONTACT} canReply />);
    expect(screen.getByRole('button', { name: 'Message actions' })).toBeInTheDocument();
    expect(await openBubbleMenu('When is my delivery?')).toEqual(['Reply', 'Copy']);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Reply' }));
    expect(screen.getByTestId('composer-quote')).toHaveTextContent('Mr Loo: When is my delivery?');
  });

  it('swipe right starts the reply', () => {
    render(<ConversationThreadPane contact={CONTACT} canReply />);
    swipeRight('When is my delivery?');
    expect(screen.getByTestId('composer-quote')).toHaveTextContent('When is my delivery?');
  });

  it('on Note, a swipe switches to Reply with the quote; Note itself never shows it', () => {
    render(<ConversationThreadPane contact={CONTACT} canReply />);
    fireEvent.click(screen.getByTestId('inbox-composer-mode-note'));
    expect(screen.getByTestId('note-composer')).toBeInTheDocument();
    expect(screen.queryByTestId('composer-quote')).toBeNull();
    swipeRight('When is my delivery?');
    expect(screen.getByTestId('inbox-composer-mode-reply')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('composer-quote')).toBeInTheDocument();
  });

  it('without reply rights the menu is Copy only and a swipe does nothing', async () => {
    render(<ConversationThreadPane contact={CONTACT} canReply={false} />);
    swipeRight('When is my delivery?');
    expect(screen.queryByTestId('composer-quote')).toBeNull();
    expect(await openBubbleMenu('When is my delivery?')).toEqual(['Copy']);
  });

  it('another contact never inherits the quote', () => {
    const { rerender } = render(<ConversationThreadPane contact={CONTACT} canReply />);
    swipeRight('When is my delivery?');
    rerender(
      <ConversationThreadPane
        contact={{ ...CONTACT, contact_ref: 'c-2' } as ConversationInboxItem}
        canReply
      />,
    );
    expect(screen.queryByTestId('composer-quote')).toBeNull();
  });
});
