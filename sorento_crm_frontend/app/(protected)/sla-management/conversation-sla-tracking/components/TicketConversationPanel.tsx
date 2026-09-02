'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import RespondChatList from '@/components/common/RespondChatList';
import InternalCommentComposer from '@/components/common/conversation/InternalCommentComposer';
import SharedConversationComposer from '@/components/common/conversation/SharedConversationComposer';
import { useConversationEvents } from '@/components/common/conversation/useConversationEvents';
import { useConversationThread } from '@/components/common/conversation/useConversationThread';

import {
  useSlaTrackingConversation,
  useSlaTrackingMediaProxy,
  useSlaTrackingThreadLoaders,
} from '../hooks/useConversationSLATracking';
import {
  useDraftInterventionTicketReply,
  useInterventionTicket,
  useSendInterventionTicketMessage,
} from '../hooks/useInterventionTickets';
import {
  ticketCommentsKey,
  useCreateTicketComment,
  useTicketComments,
} from '../hooks/useTicketComments';

/**
 * How often an open panel re-reads the thread with NO live stream (paused in a
 * background tab). This is the fallback lane of AC-K1.
 */
const THREAD_POLL_MS = 10_000;
/**
 * The same poll while the live stream IS connected. Belt and braces: the stream
 * already pokes on every inbound message, so this only has to catch the case
 * where a poke was published while the socket was momentarily down.
 */
const THREAD_POLL_LIVE_MS = 60_000;

export interface TicketJumpRequest {
  messageId: string | null;
  /** Bump to (re)trigger the jump - asking for the SAME message twice scrolls twice. */
  nonce: number;
}

interface TicketConversationPanelProps {
  /** The conversation SLA tracking / intervention ticket this thread belongs to. */
  ticketId: string | null;
  /** False while the surface holding it is closed: no poll, no stream, no reads. */
  enabled?: boolean;
  maxHeightClass?: string;
  /**
   * Scroll the thread to a message, fetching the page around it when it is
   * outside the loaded window. The (id, nonce) pair is the same idiom
   * `RespondChatList` takes, one level up: the drawer's quoted enquiry bumps
   * the nonce, and asking for the same id twice scrolls twice.
   */
  jumpRequest?: TicketJumpRequest | null;
  /** Called after a reply goes out, for surfaces that load imperatively. */
  onSent?: () => void;
  /**
   * Whether replying is possible when there is NO ticket detail to read
   * (`GET /{id}/ticket` 404s for a form-scope tracker, and for a viewer outside
   * the ticket's act-scope). The composer then falls back to the shared entity
   * chat send, exactly as this surface behaved before.
   */
  fallbackCanReply?: boolean;
  /** Shown in that fallback when replying is not possible either. */
  fallbackNotAvailableMessage?: string;
  className?: string;
}

/**
 * THE conversation panel: the shared contact thread, its internal notes, and
 * the Reply / Comment composers.
 *
 * One component, two mounts - the intervention-ticket drawer and the SLA
 * detail page's "Chat Records" sheet. They used to be two call sites passing
 * two different prop sets, and the detail page quietly lost attachments,
 * snippets, emoji, AI assist, the manual template send, the 24h-window state
 * and the note composer. Anything that is a capability of the thread lives
 * here; anything that is a property of the TICKET (header, clocks, resolve,
 * reassign, extend, the quoted enquiry) stays with the caller.
 */
