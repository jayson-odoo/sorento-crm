'use client';

import { useState, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { Send, ExternalLink, RefreshCw, Link2, LayoutTemplate } from 'lucide-react';
import { usePurchaseRequestConversation, useUpdatePurchaseRequestAndReply } from '../hooks/usePurchaseRequests';
import RespondChatList from '@/components/common/RespondChatList';
import SendTemplateDialog from '@/components/common/whatsapp-template/SendTemplateDialog';
import WindowStateNotice from '@/components/common/whatsapp-template/WindowStateNotice';
import { getWindowState } from '@/services/whatsappTemplateService';

interface PurchaseRequestConversationPanelProps {
  requestId: string;
  canReply?: boolean;
  respondInboxUrl?: string | null;
  showAsPopup?: boolean;
  /** Sent with update-and-reply when set (keeps form number in sync on Respond message). */
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
  requestNumber,
  replyComposePrefill,
  onGetViewLink,
  contactName,
  contactPhone,
}: PurchaseRequestConversationPanelProps) {
  const [replyText, setReplyText] = useState('');
  const [viewLinkLoading, setViewLinkLoading] = useState(false);
  const [templateDialogOpen, setTemplateDialogOpen] = useState(false);
  const replyTextareaRef = useRef<HTMLTextAreaElement>(null);
  const appliedPrefillKeyRef = useRef(0);
  const { data, isLoading, refetch, isRefetching } = usePurchaseRequestConversation(requestId, { limit: 50 });
  const updateAndReplyMutation = useUpdatePurchaseRequestAndReply();

  const items = data?.items ?? [];

  // 24h WhatsApp window state — plain sends are silently dropped when closed.
  const { data: windowState } = useQuery({
    queryKey: ['whatsapp-window-state', 'purchase_request', requestId],
    queryFn: () => getWindowState('purchase_request', requestId),
    enabled: canReply,
    staleTime: 60_000,
  });
  const windowClosed = windowState ? !windowState.open : false;

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
      const rn = requestNumber != null && String(requestNumber).trim() !== '' ? requestNumber : undefined;
      await updateAndReplyMutation.mutateAsync({
        id: requestId,
        data: {
          reply_message: text,
          ...(rn !== undefined ? { request_number: rn } : {}),
        },
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
          <RespondChatList
            items={items}
            contactName={data?.contact?.name ?? contactName}
            contactPhone={data?.contact?.phone ?? contactPhone}
            maxHeightClass={showAsPopup ? 'max-h-[60vh]' : 'max-h-[400px]'}
          />
        )}

        {canReply && (
          <div className="space-y-2">
            {windowState && <WindowStateNotice windowState={windowState} />}
            <div className="flex gap-2">
              <Textarea
                ref={replyTextareaRef}
                placeholder={
                  windowClosed
                    ? '24h window closed — send a template instead'
                    : 'Type your response...'
                }
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (!windowClosed) handleSend();
                  }
                }}
                rows={3}
                disabled={windowClosed}
                className="resize-none flex-1 min-w-0"
              />
              <Button
                size="icon"
                className="shrink-0"
                disabled={!replyText.trim() || updateAndReplyMutation.isPending || windowClosed}
                onClick={handleSend}
                aria-label="Send"
              >
                <Send className="size-4" />
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant={windowClosed ? 'primary' : 'outline'}
                size="sm"
                onClick={() => setTemplateDialogOpen(true)}
              >
                <LayoutTemplate className="size-4 mr-1" />
                Send template
              </Button>
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
        )}
      </CardContent>

      <SendTemplateDialog
        entityType="purchase_request"
        entityId={requestId}
        contactId={requestId}
        open={templateDialogOpen}
        onOpenChange={setTemplateDialogOpen}
        onSent={() => {
          void refetch();
          window.setTimeout(() => {
            void refetch();
          }, 1600);
        }}
      />
    </Card>
  );
}
