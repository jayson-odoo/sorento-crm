import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

import InterventionTicketDrawer from './InterventionTicketDrawer';
import type { InterventionTicketDetail } from '../services/interventionTicketService';

const useInterventionTicket = vi.fn();
const useSlaTrackingConversation = vi.fn();
const useSlaTrackingThreadLoaders = vi.fn();
const useResolveInterventionTicket = vi.fn();
const useSendInterventionTicketMessage = vi.fn();
const useTicketComments = vi.fn();
const useCreateTicketComment = vi.fn();
const useDraftInterventionTicketReply = vi.fn();

vi.mock('../hooks/useInterventionTickets', () => ({
  useInterventionTicket: (...a: unknown[]) => useInterventionTicket(...a),
  useResolveInterventionTicket: (...a: unknown[]) => useResolveInterventionTicket(...a),
  useSendInterventionTicketMessage: (...a: unknown[]) => useSendInterventionTicketMessage(...a),
  useDraftInterventionTicketReply: (...a: unknown[]) => useDraftInterventionTicketReply(...a),
}));

vi.mock('../hooks/useTicketComments', () => ({
  useTicketComments: (...a: unknown[]) => useTicketComments(...a),
  useCreateTicketComment: (...a: unknown[]) => useCreateTicketComment(...a),
}));

// FINDING 9: the thread is the SHARED conversation query (one key with the SLA
// detail page's panel), not a private copy. The scroll-back / search loaders
// come through a hook too (layering: UI -> hook -> service), never as direct
// service imports in the component.
vi.mock('../hooks/useConversationSLATracking', () => ({
  useSlaTrackingConversation: (...a: unknown[]) => useSlaTrackingConversation(...a),
  useSlaTrackingThreadLoaders: (...a: unknown[]) => useSlaTrackingThreadLoaders(...a),
  // AC-N4: the chat-media byte loader handed to RespondChatList (stubbed here).
  useSlaTrackingMediaProxy: () => async () => new Response(),
}));

// jsdom does not implement scrollIntoView; guarded in the real component with
// `?.scrollIntoView?.(...)`, but RespondChatList is stubbed out here anyway.
vi.mock('@/components/common/RespondChatList', () => ({
  default: ({
    items,
    contactName,
    comments = [],
  }: {
    items: unknown[];
    contactName?: string | null;
    comments?: unknown[];
  }) => (
    <div data-testid="chat-list" data-contact={contactName ?? ''} data-notes={comments.length}>
      {items.length} message(s)
    </div>
  ),
}));

vi.mock('@/components/common/conversation/InternalCommentComposer', () => ({
  default: ({
    disabled,
    disabledMessage,
    onSubmit,
  }: {
    disabled?: boolean;
    disabledMessage?: string;
    onSubmit: (p: { body: string; mentionedUserIds: string[] }) => Promise<unknown>;
  }) =>
    disabled ? (
      <p data-testid="comment-composer-unavailable">{disabledMessage}</p>
    ) : (
      <button
        data-testid="comment-composer-submit"
        onClick={() => void onSubmit({ body: 'internal note', mentionedUserIds: ['u-2'] })}
      >
        Add note
      </button>
    ),
}));