export default function TicketConversationPanel({
  ticketId,
  enabled = true,
  maxHeightClass = 'max-h-[45vh]',
  jumpRequest = null,
  onSent,
  fallbackCanReply = false,
  fallbackNotAvailableMessage = 'Replying is not available for this contact.',
  className,
}: TicketConversationPanelProps) {
  // Reply talks to the contact; Comment never leaves the CRM. Two modes, one
  // switch, so nobody can WhatsApp a customer while meaning to leave a note.
  const [composerMode, setComposerMode] = useState<'reply' | 'comment'>('reply');
  const queryClient = useQueryClient();

  const activeId = enabled ? ticketId : null;
  // The SAME query key the caller's header reads: react-query serves both from
  // one cache entry, so this is not a second round trip.
  const ticketQuery = useInterventionTicket(activeId);
  const ticket = ticketQuery.data;

  // ---- AC-K1: live thread. One stream, only while this panel is mounted on a
  // contact (AC-K2), and it carries no content - every poke turns straight into
  // a refetch through the ordinary REST endpoints, which is what makes a
  // replayed or duplicated event a no-op on screen (AC-K4).
  const onLiveEvent = useCallback(
    (event: { type: string }) => {
      if (!ticketId) return;
      if (event.type === 'message') {
        // A NOTE is poked as `message` too (the backend publishes EVENT_MESSAGE
        // for a comment), so the note list refreshes on the same event.
        void queryClient.invalidateQueries({ queryKey: ['sla-tracking-conversation', ticketId] });
        void queryClient.invalidateQueries({ queryKey: ticketCommentsKey(ticketId) });
        return;
      }
      // ticket_created / ticket_updated: clocks, assignee, resolution.
      void queryClient.invalidateQueries({ queryKey: ['intervention-ticket', ticketId] });
    },
    [queryClient, ticketId],
  );
  const onLiveReady = useCallback(() => {
    if (!ticketId) return;
    // A (re)connect may have missed pokes while the socket was down, so treat
    // the handshake itself as one.
    void queryClient.invalidateQueries({ queryKey: ['sla-tracking-conversation', ticketId] });
    void queryClient.invalidateQueries({ queryKey: ticketCommentsKey(ticketId) });
    void queryClient.invalidateQueries({ queryKey: ['intervention-ticket', ticketId] });
  }, [queryClient, ticketId]);
  const { connected: liveConnected } = useConversationEvents({
    contactIds: [ticket?.respond_io_id],
    enabled: enabled && !!ticketId,
    onEvent: onLiveEvent,
    onReady: onLiveReady,
  });

  // Polls while the panel is open (and the tab is focused): a contact's reply
  // arrives on their schedule, not on ours, so an assignee reading the thread
  // must see it without hunting for a refresh. The interval relaxes while the
  // live stream is up - it is then a safety net, not the mechanism.
  const threadQuery = useSlaTrackingConversation(activeId, {
    limit: 50,
    refetchIntervalMs: liveConnected ? THREAD_POLL_LIVE_MS : THREAD_POLL_MS,
  });
  const sendMutation = useSendInterventionTicketMessage(ticketId ?? '');
  const commentsQuery = useTicketComments(activeId);
  const commentMutation = useCreateTicketComment(ticketId ?? '');
  const aiDraftMutation = useDraftInterventionTicketReply(ticketId ?? '');

  // A different ticket means a different enquiry: never carry comment mode
  // into someone else's conversation.
  useEffect(() => {
    setComposerMode('reply');
  }, [ticketId]);

  // AC-L7 / AC-L8: scroll-back and search live in the SHARED thread hook.
  const { loadPage, searchMessages } = useSlaTrackingThreadLoaders(ticketId);
  // AC-N4: chat media has no CORS, so the preview reads its bytes through the
  // ticket-scoped backend proxy - that is what makes an .xlsx open inline here.
  const mediaProxy = useSlaTrackingMediaProxy(ticketId);
  const thread = useConversationThread({
    liveItems: threadQuery.data?.items ?? [],
    loadPage,
    searchMessages,
    enabled: enabled && !!ticketId,
    resetKey: ticketId,
  });

  const { jumpToMessage } = thread;
  const handledJumpNonce = useRef(0);
  useEffect(() => {
    if (!jumpRequest?.nonce || jumpRequest.nonce === handledJumpNonce.current) return;
    handledJumpNonce.current = jumpRequest.nonce;
    jumpToMessage(jumpRequest.messageId);
  }, [jumpRequest, jumpToMessage]);

  const isResolved = !!ticket?.is_resolved;
  const canReply = ticket ? ticket.can_send && !isResolved : fallbackCanReply;
  const notAvailableMessage = ticket
    ? isResolved
      ? 'This ticket is resolved.'
      : 'Replying is not available for this contact.'
    : fallbackNotAvailableMessage;

  const handleSent = () => {
    void ticketQuery.refetch();
    // Returned so the composer's optimistic bubble (M6-01) waits for the
    // thread's own refetch before it comes down - the real row and the
    // placeholder are never both missing on screen at once.
    const threadRefetched = threadQuery.refetch();
    onSent?.();
    return threadRefetched;
  };

  return (
    <div className={cn('flex min-h-0 flex-col gap-3', className)}>
      {threadQuery.isLoading ? (
        <div className="space-y-2" data-testid="chat-records-loading">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : threadQuery.isError ? (
        <div
          data-testid="chat-records-error"
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <div className="min-w-0">
            <p>
              {threadQuery.error instanceof Error
                ? threadQuery.error.message
                : 'Failed to load the conversation.'}
            </p>
            <Button
              size="sm"
              variant="outline"
              className="mt-2 h-7"
              onClick={() => void threadQuery.refetch()}
            >
              Try again
            </Button>
          </div>
        </div>
      ) : (
        <>
          {threadQuery.data?.error && (
            <p className="text-xs text-muted-foreground">{threadQuery.data.error}</p>
          )}
          {thread.error && <p className="text-xs text-destructive">{thread.error}</p>}
          <RespondChatList
            items={thread.items}
            contactName={ticket?.contact_name}
            contactPhone={ticket?.contact_phone}
            emptyHint="No messages in this conversation yet."
            maxHeightClass={maxHeightClass}
            highlightMessageId={ticket?.source_message_id}
            highlightLabel="This enquiry"
            onLoadOlder={thread.loadOlder}
            hasMoreOlder={thread.hasMoreOlder}
            isLoadingOlder={thread.isLoadingOlder}
            atConversationStart={thread.atConversationStart}
            isDetached={thread.isDetached}
            onJumpToLatest={thread.jumpToLatest}
            newerUnseenCount={thread.newerUnseenCount}
            onLoadNewer={thread.loadNewer}
            hasMoreNewer={thread.hasMoreNewer}
            isLoadingNewer={thread.isLoadingNewer}
            searchController={thread.search}
            highlightTerm={thread.highlightTerm}
            focusMessageId={thread.focusMessageId}
            focusNonce={thread.focusNonce}
            comments={commentsQuery.data ?? []}
            mediaProxy={mediaProxy}
          />
        </>
      )}

      {/* ---- Mode switch: message the contact, or note to the team ---- */}
      {ticket && (
        <div
          role="tablist"
          aria-label="Composer mode"
          className="flex w-full gap-1 rounded-md border bg-muted/40 p-1"
        >
          {(['reply', 'comment'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              role="tab"
              aria-selected={composerMode === mode}
              data-testid={`composer-mode-${mode}`}
              onClick={() => setComposerMode(mode)}
              className={cn(
                'flex-1 rounded px-3 py-1.5 text-sm font-medium transition-colors',
                composerMode === mode
                  ? mode === 'comment'
                    ? 'bg-amber-500 text-white shadow-sm'
                    : 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {mode === 'reply' ? 'Reply' : 'Comment'}
            </button>
          ))}
        </div>
      )}

      {ticket && composerMode === 'comment' && (
        <InternalCommentComposer
          disabled={isResolved}
          disabledMessage="This ticket is resolved."
          onSubmit={({ body, mentionedUserIds }) =>
            commentMutation.mutateAsync({
              body,
              mentioned_user_ids: mentionedUserIds,
            })
          }
        />
      )}

      {/* Held back while the ticket is still loading: its window state and send
          capabilities decide what the composer even offers, and a flash of
          "replying is not available" is a lie the next render corrects. */}
      {composerMode === 'reply' && !ticketQuery.isLoading && (
        <SharedConversationComposer
          entityType="conversation_sla"
          entityId={ticket?.id ?? ticketId ?? ''}
          canReply={canReply}
          mode="conversation"
          attachmentsEnabled={!!ticket?.send_capabilities.includes('attachment')}
          // A manual template send is a reply too: stamp THIS ticket, or the
          // response clock runs on while the contact has an answer.
          templateSendTrackingId={ticket?.id ?? null}
          // Composer parity with Respond's own inbox (UAC AC-L4 / AC-L5).
          // Snippet variables resolve against THIS ticket, and the AI draft is
          // grounded on THIS thread - both server-side, so the panel only has
          // to say which ticket it is.
          snippetsEnabled={!!ticket}
          snippetTrackingId={ticket?.id ?? null}
          emojiEnabled={!!ticket}
          onAiAssist={
            ticket
              ? async ({ instruction }) => {
                  const result = await aiDraftMutation.mutateAsync({ instruction });
                  return result.draft;
                }
              : undefined
          }
          onSent={handleSent}
          // Optimistic send (M6-01): the bubble goes up before the request
          // completes and comes down once `handleSent`'s thread refetch lands.
          pendingBubble={{ add: thread.addPending, remove: thread.removePending }}
          windowStateOverride={
            ticket ? { closed: !ticket.window.open, template: ticket.chat_template } : null
          }
          sendAdapter={
            ticket
              ? (payload) =>
                  sendMutation.mutateAsync({ text: payload.text, attachments: payload.files })
              : undefined
          }
          notAvailableMessage={notAvailableMessage}
        />
      )}
    </div>
  );
}
