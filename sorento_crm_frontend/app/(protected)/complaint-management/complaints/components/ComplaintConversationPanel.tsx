'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { Send, ExternalLink, RefreshCw, FileText, Link2 } from 'lucide-react';
import { useComplaintConversation, useUpdateComplaintAndReply } from '../hooks/useComplaints';
import type { RespondMessageItem } from '../services/complaintService';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { getRespondMessageDisplayTimeMs, getRespondMessageSortTimeMs } from '@/lib/respondIoMessage';
import {
  getNormalizedRespondSource,
  getOutgoingBubbleClass,
  getOutgoingSenderLabel,
} from '@/lib/respondIoOutgoingMessage';

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
}

export default function ComplaintConversationPanel({
  complaintId,
  canReply,
  respondInboxUrl,
  showAsPopup = false,
  technicalTeamResponse,
  onGetViewLink,
  replyComposePrefill,
}: ComplaintConversationPanelProps) {
  const [replyText, setReplyText] = useState('');
  const [viewLinkLoading, setViewLinkLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const replyTextareaRef = useRef<HTMLTextAreaElement>(null);
  const appliedPrefillKeyRef = useRef(0);
  const { data, isLoading, refetch, isRefetching } = useComplaintConversation(complaintId, { limit: 50 });
  const updateAndReplyMutation = useUpdateComplaintAndReply();

  const items: RespondMessageItem[] = useMemo(() => data?.items ?? [], [data?.items]);
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

  useEffect(() => {
    if (!replyComposePrefill) return;
    if (replyComposePrefill.key === appliedPrefillKeyRef.current) return;
    appliedPrefillKeyRef.current = replyComposePrefill.key;
    setReplyText(replyComposePrefill.text);
    queueMicrotask(() => replyTextareaRef.current?.focus());
  }, [replyComposePrefill]);

  const handleSend = async () => {
    const text = replyText.trim();
    if (!text || updateAndReplyMutation.isPending) return;
    try {
      await updateAndReplyMutation.mutateAsync({
        id: complaintId,
        data: { technical_team_response: text },
      });
      setReplyText('');
      await refetch();
      window.setTimeout(() => {
        void refetch();
      }, 1600);
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

        <div className="space-y-2">
          <div className="flex gap-2">
            <Textarea
              ref={replyTextareaRef}
              placeholder="Type your response..."
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  if (canReply) handleSend();
                }
              }}
              rows={3}
              className="resize-none flex-1 min-w-0"
            />
            <Button
              size="icon"
              className="shrink-0"
              disabled={!replyText.trim() || updateAndReplyMutation.isPending || !canReply}
              onClick={handleSend}
              aria-label="Send"
            >
              <Send className="size-4" />
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            {technicalTeamResponse != null && technicalTeamResponse !== '' && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setReplyText(technicalTeamResponse)}
              >
                <FileText className="size-4 mr-1" />
                Use technical response
              </Button>
            )}
            {onGetViewLink && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={viewLinkLoading}
                onClick={async () => {
                  setViewLinkLoading(true);
                  try {
                    const url = await onGetViewLink();
                    if (url) {
                      setReplyText((prev) => (prev.trim() ? `${prev.trim()}\n\n${url}` : url));
                    }
                  } finally {
                    setViewLinkLoading(false);
                  }
                }}
              >
                <Link2 className="size-4 mr-1" />
                {viewLinkLoading ? 'Getting link…' : 'Attach view link'}
              </Button>
            )}
          </div>
        </div>
        {!canReply && (
          <p className="text-xs text-muted-foreground">
            Reply is only available when a Respond.io conversation is linked to this complaint.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