vi.mock('@/components/common/conversation/SharedConversationComposer', () => ({
  default: ({
    canReply,
    attachmentsEnabled,
    notAvailableMessage,
    sendAdapter,
    templateSendTrackingId,
    onSent,
    snippetsEnabled,
    snippetTrackingId,
    emojiEnabled,
    onAiAssist,
  }: {
    canReply: boolean;
    attachmentsEnabled?: boolean;
    notAvailableMessage?: string;
    sendAdapter: (payload: { text: string; files: File[] }) => Promise<unknown>;
    templateSendTrackingId?: string | null;
    onSent?: () => void;
    snippetsEnabled?: boolean;
    snippetTrackingId?: string | null;
    emojiEnabled?: boolean;
    onAiAssist?: (input: { instruction?: string }) => Promise<string>;
  }) =>
    canReply ? (
      <>
        <button
          data-testid="composer-send"
          data-attachments-enabled={String(!!attachmentsEnabled)}
          data-template-tracking-id={templateSendTrackingId ?? ''}
          data-snippets-enabled={String(!!snippetsEnabled)}
          data-snippet-tracking-id={snippetTrackingId ?? ''}
          data-emoji-enabled={String(!!emojiEnabled)}
          data-ai-assist={String(!!onAiAssist)}
          onClick={() => void sendAdapter({ text: 'hello', files: [] })}
        >
          Send
        </button>
        <button data-testid="composer-sent" onClick={() => onSent?.()}>
          sent
        </button>
        <button
          data-testid="composer-ai-assist"
          onClick={() => void onAiAssist?.({ instruction: 'offer Tuesday delivery' })}
        >
          ai
        </button>
      </>
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

const thread = {
  items: [{ messageId: 1, traffic: 'incoming', message: { type: 'text', text: 'hi' } }],
  error: null,
};

let resolveMutate: ReturnType<typeof vi.fn>;
let sendMutateAsync: ReturnType<typeof vi.fn>;
let commentMutateAsync: ReturnType<typeof vi.fn>;
let aiDraftMutateAsync: ReturnType<typeof vi.fn>;

beforeEach(() => {
  useInterventionTicket.mockReset();
  useSlaTrackingConversation.mockReset();
  useSlaTrackingThreadLoaders.mockReset();
  useSlaTrackingThreadLoaders.mockReturnValue({
    loadPage: vi.fn().mockResolvedValue({
      items: [],
      has_more_older: false,
      has_more_newer: false,
      oldest_message_id: null,
      newest_message_id: null,
    }),
    searchMessages: vi.fn().mockResolvedValue([]),
  });
  useResolveInterventionTicket.mockReset();
  useSendInterventionTicketMessage.mockReset();
  useTicketComments.mockReset();
  useCreateTicketComment.mockReset();
  useDraftInterventionTicketReply.mockReset();

  aiDraftMutateAsync = vi.fn().mockResolvedValue({ draft: 'drafted', model: 'gpt-4o', grounded_on: 3, elapsed_ms: 10 });
  useDraftInterventionTicketReply.mockReturnValue({ mutateAsync: aiDraftMutateAsync });

  useTicketComments.mockReturnValue(mockQuery([]));
  commentMutateAsync = vi.fn().mockResolvedValue({ id: 'c1' });
  useCreateTicketComment.mockReturnValue({ mutateAsync: commentMutateAsync });

  resolveMutate = vi.fn((_id: string, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
  useResolveInterventionTicket.mockReturnValue({ mutate: resolveMutate, isPending: false });

  sendMutateAsync = vi.fn().mockResolvedValue({ sent_as: 'text' });
  useSendInterventionTicketMessage.mockReturnValue({ mutateAsync: sendMutateAsync });

  useSlaTrackingConversation.mockReturnValue(mockQuery(thread));
});

function renderDrawer(props: Partial<React.ComponentProps<typeof InterventionTicketDrawer>> = {}) {
  const onOpenChange = vi.fn();
  const onResolved = vi.fn();
  const onSent = vi.fn();
  render(
    <InterventionTicketDrawer
      ticketId="t1"
      open
      onOpenChange={onOpenChange}
      onResolved={onResolved}
      onSent={onSent}
      {...props}
    />,
  );
  return { onOpenChange, onResolved, onSent };
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

  it('FINDING 9: the thread comes from the SHARED conversation query, limit 50', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    renderDrawer();
    await waitFor(() => expect(screen.getByTestId('chat-list')).toBeInTheDocument());
    expect(useSlaTrackingConversation).toHaveBeenCalledWith(
      't1',
      expect.objectContaining({ limit: 50 }),
    );
  });

  it('FINDING 14: the scroll-back and search loaders come from a hook, keyed on the ticket', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    renderDrawer();
    await waitFor(() => expect(screen.getByTestId('chat-list')).toBeInTheDocument());
    expect(useSlaTrackingThreadLoaders).toHaveBeenCalledWith('t1');
  });

  it('an open drawer polls the thread, so a contact reply appears on its own', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    renderDrawer();
    await waitFor(() => expect(screen.getByTestId('chat-list')).toBeInTheDocument());
    expect(useSlaTrackingConversation).toHaveBeenCalledWith(
      't1',
      expect.objectContaining({ refetchIntervalMs: 10_000 }),
    );
  });

  it('a closed drawer asks for no ticket at all, so the polling stops with it', () => {
    useInterventionTicket.mockReturnValue(mockQuery(undefined));
    renderDrawer({ open: false });
    expect(useSlaTrackingConversation).toHaveBeenCalledWith(null, expect.anything());
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

  it('a send tells the worklist to reload, not just this drawer', async () => {
    // The worklist behind the drawer loads outside react-query, so nothing a
    // mutation invalidates reaches it - the drawer has to say so directly.
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    const { onSent } = renderDrawer();

    await waitFor(() => expect(screen.getByTestId('composer-sent')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('composer-sent'));

    expect(onSent).toHaveBeenCalled();
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
    // AC-M1: the drawer does NOT close itself - only the user closes it.
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect(onResolved).toHaveBeenCalled();
  });

  it('Resolve button is disabled when the ticket cannot be resolved', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket({ can_resolve: false })));
    renderDrawer();
    await waitFor(() => expect(screen.getByRole('button', { name: /Resolve ticket/i })).toBeDisabled());
  });

  // ---- AC-L1: comment mode -------------------------------------------------

  it('opens in Reply mode: the message composer is shown, the note composer is not', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    renderDrawer();

    await waitFor(() => expect(screen.getByTestId('composer-send')).toBeInTheDocument());
    expect(screen.queryByTestId('comment-composer-submit')).not.toBeInTheDocument();
    expect(screen.getByTestId('composer-mode-reply')).toHaveAttribute('aria-selected', 'true');
  });

  it('switching to Comment swaps the composer, so a note can never be sent to the contact', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    renderDrawer();

    await waitFor(() => expect(screen.getByTestId('composer-mode-comment')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('composer-mode-comment'));

    expect(screen.getByTestId('comment-composer-submit')).toBeInTheDocument();
    expect(screen.queryByTestId('composer-send')).not.toBeInTheDocument();
    expect(screen.getByTestId('composer-mode-comment')).toHaveAttribute('aria-selected', 'true');
  });

  it('adding a note calls the comment mutation, never the send mutation', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    renderDrawer();

    await waitFor(() => expect(screen.getByTestId('composer-mode-comment')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('composer-mode-comment'));
    fireEvent.click(screen.getByTestId('comment-composer-submit'));

    await waitFor(() =>
      expect(commentMutateAsync).toHaveBeenCalledWith({
        body: 'internal note',
        mentioned_user_ids: ['u-2'],
      }),
    );
    expect(sendMutateAsync).not.toHaveBeenCalled();
  });

  it('a resolved ticket disables the note composer with a reason', async () => {
    useInterventionTicket.mockReturnValue(
      mockQuery(makeTicket({ is_resolved: true, can_resolve: false })),
    );
    renderDrawer();

    await waitFor(() => expect(screen.getByTestId('composer-mode-comment')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('composer-mode-comment'));

    expect(screen.getByTestId('comment-composer-unavailable')).toHaveTextContent(
      'This ticket is resolved.',
    );
  });

  it('the notes reach the thread so they render inline with the messages', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    useTicketComments.mockReturnValue(
      mockQuery([
        {
          id: 'c1',
          tracking_id: 't1',
          body: 'Waiting on the warehouse.',
          author_name: 'Agent One',
          mentioned_names: [],
          source: 'crm',
          created_at: '2026-08-15T02:00:00',
        },
      ]),
    );
    renderDrawer();

    await waitFor(() => expect(screen.getByTestId('chat-list')).toHaveAttribute('data-notes', '1'));
  });

  it('a closed drawer loads no notes either', () => {
    useInterventionTicket.mockReturnValue(mockQuery(undefined));
    renderDrawer({ open: false });
    expect(useTicketComments).toHaveBeenCalledWith(null);
  });
});

// --------------------------------------------------------- composer parity
// UAC AC-L4 / AC-L5, slice S4.4. The drawer only says WHICH ticket; snippet
// variables and the AI grounding are both resolved server-side against it.

describe('InterventionTicketDrawer composer parity (AC-L4 / AC-L5)', () => {
  it('turns on the snippet picker for THIS ticket', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    renderDrawer();

    const send = await screen.findByTestId('composer-send');
    expect(send).toHaveAttribute('data-snippets-enabled', 'true');
    expect(send).toHaveAttribute('data-snippet-tracking-id', 't1');
  });

  it('turns on the emoji picker', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    renderDrawer();

    expect(await screen.findByTestId('composer-send')).toHaveAttribute(
      'data-emoji-enabled',
      'true',
    );
  });

  it('offers AI assist and passes the instruction through to the ticket draft', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    renderDrawer();

    expect(await screen.findByTestId('composer-send')).toHaveAttribute('data-ai-assist', 'true');
    fireEvent.click(screen.getByTestId('composer-ai-assist'));

    await waitFor(() =>
      expect(aiDraftMutateAsync).toHaveBeenCalledWith({
        instruction: 'offer Tuesday delivery',
      }),
    );
  });
});

