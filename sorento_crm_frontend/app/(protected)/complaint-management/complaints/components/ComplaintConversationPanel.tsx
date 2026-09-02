'use client';

import { useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useComplaintConversation } from '../hooks/useComplaints';
import RespondChatList from '@/components/common/RespondChatList';
import SharedConversationComposer from '@/components/common/conversation/SharedConversationComposer';
import { invalidateConversationWindow } from '@/components/common/conversation/useConversationWindowState';
import { usePendingThreadItems } from '@/components/common/conversation/usePendingThreadItems';

interface ComplaintConversationPanelProps {
  complaintId: string;
  canReply: boolean;
  /** When set, show "Open in Respond" and use as popup-style header (e.g. in Sheet). */
  respondInboxUrl?: string | null;
  /** When true, render compact header with title + Open in Respond + Sync (for use in Sheet). */
  showAsPopup?: boolean;
  /** Technical team response text; "Use technical response" fills the reply with this. */
  technicalTeamResponse?: string | null;
  /** Called when "Attach view link" is clicked; return value is appended to the reply. */
  onGetViewLink?: () => Promise<string>;
  /**
   * When `key` changes, replaces the compose field with `text` (e.g. after "Update & Reply" opens chat).
   */
  replyComposePrefill?: { key: number; text: string } | null;
  /** Contact display in WhatsApp-style header. */
  contactName?: string | null;
  contactPhone?: string | null;
}

export default function ComplaintConversationPanel({
  complaintId,
  canReply,
  respondInboxUrl,
  showAsPopup = false,
  technicalTeamResponse,
  onGetViewLink,
  replyComposePrefill,
  contactName,
  contactPhone,
}: ComplaintConversationPanelProps) {
  const { data, isLoading, refetch, isRefetching } = useComplaintConversation(complaintId, { limit: 50 });
  const queryClient = useQueryClient();
  const pending = usePendingThreadItems();

  // A different complaint is a different draft: never leave a stranger's
  // in-flight send dimmed in a thread that just mounted under a new id.
  useEffect(() => {
    pending.clearPending();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [complaintId]);

  const items = [...(data?.items ?? []), ...pending.pendingItems];

  // Refresh control: re-pull messages AND re-evaluate the 24h window (an incoming
  // reply re-opens it → composer flips template mode → plain textbox).
  const handleRefresh = () => {
    void refetch();
    invalidateConversationWindow(queryClient, 'complaint', complaintId);
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
          entityType="complaint"
          entityId={complaintId}
          canReply={canReply}
          mode="entity"
          useResponseText={technicalTeamResponse}
          useResponseLabel="Use technical response"
          onGetViewLink={onGetViewLink}
          replyComposePrefill={replyComposePrefill}
          onSent={refetchSoon}
          pendingBubble={{ add: pending.addPending, remove: pending.removePending }}
        />
      </CardContent>
    </Card>
  );
}
