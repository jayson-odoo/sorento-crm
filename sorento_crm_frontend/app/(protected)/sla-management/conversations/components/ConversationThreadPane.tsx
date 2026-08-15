'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, ArrowLeft, MessagesSquare } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import RespondChatList from '@/components/common/RespondChatList';
import InternalCommentComposer from '@/components/common/conversation/InternalCommentComposer';
import SharedConversationComposer from '@/components/common/conversation/SharedConversationComposer';
import { excerptOfMessage } from '@/components/common/conversation/quotedReply';
import { useConversationEvents } from '@/components/common/conversation/useConversationEvents';
import { useConversationThread } from '@/components/common/conversation/useConversationThread';
import { cn } from '@/lib/utils';

import {
  contactCommentsKey,
  contactThreadKey,
  THREAD_POLL_LIVE_MS,
  THREAD_POLL_MS,
  useContactComments,
  useContactMediaProxy,
  useContactThread,
  useContactThreadLoaders,
  useContactWindow,
  useCreateContactComment,
  useReplyToContact,
  useSendContactTemplate,
} from '../hooks/useConversationsInbox';
import type { ConversationInboxItem } from '../services/conversationsInboxService';
import { useQueryClient } from '@tanstack/react-query';

interface ConversationThreadPaneProps {
  contact: ConversationInboxItem | null;
  /** False hides the composer's Reply mode entirely (read-only viewer). */
  canReply: boolean;
  /** Mobile only: returns to the list. */
  onBack?: () => void;
  className?: string;
}

/**
 * The right pane (UAC AC-N2 / AC-N3): the SAME shared thread the ticket drawer
 * renders - scroll-back, in-thread search, attachment preview, interleaved
 * notes - driven by contact-keyed loaders instead of ticket-keyed ones.
 *
 * Read access is the `sla_management.conversations.view` permission that got
 * the user to this page at all. Reply is its own permission; a reply is stamped
 * onto the sender's own open enquiry when they hold exactly one.
 */
