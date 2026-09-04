'use client';

import { useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { usePurchaseRequestConversation } from '../hooks/usePurchaseRequests';
import RespondChatList from '@/components/common/RespondChatList';
import SharedConversationComposer from '@/components/common/conversation/SharedConversationComposer';
import { invalidateConversationWindow } from '@/components/common/conversation/useConversationWindowState';
import { usePendingThreadItems } from '@/components/common/conversation/usePendingThreadItems';

interface PurchaseRequestConversationPanelProps {
  requestId: string;
  canReply?: boolean;
  respondInboxUrl?: string | null;
  showAsPopup?: boolean;
  /** Retained for caller compatibility; the pure chat send resolves the form number server-side. */
  requestNumber?: string | null;
  /**
   * When `key` changes, replaces the compose field with `text` (e.g. after "Update & Reply" opens chat).
   * Parent should clear when the sheet closes so "Chat records" alone does not reuse stale drafts.
   */
  replyComposePrefill?: { key: number; text: string } | null;
  /** Called when "Attach view link" is clicked; return value is appended to the reply. */
  onGetViewLink?: () => Promise<string>;
  /** Contact display in WhatsApp-style header. */
  contactName?: string | null;
  contactPhone?: string | null;
}

export default function PurchaseRequestConversationPanel({
  requestId,
  canReply = true,
  respondInboxUrl,
  showAsPopup = false,
  replyComposePrefill,
  onGetViewLink,
  contactName,
  contactPhone,
}: PurchaseRequestConversationPanelProps) {
  const { data, isLoading, refetch, isRefetching } = usePurchaseRequestConversation(requestId, { limit: 50 });
  const queryClient = useQueryClient();
  const pending = usePendingThreadItems();
  const { clearPending } = pending;

  // A different request is a different draft: never leave a stranger's
  // in-flight send dimmed in a thread that just mounted under a new id.
  // `clearPending` is `useCallback`-stable (empty deps in the hook), so
  // listing it here does not re-run this on every render.
  useEffect(() => {
    clearPending();
  }, [requestId, clearPending]);

  const items = [...(data?.items ?? []), ...pending.pendingItems];

  const handleRefresh = () => {
    void refetch();
    invalidateConversationWindow(queryClient, 'purchase_request', requestId);
  };

  // Returned so the composer's optimistic bubble (M6-01) waits for THIS
  // refetch before it comes down; the 1.6s pulse only chases delivery ticks.
  const refetchSoon = () => {
    const refetched = refetch();
    window.setTimeout(() => {
      void refetch();
    }, 1600);
    return refetched;
  };

  const headerTitle = showAsPopup ? 'Chat Records' : 'Conversation (Respond.io)';
  const showHeaderActions = showAsPopup;

  const header = (
    <div className="flex items-center justify-between gap-2">
      <CardTitle className="text-base">{headerTitle}</CardTitle>
      {showHeaderActions && (
        <div className="flex items-center gap-1">
          {respondInboxUrl && (
            <Button
              variant="ghost"
              size="icon"
              className="shrink-0"
              onClick={() => window.open(respondInboxUrl, '_blank')}
              aria-label="Open conversation in Respond"
            >
              <ExternalLink className="size-4" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0"
            disabled={isRefetching}
            onClick={handleRefresh}
            aria-label="Refresh messages"
          >
            <RefreshCw className={`size-4 ${isRefetching ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      )}
    </div>
  );

  return (
    <Card className={showAsPopup ? 'border-0 shadow-none' : ''}>
      <CardHeader className={showAsPopup ? 'pb-2' : ''}>
        {header}
      </CardHeader>
      <CardContent className="space-y-4">
        {data?.error && (
          <p className="text-sm text-muted-foreground">{data.error}</p>
        )}
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : (
          <RespondChatList
            items={items}
            contactName={data?.contact?.name ?? contactName}
            contactPhone={data?.contact?.phone ?? contactPhone}
            maxHeightClass={showAsPopup ? 'max-h-[60vh]' : 'max-h-[400px]'}
          />
        )}

        <SharedConversationComposer
          entityType="purchase_request"
          entityId={requestId}
          canReply={canReply}
          mode="entity"
          onGetViewLink={onGetViewLink}
          replyComposePrefill={replyComposePrefill}
          onSent={refetchSoon}
          pendingBubble={{ add: pending.addPending, remove: pending.removePending }}
        />
      </CardContent>
    </Card>
  );
}
