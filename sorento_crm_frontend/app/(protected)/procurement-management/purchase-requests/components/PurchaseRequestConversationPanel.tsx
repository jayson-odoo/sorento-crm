'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { Send, ExternalLink, RefreshCw } from 'lucide-react';
import { usePurchaseRequestConversation, useUpdatePurchaseRequestAndReply } from '../hooks/usePurchaseRequests';
import type { RespondMessageItem } from '../services/purchaseRequestService';
import { formatDateTimeInMalaysia, respondIoTimestampToDate } from '@/lib/helpers';

function getSenderLabel(item: RespondMessageItem): string {
  const source = (item.sender?.source ?? '').toLowerCase();
  if (source === 'workflow') return 'Workflow';
  if (source === 'ai_agent' || source === 'agent') return 'AI Agent';
  return 'User';
}

interface PurchaseRequestConversationPanelProps {
  requestId: string;
  canReply?: boolean;
  respondInboxUrl?: string | null;
  showAsPopup?: boolean;
}

function parseCursorFromNext(nextUrl: string | undefined): string | undefined {
  if (!nextUrl) return undefined;
  try {
    const u = new URL(nextUrl);
    return u.searchParams.get('cursorId') ?? undefined;
  } catch {
    return undefined;
  }
}

export default function PurchaseRequestConversationPanel({
  requestId,
  canReply = true,
  respondInboxUrl,
  showAsPopup = false,
}: PurchaseRequestConversationPanelProps) {
  const [replyText, setReplyText] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { data, isLoading, refetch, isRefetching } = usePurchaseRequestConversation(requestId, { limit: 50 });
  const updateAndReplyMutation = useUpdatePurchaseRequestAndReply();

  const items: RespondMessageItem[] = data?.items ?? [];
  const sortedItems = useMemo(() => {
    return [...items].sort((a, b) => {
      const ta = respondIoTimestampToDate(a.status?.[0]?.timestamp ?? 0).getTime();
      const tb = respondIoTimestampToDate(b.status?.[0]?.timestamp ?? 0).getTime();
      if (Number.isNaN(ta) && Number.isNaN(tb)) return 0;
      if (Number.isNaN(ta)) return 1;
      if (Number.isNaN(tb)) return -1;
      return ta - tb;
    });
  }, [items]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [sortedItems.length]);

  const handleSend = async () => {
    const text = replyText.trim();
    if (!text || updateAndReplyMutation.isPending) return;
    try {
      await updateAndReplyMutation.mutateAsync({
        id: requestId,
        data: { reply_message: text },
      });
      setReplyText('');
      refetch();
    } catch {
      // toast from mutation
    }
  };

  const headerTitle = showAsPopup ? 'Chat Records' : 'Conversation (Respond.io)';
  const showHeaderActions = showAsPopup && (respondInboxUrl || true);

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
          <div className={`flex flex-col gap-3 overflow-y-auto rounded-md border bg-muted/30 p-3 ${showAsPopup ? 'max-h-[60vh]' : 'max-h-[400px]'}`}>
            {items.length === 0 && !data?.error && (
              <p className="text-sm text-muted-foreground py-4 text-center">No messages yet.</p>
            )}
            {sortedItems.map((item, idx) => {
              const isOutgoing = item.traffic === 'outgoing';
              const text = item.message?.text ?? '';
              const ts = item.status?.[0]?.timestamp ?? 0;
              const tsDate = respondIoTimestampToDate(ts);
              const dateStr =
                ts && !Number.isNaN(tsDate.getTime())
                  ? formatDateTimeInMalaysia(tsDate)
                  : '';
              const senderLabel = isOutgoing ? getSenderLabel(item) : 'Contact';
              const source = (item.sender?.source ?? '').toLowerCase();
              const isWorkflow = source === 'workflow';
              const isAiAgent = source === 'ai_agent' || source === 'agent';
              const bubbleClass = isOutgoing
                ? isWorkflow
                  ? 'bg-violet-600 text-white'
                  : isAiAgent
                    ? 'bg-violet-500/90 text-white'
                    : 'bg-primary text-primary-foreground'
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
                      <div className={`text-xs mt-1 ${isOutgoing ? 'opacity-80' : 'text-muted-foreground'}`}>
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

        {canReply && (
          <div className="flex gap-2">
            <Textarea
              placeholder="Type your response..."
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              rows={2}
              className="resize-none"
            />
            <Button
              size="icon"
              className="shrink-0"
              disabled={!replyText.trim() || updateAndReplyMutation.isPending}
              onClick={handleSend}
              aria-label="Send"
            >
              <Send className="size-4" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
