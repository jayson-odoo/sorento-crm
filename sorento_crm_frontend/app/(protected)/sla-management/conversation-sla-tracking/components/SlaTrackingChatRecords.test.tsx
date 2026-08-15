import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

/**
 * "Chat Records" on the SLA detail page (UAC AC-N8).
 *
 * The legacy panel was a hand-rolled bubble list with none of the drawer's
 * capabilities. What is pinned here is that it now renders the SHARED thread -
 * one `RespondChatList`, with the scroll-back controller, the search
 * controller, the interleaved notes and the ticket-scoped media proxy - plus
 * the states the CRUD standard asks for.
 */
const slaConversation = vi.fn();
const ticketComments = vi.fn();

vi.mock('../hooks/useConversationSLATracking', () => ({
  useSlaTrackingConversation: (...a: unknown[]) => slaConversation(...a),
  useSlaTrackingThreadLoaders: () => ({
    loadPage: vi.fn().mockResolvedValue({
      items: [],
      has_more_older: false,
      has_more_newer: false,
      oldest_message_id: null,
      newest_message_id: null,
    }),
    searchMessages: vi.fn().mockResolvedValue([]),
  }),
  useSlaTrackingMediaProxy: () => async () => new Response(),
}));

vi.mock('../hooks/useTicketComments', () => ({
  useTicketComments: (...a: unknown[]) => ticketComments(...a),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock('@/components/common/RespondChatList', () => ({
  default: ({
    items,
    comments = [],
    mediaProxy,
    searchController,
    onLoadOlder,
  }: {
    items: unknown[];
    comments?: unknown[];
    mediaProxy?: unknown;
    searchController?: unknown;
    onLoadOlder?: () => void;
  }) => (
    <div
      data-testid="chat-list"
      data-notes={comments.length}
      data-has-media-proxy={mediaProxy ? 'yes' : 'no'}
      data-has-search={searchController ? 'yes' : 'no'}
      data-has-scrollback={onLoadOlder ? 'yes' : 'no'}
    >
      {items.length} message(s)
    </div>
  ),
}));

vi.mock('@/components/common/conversation/SharedConversationComposer', () => ({
  default: ({ canReply, notAvailableMessage }: { canReply: boolean; notAvailableMessage?: string }) =>
    canReply ? (
      <button type="button" data-testid="composer-send">
        Send
      </button>
    ) : (
      <p data-testid="composer-unavailable">{notAvailableMessage}</p>
    ),
}));

import SlaTrackingChatRecords from './SlaTrackingChatRecords';

function queryState(over: Record<string, unknown> = {}) {
  return {
    data: { items: [{ messageId: 1, traffic: 'incoming', message: { type: 'text', text: 'hi' } }] },
    isLoading: false,
    isError: false,
    isRefetching: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  slaConversation.mockReset().mockReturnValue(queryState());
  ticketComments.mockReset().mockReturnValue({ data: [{ id: 'c1' }], isLoading: false });
});

describe('SlaTrackingChatRecords (AC-N8)', () => {
  it('renders the shared thread with scroll-back, search, notes and the media proxy', () => {
    render(<SlaTrackingChatRecords trackingId="t1" respondInboxUrl="https://respond.io/x" showAsPopup />);

    const list = screen.getByTestId('chat-list');
    expect(list).toHaveTextContent('1 message(s)');
    expect(list).toHaveAttribute('data-has-scrollback', 'yes');
    expect(list).toHaveAttribute('data-has-search', 'yes');
    expect(list).toHaveAttribute('data-has-media-proxy', 'yes');
    expect(list).toHaveAttribute('data-notes', '1');
  });

  it('loading state', () => {
    slaConversation.mockReturnValue(queryState({ data: undefined, isLoading: true }));
    render(<SlaTrackingChatRecords trackingId="t1" respondInboxUrl="https://respond.io/x" />);
    expect(screen.getByTestId('chat-records-loading')).toBeDefined();
  });

  it('error state offers a retry', () => {
    const refetch = vi.fn();
    slaConversation.mockReturnValue(
      queryState({
        data: undefined,
        isError: true,
        error: new Error('Failed to load the conversation.'),
        refetch,
      }),
    );
    render(<SlaTrackingChatRecords trackingId="t1" respondInboxUrl="https://respond.io/x" />);
    expect(screen.getByTestId('chat-records-error')).toHaveTextContent(
      'Failed to load the conversation.',
    );
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }));
    expect(refetch).toHaveBeenCalled();
  });

  it('says why replying is unavailable when no Respond conversation is linked', () => {
    render(<SlaTrackingChatRecords trackingId="t1" respondInboxUrl={null} />);
    expect(screen.getByTestId('composer-unavailable')).toHaveTextContent(
      'No Respond conversation link available for this contact.',
    );
  });

  it('refresh re-reads the thread', () => {
    const refetch = vi.fn();
    slaConversation.mockReturnValue(queryState({ refetch }));
    render(<SlaTrackingChatRecords trackingId="t1" respondInboxUrl="https://respond.io/x" showAsPopup />);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh messages' }));
    expect(refetch).toHaveBeenCalled();
  });
});