export default function ConversationThreadPane({
  contact,
  canReply,
  onBack,
  className,
}: ConversationThreadPaneProps) {
  const contactRef = contact?.contact_ref ?? null;
  const [mode, setMode] = useState<'reply' | 'note'>('reply');
  const [replyTo, setReplyTo] = useState<
    { messageId: string | number | null; excerpt: string } | null
  >(null);

  const queryClient = useQueryClient();

  // ---- AC-K1 / AC-K2: live thread. One stream, only for the contact this pane
  // has OPEN, closed when the selection changes or the pane unmounts. Every
  // poke is content-free, so it turns into a refetch and nothing else.
  const onLiveEvent = useCallback(() => {
    if (!contactRef) return;
    // Every type this pane can receive means the same two things here: the
    // thread may have a new message (a NOTE is poked as `message` too) and the
    // row's snippet / ticket counts in the list may have moved.
    void queryClient.invalidateQueries({ queryKey: contactThreadKey(contactRef) });
    void queryClient.invalidateQueries({ queryKey: contactCommentsKey(contactRef) });
    void queryClient.invalidateQueries({ queryKey: ['conversations-inbox'] });
  }, [contactRef, queryClient]);
  const { connected: liveConnected } = useConversationEvents({
    contactIds: [contact?.respond_io_id],
    enabled: !!contactRef,
    onEvent: onLiveEvent,
    onReady: onLiveEvent,
  });

  const threadQuery = useContactThread(contactRef, {
    refetchIntervalMs: liveConnected ? THREAD_POLL_LIVE_MS : THREAD_POLL_MS,
  });
  const commentsQuery = useContactComments(contactRef);
  const { loadPage, searchMessages } = useContactThreadLoaders(contactRef);
  const mediaProxy = useContactMediaProxy(contactRef);
  const replyMutation = useReplyToContact(contactRef);
  const templateMutation = useSendContactTemplate(contactRef);
  // AC-N3 gap closure: the window and the out-of-window template are contact-
  // keyed now, so the composer smart-sends here exactly as the drawer does
  // instead of assuming an open window.
  const windowQuery = useContactWindow(contactRef);

  // A note is CONTACT-scoped: it needs no ticket, so the mode is offered
  // unconditionally to anyone who can read the conversation. The ticket-keyed
  // create is the drawer's; this one lands with `tracking_id` null and renders
  // in both places.
  const commentMutation = useCreateContactComment(contactRef);
  // Snippet `$variables` still resolve against a ticket, so they only have a
  // subject when the viewer holds exactly one open enquiry for this contact.
  const snippetTicketId = contact?.my_open_ticket_id ?? null;

  const thread = useConversationThread({
    liveItems: threadQuery.data?.items ?? [],
    loadPage,
    searchMessages,
    enabled: !!contactRef,
    resetKey: contactRef,
  });

  // A different contact is a different conversation: never carry the composer
  // mode across, and never carry a quote into someone else's thread.
  useEffect(() => {
    setMode('reply');
    setReplyTo(null);
  }, [contactRef]);

  if (!contact) {
    return (
      <div
        data-testid="thread-pane-empty"
        className={cn(
          'flex min-h-[40vh] flex-1 flex-col items-center justify-center gap-2 rounded-md border border-dashed p-6 text-center',
          className,
        )}
      >
        <MessagesSquare className="size-8 text-muted-foreground/50" />
        <p className="text-sm font-medium">Select a conversation</p>
        <p className="text-xs text-muted-foreground">
          Pick a contact on the left to read the thread.
        </p>
      </div>
    );
  }

  return (
    <div className={cn('flex min-h-0 flex-1 flex-col gap-3', className)}>
      {onBack && (
        <Button
          variant="ghost"
          size="sm"
          className="self-start lg:hidden"
          data-testid="thread-back"
          onClick={onBack}
        >
          <ArrowLeft className="size-4" />
          All conversations
        </Button>
      )}

      {threadQuery.isLoading ? (
        <div className="space-y-2" data-testid="thread-loading">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : threadQuery.isError ? (
        <div
          data-testid="thread-error"
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
            contactName={contact.name}
            contactPhone={contact.phone}
            emptyHint="No messages in this conversation yet."
            maxHeightClass="max-h-[52vh]"
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
            // Respond has no reply-to parameter, so the quote is emulated as a
            // ">" prefix the composer builds - same as the drawer.
            onReply={
              canReply
                ? (item) =>
                    setReplyTo({
                      messageId: item.messageId ?? null,
                      excerpt: excerptOfMessage(item),
                    })
                : undefined
            }
          />
        </>
      )}

      {/* ---- Mode switch: message the contact, or note to the team ---- */}
      <div
        role="tablist"
        aria-label="Composer mode"
        className="flex w-full gap-1 rounded-md border bg-muted/40 p-1"
      >
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'reply'}
          data-testid="inbox-composer-mode-reply"
          onClick={() => setMode('reply')}
          className={cn(
            'flex-1 rounded px-3 py-1.5 text-sm font-medium transition-colors',
            mode === 'reply'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          Reply
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'note'}
          data-testid="inbox-composer-mode-note"
          onClick={() => setMode('note')}
          className={cn(
            'flex-1 rounded px-3 py-1.5 text-sm font-medium transition-colors',
            mode === 'note'
              ? 'bg-amber-500 text-white shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          Note
        </button>
      </div>

      {mode === 'note' && (
        <InternalCommentComposer
          onSubmit={({ body, mentionedUserIds }) =>
            commentMutation.mutateAsync({ body, mentioned_user_ids: mentionedUserIds })
          }
        />
      )}

      {mode === 'reply' && (
        <SharedConversationComposer
          // No entity owns an inbox reply - it is keyed by the contact, so the
          // window, the template preview and both sends all come through the
          // overrides below rather than through the entity chat routes.
          entityType="conversation_contact"
          entityId={contactRef ?? ''}
          canReply={canReply}
          mode="conversation"
          attachmentsEnabled
          // The window is a live Respond read, so until it lands the composer
          // assumes OPEN: showing the template form to someone who is in fact
          // in-window would make them fill a template for nothing.
          windowStateOverride={{
            closed: windowQuery.data ? !windowQuery.data.window.open : false,
            template: windowQuery.data?.chat_template ?? null,
          }}
          templateSendAdapter={(input) => templateMutation.mutateAsync(input)}
          snippetsEnabled
          snippetTrackingId={snippetTicketId}
          emojiEnabled
          replyTo={replyTo}
          onClearReplyTo={() => setReplyTo(null)}
          sendAdapter={async (payload) => {
            const result = await replyMutation.mutateAsync({
              text: payload.text,
              files: payload.files,
              reply_to_message_id:
                payload.replyToMessageId != null ? String(payload.replyToMessageId) : null,
              reply_to_excerpt: payload.replyToExcerpt ?? null,
            });
            // AC-N2: a stamped send answered one of the sender's own enquiries
            // and stopped its clock. Said quietly - an unstamped send still
            // reached the contact, so it is information, not a failure.
            if (result.stamped_ticket_id) {
              toast.success('Sent - counted as the reply to your open enquiry.');
            } else {
              toast.success('Sent.');
            }
            return result;
          }}
          notAvailableMessage="You do not have permission to reply to contacts."
        />
      )}
    </div>
  );
}
