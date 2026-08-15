'use client';

import { useQueryClient } from '@tanstack/react-query';
import { AlertCircle, ExternalLink, RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import RespondChatList from '@/components/common/RespondChatList';
import SharedConversationComposer from '@/components/common/conversation/SharedConversationComposer';
import { useConversationThread } from '@/components/common/conversation/useConversationThread';
import { invalidateConversationWindow } from '@/components/common/conversation/useConversationWindowState';

import {
  useSlaTrackingConversation,
  useSlaTrackingMediaProxy,
  useSlaTrackingThreadLoaders,
} from '../hooks/useConversationSLATracking';
import { useTicketComments } from '../hooks/useTicketComments';

interface SlaTrackingChatRecordsProps {
  trackingId: string;
  respondInboxUrl?: string | null;
  /** Rendered inside the detail page's sheet: no card chrome, taller thread. */
  showAsPopup?: boolean;
}

/**
 * "Chat Records" on the SLA tracking detail page (UAC AC-N8).
 *
 * This used to be a hand-rolled bubble list that had drifted a long way from
 * the ticket drawer's: no scroll-back, no in-thread search, no attachment
 * preview, no internal notes, no quoted context. It now renders the SAME
 * shared thread the drawer does - one `RespondChatList` driven by
 * `useConversationThread` with the ticket-keyed loaders - so those capabilities
 * cannot diverge again.
 */
export default function SlaTrackingChatRecords({
  trackingId,
  respondInboxUrl,
  showAsPopup = false,
}: SlaTrackingChatRecordsProps) {
  // A Respond contact is linked when we have an inbox URL for the conversation.
  const canReply = Boolean(respondInboxUrl);
  const queryClient = useQueryClient();

  const threadQuery = useSlaTrackingConversation(trackingId, { limit: 50 });
  const commentsQuery = useTicketComments(trackingId);
  const { loadPage, searchMessages } = useSlaTrackingThreadLoaders(trackingId);
  const mediaProxy = useSlaTrackingMediaProxy(trackingId);

  const thread = useConversationThread({
    liveItems: threadQuery.data?.items ?? [],
    loadPage,
    searchMessages,
    enabled: !!trackingId,
    resetKey: trackingId,
  });

  const handleRefresh = () => {
    void threadQuery.refetch();
    // Re-checking messages must re-evaluate the 24h window too: an incoming
    // reply re-opens it, which flips the composer out of template mode.
    invalidateConversationWindow(queryClient, 'conversation_sla', trackingId);
  };

  const header = (
    <div className="flex items-center justify-between gap-2">
      <CardTitle className="text-base">
        {showAsPopup ? 'Chat Records' : 'Conversation (Respond.io)'}
      </CardTitle>
      {showAsPopup && (
        <div className="flex items-center gap-1">
          {respondInboxUrl && (
            <Button
              variant="ghost"
              size="icon"
              className="shrink-0"
              onClick={() => window.open(respondInboxUrl, '_blank', 'noopener,noreferrer')}
              aria-label="Open conversation in Respond"
            >
              <ExternalLink className="size-4" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0"
            disabled={threadQuery.isRefetching}
            onClick={handleRefresh}
            aria-label="Refresh messages"
          >
            <RefreshCw
              className={`size-4 ${threadQuery.isRefetching ? 'animate-spin' : ''}`}
            />
          </Button>
        </div>
      )}
    </div>
  );

  return (
    <Card className={showAsPopup ? 'border-0 shadow-none' : ''}>
      <CardHeader className={showAsPopup ? 'pb-2' : ''}>{header}</CardHeader>
      <CardContent className="space-y-4">
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
              <p className="text-sm text-muted-foreground">{threadQuery.data.error}</p>
            )}
            {thread.error && <p className="text-xs text-destructive">{thread.error}</p>}
            <RespondChatList
              items={thread.items}
              emptyHint="No messages yet."
              maxHeightClass={showAsPopup ? 'max-h-[55vh]' : 'max-h-[400px]'}
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

        <SharedConversationComposer
          entityType="conversation_sla"
          entityId={trackingId}
          canReply={canReply}
          mode="conversation"
          onSent={() => {
            void threadQuery.refetch();
            // Respond acknowledges before the message is readable back: one
            // late re-read catches it without a poll on a page nobody is
            // watching.
            window.setTimeout(() => {
              void threadQuery.refetch();
            }, 1600);
          }}
          notAvailableMessage="No Respond conversation link available for this contact."
        />
      </CardContent>
    </Card>
  );
}