// ------------------------------------------------ post-resolve reassurance
// UAC AC-M1 / AC-M2, slice S4.5. Resolving used to close the drawer, which
// yanked the conversation away at exactly the moment the assignee wants to
// re-read what they just agreed to.

describe('InterventionTicketDrawer resolved state (AC-M1 / AC-M2)', () => {
  it('stays open after a resolve and refetches the ticket into its Resolved state', async () => {
    const refetch = vi.fn();
    useInterventionTicket.mockReturnValue({ ...mockQuery(makeTicket()), refetch });
    const { onOpenChange, onResolved } = renderDrawer();

    fireEvent.click(await screen.findByRole('button', { name: /Resolve ticket/i }));
    fireEvent.click(await screen.findByRole('button', { name: /^Confirm$/i }));

    expect(onOpenChange).not.toHaveBeenCalled();
    expect(refetch).toHaveBeenCalled();
    // The worklist behind it still drops the row: it is no longer pending.
    expect(onResolved).toHaveBeenCalled();
  });

  it('shows a Resolved badge in the header once resolved', async () => {
    useInterventionTicket.mockReturnValue(
      mockQuery(makeTicket({ is_resolved: true, can_resolve: false, can_send: false })),
    );
    renderDrawer();

    expect(await screen.findByTestId('ticket-resolved-badge')).toHaveTextContent('Resolved');
  });

  it('keeps the thread and the notes readable while the composer is disabled with its reason', async () => {
    useInterventionTicket.mockReturnValue(
      mockQuery(makeTicket({ is_resolved: true, can_resolve: false, can_send: false })),
    );
    useTicketComments.mockReturnValue(
      mockQuery([
        {
          id: 'c1',
          tracking_id: 't1',
          body: 'Waiting on the warehouse.',
          author_name: 'Agent One',
          mentioned_names: [],
          source: 'crm',
          created_at: '2026-08-15T02:00:00',
        },
      ]),
    );
    renderDrawer();

    // Thread still rendered, notes still merged into it.
    expect(await screen.findByTestId('chat-list')).toHaveTextContent('1 message(s)');
    expect(screen.getByTestId('chat-list')).toHaveAttribute('data-notes', '1');
    // The reason is visible, not hidden behind a vanished composer.
    expect(screen.getByTestId('composer-unavailable')).toHaveTextContent(
      'This ticket is resolved.',
    );
    expect(screen.getByRole('button', { name: /Resolve ticket/i })).toBeDisabled();
  });

  it('offers View history to the SLA listing filtered to THIS contact', async () => {
    useInterventionTicket.mockReturnValue(
      mockQuery(makeTicket({ is_resolved: true, can_resolve: false, can_send: false })),
    );
    renderDrawer();

    const link = await screen.findByTestId('ticket-history-link');
    // The Respond.io contact id, never the CRM UUID.
    expect(link.querySelector('a') ?? link).toHaveAttribute(
      'href',
      '/sla-management/conversation-sla-tracking?contact=10025531',
    );
  });

  it('falls back to the phone number when the contact has no Respond id', async () => {
    useInterventionTicket.mockReturnValue(
      mockQuery(
        makeTicket({
          is_resolved: true,
          can_resolve: false,
          can_send: false,
          respond_io_id: null,
        }),
      ),
    );
    renderDrawer();

    const link = await screen.findByTestId('ticket-history-link');
    expect((link.querySelector('a') ?? link).getAttribute('href')).toBe(
      `/sla-management/conversation-sla-tracking?contact=${encodeURIComponent('+60 12-334 5566')}`,
    );
  });

  it('offers no history link while the ticket is still open - there is nothing to look back on yet', async () => {
    useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
    renderDrawer();

    await screen.findByTestId('composer-send');
    expect(screen.queryByTestId('ticket-history-link')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ticket-resolved-badge')).not.toBeInTheDocument();
  });

  // AC-N5(a)/(b): the ticket actions live in the header action group. They used
  // to sit in a footer under the composer, crowding its toolbar.
  describe('header action group (AC-N5)', () => {
    it('Resolve lives in the header group, above the composer', async () => {
      useInterventionTicket.mockReturnValue(mockQuery(makeTicket()));
      renderDrawer();

      const actions = await screen.findByTestId('ticket-header-actions');
      const resolve = screen.getByRole('button', { name: /Resolve ticket/i });
      expect(actions.contains(resolve)).toBe(true);

      // Header group precedes the composer in document order.
      const composer = screen.getByTestId('composer-send');
      expect(
        actions.compareDocumentPosition(composer) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    });

    it('the resolved-state affordances join the same group', async () => {
      useInterventionTicket.mockReturnValue(
        mockQuery(
          makeTicket({
            is_resolved: true,
            can_resolve: false,
            can_send: false,
            resolved_at: '2026-08-12T04:00:00',
          }),
        ),
      );
      renderDrawer();

      const actions = await screen.findByTestId('ticket-header-actions');
      expect(actions.contains(screen.getByTestId('ticket-resolved-at'))).toBe(true);
      expect(actions.contains(screen.getByTestId('ticket-history-link'))).toBe(true);
    });
  });
});
