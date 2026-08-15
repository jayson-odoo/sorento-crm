'use client';

import { useEffect, useState } from 'react';
import { AlertCircle, ArrowLeft, MessagesSquare } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import RespondChatList from '@/components/common/RespondChatList';
import InternalCommentComposer from '@/components/common/conversation/InternalCommentComposer';
import SharedConversationComposer from '@/components/common/conversation/SharedConversationComposer';
import { useConversationThread } from '@/components/common/conversation/useConversationThread';
import { useCreateTicketComment } from '@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTicketComments';
import { cn } from '@/lib/utils';

import {
  contactCommentsKey,
  useContactComments,
  useContactMediaProxy,
  useContactThread,
  useContactThreadLoaders,
  useReplyToContact,
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

  const threadQuery = useContactThread(contactRef);
  const commentsQuery = useContactComments(contactRef);
  const { loadPage, searchMessages } = useContactThreadLoaders(contactRef);
  const mediaProxy = useContactMediaProxy(contactRef);
  const replyMutation = useReplyToContact(contactRef);
  const queryClient = useQueryClient();

  // A note is written against a TICKET: there is no contact-keyed note create
  // (recorded as a backend follow-up in the plan's S4.9 note). So the mode is
  // only offered when this viewer holds exactly one open enquiry for the
  // contact, which is also the only case where "which ticket owns it" has an
  // unambiguous answer.
  const noteTicketId = contact?.my_open_ticket_id ?? null;
  const commentMutation = useCreateTicketComment(noteTicketId ?? '');

  const thread = useConversationThread({
    liveItems: threadQuery.data?.items ?? [],
    loadPage,
    searchMessages,
    enabled: !!contactRef,
    resetKey: contactRef,
  });

  // A different contact is a different conversation: never carry the composer
  // mode across, and never leave Note selected for someone it is unavailable for.
  useEffect(() => {
    setMode('reply');
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

  const noteAvailable = !!noteTicketId;

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
          disabled={!noteAvailable}
          title={
            noteAvailable
              ? undefined
              : 'Notes attach to one of your own open enquiries for this contact.'
          }
          onClick={() => setMode('note')}
          className={cn(
            'flex-1 rounded px-3 py-1.5 text-sm font-medium transition-colors',
            mode === 'note'
              ? 'bg-amber-500 text-white shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
            !noteAvailable && 'cursor-not-allowed opacity-50 hover:text-muted-foreground',
          )}
        >
          Note
        </button>
      </div>

      {mode === 'note' && noteAvailable && (
        <InternalCommentComposer
          onSubmit={async ({ body, mentionedUserIds }) => {
            const created = await commentMutation.mutateAsync({
              body,
              mentioned_user_ids: mentionedUserIds,
            });
            // The note list here is contact-keyed, so the ticket-keyed mutation's
            // own invalidation does not reach it.
            void queryClient.invalidateQueries({ queryKey: contactCommentsKey(contactRef) });
            return created;
          }}
        />
      )}

      {mode === 'reply' && (
        <SharedConversationComposer
          // No entity owns an inbox reply - it is keyed by the contact. The
          // ids are only ever used for the window/template queries, which the
          // override below turns off (there is no contact-keyed window read;
          // the backend still smart-sends a template out of window).
          entityType="conversation_contact"
          entityId={contactRef ?? ''}
          canReply={canReply}
          mode="conversation"
          attachmentsEnabled
          showTemplateButton={false}
          windowStateOverride={{ closed: false }}
          snippetsEnabled
          snippetTrackingId={noteTicketId}
          emojiEnabled
          sendAdapter={async (payload) => {
            const result = await replyMutation.mutateAsync({
              text: payload.text,
              files: payload.files,
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
