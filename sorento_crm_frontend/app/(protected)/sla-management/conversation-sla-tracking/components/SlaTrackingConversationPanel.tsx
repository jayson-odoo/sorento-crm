'use client';

import { useRef, useEffect, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ExternalLink, RefreshCw } from 'lucide-react';
import type { RespondMessageItem } from '@/app/(protected)/procurement-management/stock-inquiries/services/stockInquiryService';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { getRespondMessageDisplayTimeMs, getRespondMessageSortTimeMs } from '@/lib/respondIoMessage';
import {
  getNormalizedRespondSource,
  getOutgoingBubbleClass,
  getOutgoingSenderLabel,
} from '@/lib/respondIoOutgoingMessage';
import { useSlaTrackingConversation } from '../hooks/useConversationSLATracking';

interface SlaTrackingConversationPanelProps {
  trackingId: string;
  respondInboxUrl?: string | null;
  showAsPopup?: boolean;
}

export default function SlaTrackingConversationPanel({
  trackingId,
  respondInboxUrl,
  showAsPopup = false,
}: SlaTrackingConversationPanelProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { data, isLoading, refetch, isRefetching } = useSlaTrackingConversation(trackingId, {
    limit: 50,
  });

  const items: RespondMessageItem[] = data?.items ?? [];
  const sortedItems = useMemo(() => {
    return [...items].sort((a, b) => {
      const ta = getRespondMessageSortTimeMs(a);
      const tb = getRespondMessageSortTimeMs(b);
      if (ta !== tb) return ta - tb;
      return (a.messageId ?? 0) - (b.messageId ?? 0);
    });
  }, [items]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [sortedItems.length]);

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
            onClick={() => refetch()}
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
      <CardHeader className={showAsPopup ? 'pb-2' : ''}>{header}</CardHeader>
      <CardContent className="space-y-4">
        {data?.error && <p className="text-sm text-muted-foreground">{data.error}</p>}
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : (
          <div
            className={`flex flex-col gap-3 overflow-y-auto rounded-md border bg-muted/30 p-3 ${showAsPopup ? 'max-h-[60vh]' : 'max-h-[400px]'}`}
          >
            {items.length === 0 && !data?.error && (
              <p className="text-sm text-muted-foreground py-4 text-center">No messages yet.</p>
            )}
            {sortedItems.map((item, idx) => {
              const isOutgoing = item.traffic === 'outgoing';
              const text = item.message?.text ?? '';
              const displayMs = getRespondMessageDisplayTimeMs(item);
              const dateStr =
                displayMs > 0 && !Number.isNaN(displayMs)
                  ? formatDateTimeInMalaysia(displayMs)
                  : '';
              const sourceNorm = getNormalizedRespondSource(item);
              const senderLabel = isOutgoing ? getOutgoingSenderLabel(sourceNorm) : 'Contact';
              const bubbleClass = isOutgoing
                ? getOutgoingBubbleClass(sourceNorm)
                : 'bg-muted';
              return (
                <div
                  key={item.messageId != null ? String(item.messageId) : `msg-${idx}`}
                  className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}
                >
                  <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${bubbleClass}`}>
                    <div className="text-xs font-medium opacity-90 mb-0.5">{senderLabel}</div>
                    <div className="whitespace-pre-wrap break-words">{text || '(no text)'}</div>
                    {dateStr && (
                      <div
                        className={`text-xs mt-1 ${isOutgoing ? 'opacity-80' : 'text-muted-foreground'}`}
                      >
                        {dateStr}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>
        )}

        <div className="rounded-md border border-dashed bg-muted/30 p-3">
          <p className="text-sm text-muted-foreground">
            Replies — including files and images — are sent from Respond. Open the conversation
            there to respond to the customer.
          </p>
          {respondInboxUrl ? (
            <Button
              className="mt-2"
              size="sm"
              onClick={() => window.open(respondInboxUrl, '_blank', 'noopener,noreferrer')}
            >
              <ExternalLink className="size-4" />
              Open in Respond
            </Button>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">
              No Respond conversation link available for this contact.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
