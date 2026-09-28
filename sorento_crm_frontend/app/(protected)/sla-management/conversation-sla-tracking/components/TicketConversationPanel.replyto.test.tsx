/**
 * The ticket panel owns the reply target (#1317, AC-RT-3/5/16): Reply from a
 * bubble switches to the Reply tab and hands the composer the quote; Comment
 * never carries it; a resolved ticket offers no Reply; another ticket clears it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';

import type { InterventionTicketDetail } from '../services/interventionTicketService';

const chatListProps: Record<string, unknown>[] = [];
const composerProps: Record<string, unknown>[] = [];
const sendMutateAsync = vi.fn();
const interventionTicket = vi.fn();

vi.mock('../hooks/useConversationSLATracking', () => ({
  useSlaTrackingConversation: () => ({
    data: { items: [] },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
  useSlaTrackingThreadLoaders: () => ({ loadPage: vi.fn(), searchMessages: vi.fn() }),
  useSlaTrackingMediaProxy: () => async () => new Response(),
}));

vi.mock('../hooks/useTicketComments', () => ({
  ticketCommentsKey: (id: string | null) => ['ticket-comments', id],
  useTicketComments: () => ({ data: [], isLoading: false }),
  useCreateTicketComment: () => ({ mutateAsync: vi.fn() }),
}));

vi.mock('../hooks/useInterventionTickets', () => ({
  useInterventionTicket: (...a: unknown[]) => interventionTicket(...a),
  useSendInterventionTicketMessage: () => ({ mutateAsync: sendMutateAsync }),
  useDraftInterventionTicketReply: () => ({ mutateAsync: vi.fn() }),
}));

vi.mock('@/components/common/conversation/useConversationEvents', () => ({
  useConversationEvents: () => ({ connected: false }),
}));

vi.mock('@/components/common/conversation/useConversationThread', () => ({
  useConversationThread: () => ({
    items: [],
    jumpToMessage: vi.fn(),
    addPending: vi.fn(),
    removePending: vi.fn(),
    search: {},
  }),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock('@/components/common/RespondChatList', () => ({
  default: (props: Record<string, unknown>) => {
    chatListProps.push(props);
    const onReply = props.onReply as ((t: unknown) => void) | undefined;
    return (
      <button
        type="button"
        data-testid="fake-bubble-reply"
        onClick={() =>
          onReply?.({ messageId: '11', excerpt: 'Is the sink in stock?', senderLabel: 'Mr Loo' })
        }
      >
        reply
      </button>
    );
  },
}));

vi.mock('@/components/common/conversation/SharedConversationComposer', () => ({
  default: (props: Record<string, unknown>) => {
    composerProps.push(props);
    const replyTo = props.replyTo as { excerpt: string } | null;
    return (
      <div data-testid="composer">
        {replyTo && <span data-testid="composer-quote">{replyTo.excerpt}</span>}
        <button type="button" onClick={() => (props.onClearReplyTo as () => void)?.()}>
          clear
        </button>
      </div>
    );
  },
}));

vi.mock('@/components/common/conversation/InternalCommentComposer', () => ({
  default: () => <div data-testid="note-composer" />,
}));

import TicketConversationPanel from './TicketConversationPanel';

const TICKET = {
  id: 't1',
  contact_name: 'Mr Loo',
  respond_io_id: '10025531',
  source_message_id: '11',
  is_resolved: false,
  can_send: true,
  send_capabilities: ['text', 'attachment'],
  window: { open: true, expires_at: null },
  chat_template: null,
} as unknown as InterventionTicketDetail;

function ticketResult(ticket: InterventionTicketDetail) {
  return { data: ticket, isLoading: false, isError: false, error: null, refetch: vi.fn() };
}

beforeEach(() => {
  chatListProps.length = 0;
  composerProps.length = 0;
  sendMutateAsync.mockReset().mockResolvedValue({ sent_as: 'text' });
  interventionTicket.mockReset().mockReturnValue(ticketResult(TICKET));
});

describe('TicketConversationPanel reply-to', () => {
  it('AC-RT-1/6: hands the thread a Reply (the menu itself is on every RespondChatList)', () => {
    render(<TicketConversationPanel ticketId="t1" />);
    const props = chatListProps.at(-1)!;
    expect(typeof props.onReply).toBe('function');
  });

  it('AC-RT-3: Reply from Comment mode switches to the Reply tab with the quote', () => {
    render(<TicketConversationPanel ticketId="t1" />);
    fireEvent.click(screen.getByTestId('composer-mode-comment'));
    expect(screen.getByTestId('note-composer')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('fake-bubble-reply'));
    expect(screen.getByTestId('composer-mode-reply')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('composer-quote')).toHaveTextContent('Is the sink in stock?');
  });

  it('AC-RT-16: Comment hides the quote, Reply brings it back', () => {
    render(<TicketConversationPanel ticketId="t1" />);
    fireEvent.click(screen.getByTestId('fake-bubble-reply'));
    fireEvent.click(screen.getByTestId('composer-mode-comment'));
    expect(screen.queryByTestId('composer-quote')).toBeNull();
    fireEvent.click(screen.getByTestId('composer-mode-reply'));
    expect(screen.getByTestId('composer-quote')).toHaveTextContent('Is the sink in stock?');
  });

  it('AC-RT-14: the composer can dismiss it', () => {
    render(<TicketConversationPanel ticketId="t1" />);
    fireEvent.click(screen.getByTestId('fake-bubble-reply'));
    fireEvent.click(screen.getByText('clear'));
    expect(screen.queryByTestId('composer-quote')).toBeNull();
  });

  it('AC-RT-17: a stale post-send clear leaves a newer pick alone', () => {
    render(<TicketConversationPanel ticketId="t1" />);
    fireEvent.click(screen.getByTestId('fake-bubble-reply'));
    const clear = composerProps.at(-1)!.onClearReplyTo as (sent?: unknown) => void;
    act(() => clear({ messageId: 'older', excerpt: 'older quote', senderLabel: 'Mr Loo' }));
    expect(screen.getByTestId('composer-quote')).toHaveTextContent('Is the sink in stock?');
  });

  it('AC-RT-17: the ticket send forwards the audit fields', async () => {
    render(<TicketConversationPanel ticketId="t1" />);
    const adapter = composerProps.at(-1)!.sendAdapter as (p: unknown) => Promise<unknown>;
    await act(async () => {
      await adapter({ text: '> q\nbody', files: [], replyToMessageId: '11', replyToExcerpt: 'q' });
    });
    expect(sendMutateAsync).toHaveBeenCalledWith({
      text: '> q\nbody',
      attachments: [],
      reply_to_message_id: '11',
      reply_to_excerpt: 'q',
    });
  });

  it('AC-RT-5: a resolved ticket offers the menu without Reply', () => {
    interventionTicket.mockReturnValue(ticketResult({ ...TICKET, is_resolved: true }));
    render(<TicketConversationPanel ticketId="t1" />);
    const props = chatListProps.at(-1)!;
    expect(props.onReply).toBeUndefined();
  });

  it('AC-RT-16: another ticket clears the quote', () => {
    const { rerender } = render(<TicketConversationPanel ticketId="t1" />);
    fireEvent.click(screen.getByTestId('fake-bubble-reply'));
    expect(screen.getByTestId('composer-quote')).toBeInTheDocument();
    interventionTicket.mockReturnValue(ticketResult({ ...TICKET, id: 't2' }));
    rerender(<TicketConversationPanel ticketId="t2" />);
    expect(screen.queryByTestId('composer-quote')).toBeNull();
  });
});
