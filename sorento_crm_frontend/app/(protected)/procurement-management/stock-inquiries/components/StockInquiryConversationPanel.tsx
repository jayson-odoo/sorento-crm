'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useStockInquiryConversation } from '../hooks/useStockInquiries';
import RespondChatList from '@/components/common/RespondChatList';
import SharedConversationComposer from '@/components/common/conversation/SharedConversationComposer';
import { invalidateConversationWindow } from '@/components/common/conversation/useConversationWindowState';

interface StockInquiryConversationPanelProps {
  inquiryId: string;
  canReply: boolean;
  /** When set, show "Open in Respond" and use as popup-style header (e.g. in Sheet). */
  respondInboxUrl?: string | null;
  /** When true, render compact header with title + Open in Respond + Sync (for use in Sheet). */
  showAsPopup?: boolean;
  /** Purchasing team response text; "Use purchasing response" button fills the reply with this. */
  purchasingResponse?: string | null;
  /** Called when "Attach view link" is clicked; return value is appended to the reply. */
  onGetViewLink?: () => Promise<string>;
  /**
   * When `key` changes, replaces the compose field with `text` (e.g. after "Update & Reply" opens chat).
   * Parent should clear when the sheet closes so "Chat records" alone does not reuse stale drafts.
   */
  replyComposePrefill?: { key: number; text: string } | null;
  /** Contact display in WhatsApp-style header. */
  contactName?: string | null;
  contactPhone?: string | null;
}

export default function StockInquiryConversationPanel({
  inquiryId,
  canReply,
  respondInboxUrl,
  showAsPopup = false,
  purchasingResponse,
  onGetViewLink,
  replyComposePrefill,
  contactName,
  contactPhone,
}: StockInquiryConversationPanelProps) {
  const { data, isLoading, refetch, isRefetching } = useStockInquiryConversation(inquiryId, { limit: 50 });
  const queryClient = useQueryClient();

  const items = data?.items ?? [];

  const handleRefresh = () => {
    void refetch();
    invalidateConversationWindow(queryClient, 'stock_inquiry', inquiryId);
  };

  const refetchSoon = () => {
    void refetch();
    window.setTimeout(() => {
      void refetch();
    }, 1600);
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
          entityType="stock_inquiry"
          entityId={inquiryId}
          canReply={canReply}
          mode="entity"
          useResponseText={purchasingResponse}
          useResponseLabel="Use purchasing response"
          onGetViewLink={onGetViewLink}
          replyComposePrefill={replyComposePrefill}
          onSent={refetchSoon}
          notAvailableMessage="Reply is only available when the inquiry is pending purchasing review or responded."
        />
      </CardContent>
    </Card>
  );
}
