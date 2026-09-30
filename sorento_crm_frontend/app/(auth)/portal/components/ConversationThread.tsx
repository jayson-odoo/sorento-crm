'use client';

import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import RespondChatList from '@/components/common/RespondChatList';
import { useConversationThread } from '@/components/common/conversation/useConversationThread';
import { cn } from '@/lib/utils';

import {
  getConversationComments,
  getConversationPage,
  searchConversation,
  type PortalConversation,
} from '../lib/conversations-service';

/** How often the open thread re-reads its newest window (the ticket drawer's own interval). */
const THREAD_POLL_MS = 10_000;

export const portalThreadKey = (contactId: string | null) =>
  ['portal-conversation-thread', contactId] as const;
export const portalCommentsKey = (contactId: string | null) =>
  ['portal-conversation-comments', contactId] as const;

/**
 * The opened conversation (AC-CV12 to AC-CV15): the SAME shared thread the ticket drawer and
 * the CRM inbox render, driven by portal-token loaders. Read-only by owner ruling (30 Sep, Q1):
 * no composer, no note, no reply action on a bubble.
 */
export function ConversationThread({
  contact,
  enabled = true,
  maxHeightClass = 'max-h-[60dvh]',
  className,
}: {
  contact: PortalConversation;
  enabled?: boolean;
  maxHeightClass?: string;
  className?: string;
}) {
  const contactId = enabled ? contact.contact_id : null;

  const threadQuery = useQuery({
    queryKey: portalThreadKey(contactId),
    queryFn: () => getConversationPage(contactId as string, { limit: 50 }),
    enabled: !!contactId,
    staleTime: 30_000,
    refetchInterval: THREAD_POLL_MS,
    refetchIntervalInBackground: false,
    retry: 1,
  });
  const commentsQuery = useQuery({
    queryKey: portalCommentsKey(contactId),
    queryFn: () => getConversationComments(contactId as string),
    enabled: !!contactId,
    retry: 1,
  });

  const loadPage = useCallback(
    (params: {
      before?: string;
      after?: string;
      around?: string;
      limit?: number;
    }) => getConversationPage(contactId ?? '', params),
    [contactId],
  );
  const searchMessages = useCallback(
    (query: string) => searchConversation(contactId ?? '', query),
    [contactId],
  );

  const thread = useConversationThread({
    liveItems: threadQuery.data?.items ?? [],
    loadPage,
    searchMessages,
    enabled: !!contactId,
    resetKey: contactId,
  });

  return (
    <div
      data-testid="portal-conversation-thread"
      className={cn('flex min-h-0 flex-1 flex-col gap-2', className)}
    >
      {threadQuery.isLoading ? (
        <div className="space-y-2" data-testid="portal-thread-loading">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : threadQuery.isError ? (
        <div
          data-testid="portal-thread-error"
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
            <p className="text-xs text-muted-foreground">
              {threadQuery.data.error}
            </p>
          )}
          {thread.error && (
            <p className="text-xs text-destructive">{thread.error}</p>
          )}
          <RespondChatList
            items={thread.items}
            contactName={
              contact.customer_name && contact.contact_name
                ? `${contact.customer_name} · ${contact.contact_name}`
                : contact.customer_name || contact.contact_name
            }
            contactPhone={contact.contact_phone}
            emptyHint="No messages in this conversation yet."
            maxHeightClass={maxHeightClass}
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
            onJumpToMessage={thread.jumpToMessage}
            // No `onReply`: read-only (Q1). Copy on a bubble stays.
          />
        </>
      )}
    </div>
  );
}
