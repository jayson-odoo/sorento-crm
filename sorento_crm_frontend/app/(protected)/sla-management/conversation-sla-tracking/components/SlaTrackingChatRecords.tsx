'use client';

import { useQueryClient } from '@tanstack/react-query';
import { ExternalLink, RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { invalidateConversationWindow } from '@/components/common/conversation/useConversationWindowState';

import { useSlaTrackingConversation } from '../hooks/useConversationSLATracking';
import TicketConversationPanel from './TicketConversationPanel';

interface SlaTrackingChatRecordsProps {
  trackingId: string;
  respondInboxUrl?: string | null;
  /** Rendered inside the detail page's sheet: no card chrome, taller thread. */
  showAsPopup?: boolean;
}

/**
 * "Chat Records" on the SLA tracking detail page (UAC AC-N8).
 *
 * This is the ticket drawer's chat panel, literally: `TicketConversationPanel`
 * is ONE component mounted by both surfaces. It used to be a second call site
 * passing its own (shorter) prop set, and the detail page silently lost
 * attachments, the "/" snippet picker, emoji, AI assist, the manual template
 * send, the real 24h-window state and the internal-note composer while looking
 * close enough to pass. This file is now only the card chrome around it:
 * a title, Open-in-Respond and Refresh.
 */
export default function SlaTrackingChatRecords({
  trackingId,
  respondInboxUrl,
  showAsPopup = false,
}: SlaTrackingChatRecordsProps) {
  const queryClient = useQueryClient();
  // Held here only for the header's Refresh: the panel owns the reading.
  const threadQuery = useSlaTrackingConversation(trackingId, { limit: 50 });

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
      <CardContent>
        <TicketConversationPanel
          ticketId={trackingId}
          maxHeightClass={showAsPopup ? 'max-h-[55vh]' : 'max-h-[400px]'}
          // No ticket detail (a form-scope tracker, or a viewer outside the
          // ticket's act-scope): a linked Respond conversation is still enough
          // to reply through the shared entity chat send, as it always was.
          fallbackCanReply={Boolean(respondInboxUrl)}
          fallbackNotAvailableMessage="No Respond conversation link available for this contact."
        />
      </CardContent>
    </Card>
  );
}
