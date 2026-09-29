/**
 * Reply-to on every conversation surface (#1317, owner answer 3): the complaint,
 * stock inquiry and purchase request Chat Records carry the SAME bubble menu and
 * swipe as ticket resolving, through the real RespondChatList, and hand the
 * picked message to their composer as the quote.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { openBubbleMenu, swipeRight } from '@/test-utils/replyGestures';

const QUESTION = {
  messageId: 1_786_000_001_000_000,
  traffic: 'incoming',
  message: { type: 'text', text: 'Is the sink in stock?' },
  status: [],
};

const conversation = () => ({
  data: { items: [QUESTION], contact: { name: 'Mr Loo', phone: '+60123' } },
  isLoading: false,
  refetch: vi.fn().mockResolvedValue({}),
  isRefetching: false,
});

vi.mock('@/app/(protected)/complaint-management/complaints/hooks/useComplaints', () => ({
  useComplaintConversation: () => conversation(),
}));
vi.mock('@/app/(protected)/procurement-management/stock-inquiries/hooks/useStockInquiries', () => ({
  useStockInquiryConversation: () => conversation(),
}));
vi.mock('@/app/(protected)/procurement-management/purchase-requests/hooks/usePurchaseRequests', () => ({
  usePurchaseRequestConversation: () => conversation(),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));
vi.mock('@/components/common/conversation/useConversationWindowState', () => ({
  invalidateConversationWindow: vi.fn(),
}));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

type Target = { messageId: string | null; excerpt: string; senderLabel: string };
vi.mock('@/components/common/conversation/SharedConversationComposer', () => ({
  default: (props: {
    replyTo?: Target | null;
    onClearReplyTo?: (sent?: Target) => void;
  }) => (
    <div data-testid="composer">
      {props.replyTo && (
        <span data-testid="composer-quote">
          {props.replyTo.senderLabel}: {props.replyTo.excerpt}
        </span>
      )}
      <button type="button" onClick={() => props.onClearReplyTo?.()}>
        cancel reply
      </button>
      <button
        type="button"
        onClick={() => props.replyTo && props.onClearReplyTo?.(props.replyTo)}
      >
        sent
      </button>
    </div>
  ),
}));

import ComplaintConversationPanel from '@/app/(protected)/complaint-management/complaints/components/ComplaintConversationPanel';
import StockInquiryConversationPanel from '@/app/(protected)/procurement-management/stock-inquiries/components/StockInquiryConversationPanel';
import PurchaseRequestConversationPanel from '@/app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestConversationPanel';

const SURFACES: {
  name: string;
  mount: (id: string, canReply: boolean) => React.ReactElement;
}[] = [
  {
    name: 'complaint Chat Records',
    mount: (id, canReply) => <ComplaintConversationPanel complaintId={id} canReply={canReply} />,
  },
  {
    name: 'stock inquiry Chat Records',
    mount: (id, canReply) => <StockInquiryConversationPanel inquiryId={id} canReply={canReply} />,
  },
  {
    name: 'purchase request Chat Records',
    mount: (id, canReply) => (
      <PurchaseRequestConversationPanel requestId={id} canReply={canReply} />
    ),
  },
];

beforeEach(() => {
  vi.clearAllMocks();
});

describe.each(SURFACES)('$name', ({ mount }) => {
  it('right click offers Reply, Copy; Reply hands the composer the quote', async () => {
    render(mount('e1', true));
    expect(await openBubbleMenu('Is the sink in stock?')).toEqual(['Reply', 'Copy']);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Reply' }));
    expect(screen.getByTestId('composer-quote')).toHaveTextContent(
      'Mr Loo: Is the sink in stock?',
    );
  });

  it('a hover chevron is on the bubble', () => {
    render(mount('e1', true));
    expect(screen.getByRole('button', { name: 'Message actions' })).toBeInTheDocument();
  });

  it('swipe right past the threshold starts the same reply', () => {
    render(mount('e1', true));
    expect(screen.queryByTestId('composer-quote')).toBeNull();
    swipeRight('Is the sink in stock?');
    expect(screen.getByTestId('composer-quote')).toHaveTextContent('Is the sink in stock?');
  });

  it('Cancel and a completed send both drop the quote', () => {
    render(mount('e1', true));
    swipeRight('Is the sink in stock?');
    fireEvent.click(screen.getByRole('button', { name: 'cancel reply' }));
    expect(screen.queryByTestId('composer-quote')).toBeNull();
    swipeRight('Is the sink in stock?');
    fireEvent.click(screen.getByRole('button', { name: 'sent' }));
    expect(screen.queryByTestId('composer-quote')).toBeNull();
  });

  it('without reply rights the menu is Copy only and a swipe does nothing', async () => {
    render(mount('e1', false));
    swipeRight('Is the sink in stock?');
    expect(screen.queryByTestId('composer-quote')).toBeNull();
    expect(await openBubbleMenu('Is the sink in stock?')).toEqual(['Copy']);
  });

  it('another record never inherits the quote', () => {
    const { rerender } = render(mount('e1', true));
    swipeRight('Is the sink in stock?');
    expect(screen.getByTestId('composer-quote')).toBeInTheDocument();
    rerender(mount('e2', true));
    expect(screen.queryByTestId('composer-quote')).toBeNull();
  });
});
