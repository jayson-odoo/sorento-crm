import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ComplaintConversationPanel from './ComplaintConversationPanel';

/**
 * M6-01: this panel has no `useConversationThread` scroll-back window - it is
 * a plain react-query list - so it wires `usePendingThreadItems` directly and
 * merges the bubble into what it feeds `RespondChatList`. Everything else
 * about the bubble (shape, dim, timing) is covered once at the hook /
 * composer / RespondChatList level; this only proves the wiring.
 */

const refetch = vi.fn().mockResolvedValue({});
vi.mock('../hooks/useComplaints', () => ({
  useComplaintConversation: () => ({
    data: { items: [{ messageId: 1, traffic: 'incoming', message: { type: 'text', text: 'hi' } }] },
    isLoading: false,
    refetch,
    isRefetching: false,
  }),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({}),
}));

vi.mock('@/components/common/conversation/useConversationWindowState', () => ({
  invalidateConversationWindow: vi.fn(),
}));

let lastChatListProps: { items: unknown[] } | null = null;
vi.mock('@/components/common/RespondChatList', () => ({
  default: (props: { items: unknown[] }) => {
    lastChatListProps = props;
    return <div data-testid="chat-list">{props.items.length} message(s)</div>;
  },
}));

interface ComposerStubProps {
  onSent?: () => void | Promise<unknown>;
  pendingBubble?: {
    add: (input: { text: string; files: { name: string }[] }) => string;
    remove: (key: string) => void;
  };
}
let lastPendingKey: string | undefined;
vi.mock('@/components/common/conversation/SharedConversationComposer', () => ({
  default: ({ onSent, pendingBubble }: ComposerStubProps) => (
    <>
      <button
        type="button"
        data-testid="send"
        onClick={() => {
          lastPendingKey = pendingBubble?.add({ text: 'hello', files: [] });
          void onSent?.();
        }}
      >
        Send
      </button>
      <button
        type="button"
        data-testid="settle"
        onClick={() => {
          if (lastPendingKey) pendingBubble?.remove(lastPendingKey);
        }}
      >
        Settle
      </button>
    </>
  ),
}));

describe('ComplaintConversationPanel - optimistic send wiring (M6-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    lastChatListProps = null;
  });

  it('merges the pending bubble into the items handed to RespondChatList, then drops it', () => {
    render(<ComplaintConversationPanel complaintId="c1" canReply />);
    expect(screen.getByTestId('chat-list')).toHaveTextContent('1 message(s)');

    fireEvent.click(screen.getByTestId('send'));
    expect(screen.getByTestId('chat-list')).toHaveTextContent('2 message(s)');

    fireEvent.click(screen.getByTestId('settle'));
    expect(screen.getByTestId('chat-list')).toHaveTextContent('1 message(s)');
    expect(lastChatListProps).not.toBeNull();
  });

  it('onSent forwards the refetch promise', () => {
    render(<ComplaintConversationPanel complaintId="c1" canReply />);
    fireEvent.click(screen.getByTestId('send'));
    expect(refetch).toHaveBeenCalled();
  });
});
