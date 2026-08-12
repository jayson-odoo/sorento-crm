import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

import InterventionTicketDrawer from './InterventionTicketDrawer';
import type { InterventionTicketDetail, InterventionTicketThread } from '../services/interventionTicketService';

const useInterventionTicket = vi.fn();
const useInterventionTicketThread = vi.fn();
const useResolveInterventionTicket = vi.fn();
const useSendInterventionTicketMessage = vi.fn();

vi.mock('../hooks/useInterventionTickets', () => ({
  useInterventionTicket: (...a: unknown[]) => useInterventionTicket(...a),
  useInterventionTicketThread: (...a: unknown[]) => useInterventionTicketThread(...a),
  useResolveInterventionTicket: (...a: unknown[]) => useResolveInterventionTicket(...a),
  useSendInterventionTicketMessage: (...a: unknown[]) => useSendInterventionTicketMessage(...a),
}));

// jsdom does not implement scrollIntoView; guarded in the real component with
// `?.scrollIntoView?.(...)`, but RespondChatList is stubbed out here anyway.
vi.mock('@/components/common/RespondChatList', () => ({
  default: ({ items, contactName }: { items: unknown[]; contactName?: string | null }) => (
    <div data-testid="chat-list" data-contact={contactName ?? ''}>
      {items.length} message(s)
    </div>
  ),
}));

vi.mock('@/components/common/conversation/SharedConversationComposer', () => ({
  default: ({
    canReply,
    attachmentsEnabled,
    notAvailableMessage,
    sendAdapter,
    templateSendTrackingId,
  }: {
    canReply: boolean;
    attachmentsEnabled?: boolean;
    notAvailableMessage?: string;
    sendAdapter: (payload: { text: string; files: File[] }) => Promise<unknown>;
    templateSendTrackingId?: string | null;
  }) =>
    canReply ? (
      <button
        data-testid="composer-send"
        data-attachments-enabled={String(!!attachmentsEnabled)}
        data-template-tracking-id={templateSendTrackingId ?? ''}
        onClick={() => void sendAdapter({ text: 'hello', files: [] })}
      >
        Send
      </button>
    ) : (
      <p data-testid="composer-unavailable">{notAvailableMessage}</p>
    ),
}));

function makeTicket(over: Partial<InterventionTicketDetail> = {}): InterventionTicketDetail {
  return {
    id: 't1',
    contact_name: 'Aisyah Rahman',
    contact_phone: '+60 12-334 5566',
    respond_io_id: '10025531',
    source_message_id: '123',
    source_message_text: 'Yes, please connect me to a person.',
    source_message_at: '2026-08-12T02:00:00',
    team_label: 'Customer Service - Tier 1',
    assignee_name: 'You',
    policy_name: 'Conversation SLA - Standard',
    initiated_at: '2026-08-12T02:00:00',
    current_tier: 1,
    escalated_at: null,
    escalation_reason: null,
    due_at: new Date(Date.now() + 46 * 60_000).toISOString(),
    due_at_resolution: new Date(Date.now() + 350 * 60_000).toISOString(),
    is_responded: false,
    responded_at: null,
    is_resolved: false,
    resolved_at: null,
    can_send: true,
    can_resolve: true,
    send_capabilities: ['text', 'attachment'],
    window: { open: true, expires_at: null },
    chat_template: null,
    ...over,
  };
}

function mockQuery<T>(data: T | undefined, opts: Partial<{ isLoading: boolean; isError: boolean; error: Error }> = {}) {
  return {
    data,
    isLoading: !!opts.isLoading,
    isError: !!opts.isError,
    error: opts.error ?? null,
    refetch: vi.fn(),
  };
}

const thread: InterventionTicketThread = {
  items: [{ messageId: 1, traffic: 'incoming', message: { type: 'text', text: 'hi' } } as never],
};

let resolveMutate: ReturnType<typeof vi.fn>;
let sendMutateAsync: ReturnType<typeof vi.fn>;

beforeEach(() => {
  useInterventionTicket.mockReset();
  useInterventionTicketThread.mockReset();
  useResolveInterventionTicket.mockReset();
  useSendInterventionTicketMessage.mockReset();

  resolveMutate = vi.fn((_id: string, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
  useResolveInterventionTicket.mockReturnValue({ mutate: resolveMutate, isPending: false });

  sendMutateAsync = vi.fn().mockResolvedValue({ sent_as: 'text' });
  useSendInterventionTicketMessage.mockReturnValue({ mutateAsync: sendMutateAsync });

  useInterventionTicketThread.mockReturnValue(mockQuery(thread));
});

function renderDrawer(props: Partial<React.ComponentProps<typeof InterventionTicketDrawer>> = {}) {
  const onOpenChange = vi.fn();
  const onResolved = vi.fn();
  render(
    <InterventionTicketDrawer
      ticketId="t1"
      open
      onOpenChange={onOpenChange}
      onResolved={onResolved}
      {...props}
    />,
  );
  return { onOpenChange, onResolved };
}

describe('InterventionTicketDrawer', () => {
  it('loading state: shows skeletons, no enquiry header yet', () => {
    useInterventionTicket.mockReturnValue(mockQuery(undefined, { isLoading: true }));
    renderDrawer();
    expect(screen.getByText(/Loading enquiry/i)).toBeInTheDocument();
    expect(screen.queryByText(/Yes, please connect/i)).not.toBeInTheDocument();
  });

  it('error state: shows the message and a retry button that refetches', () => {
    const refetch = vi.fn();
    useInterventionTicket.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Failed to load this ticket'),
      refetch,
    });
    renderDrawer();
    expect(screen.getByText('Failed to load this ticket')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }));
    expect(refetch).toHaveBeenCalled();
  });

  it('data state: renders enquiry header, chips, team, and the thread', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    renderDrawer();

    await waitFor(() => expect(screen.getByText('Aisyah Rahman')).toBeInTheDocument());
    expect(screen.getByText('Yes, please connect me to a person.')).toBeInTheDocument();
    expect(screen.getByText('Customer Service - Tier 1')).toBeInTheDocument();
    expect(screen.getByText(/Respond in/i)).toBeInTheDocument();
    expect(screen.getByTestId('chat-list')).toHaveTextContent('1 message(s)');
  });

  it('AC-E7: a blank enquiry text falls back to a neutral header label', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket({ source_message_text: '  ' })));
    renderDrawer();
    await waitFor(() =>
      expect(screen.getByText('No enquiry text captured.')).toBeInTheDocument(),
    );
  });

  it('composer: enabled + attachments on when the ticket allows sending', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    renderDrawer();
    await waitFor(() => expect(screen.getByTestId('composer-send')).toBeInTheDocument());
    expect(screen.getByTestId('composer-send')).toHaveAttribute('data-attachments-enabled', 'true');

    fireEvent.click(screen.getByTestId('composer-send'));
    await waitFor(() => expect(sendMutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ text: 'hello' }),
    ));
  });

  it('FINDING 4: the template send is stamped with this ticket id', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    renderDrawer();
    await waitFor(() => expect(screen.getByTestId('composer-send')).toBeInTheDocument());
    expect(screen.getByTestId('composer-send')).toHaveAttribute(
      'data-template-tracking-id',
      't1',
    );
  });

  it('composer: disabled with a reason once the ticket is resolved', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket({ is_resolved: true, can_resolve: false })));
    renderDrawer();
    await waitFor(() => expect(screen.getByTestId('composer-unavailable')).toBeInTheDocument());
    expect(screen.getByTestId('composer-unavailable')).toHaveTextContent('This ticket is resolved.');
  });

  it('resolve flow: confirm dialog copy names the sibling contact, confirming resolves only this ticket', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    const { onOpenChange, onResolved } = renderDrawer();

    await waitFor(() => expect(screen.getByRole('button', { name: /Resolve ticket/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Resolve ticket/i }));

    await waitFor(() => expect(screen.getByText('Mark as resolved')).toBeInTheDocument());
    expect(screen.getByText(/Other open enquiries from Aisyah Rahman stay open/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Confirm$/i }));
    expect(resolveMutate).toHaveBeenCalledWith('t1', expect.any(Object));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onResolved).toHaveBeenCalled();
  });

  it('Resolve button is disabled when the ticket cannot be resolved', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket({ can_resolve: false })));
    renderDrawer();
    await waitFor(() => expect(screen.getByRole('button', { name: /Resolve ticket/i })).toBeDisabled());
  });
});
