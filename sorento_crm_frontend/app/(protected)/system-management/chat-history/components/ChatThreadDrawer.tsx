'use client';

import { useMemo, useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useChatThread } from '../hooks/useChatHistory';
import { useChatbotTurns, useShadowChatbotTurns } from '../hooks/useChatbotTurns';
import { ChatTranscript } from './ChatTranscript';
import type { ChatMessageRow } from '../types/chatHistory.types';

interface ChatThreadDrawerProps {
  row: ChatMessageRow | null;
  onOpenChange: (open: boolean) => void;
}

export function ChatThreadDrawer({ row, onOpenChange }: ChatThreadDrawerProps) {
  const [failedOnly, setFailedOnly] = useState(false);
  // AC-1029. Off by default: the shadow window is something the owner opens during a
  // promotion watch, and it costs a second page of turns.
  const [shadowOn, setShadowOn] = useState(false);
  const { data, isLoading } = useChatThread(row?.contact_id ?? null, row?.id);

  const messages = useMemo(() => data?.data ?? [], [data]);

  const {
    byMessageId,
    retryUnavailableReason,
    isLoading: turnsLoading,
    isError: turnsFailed,
  } = useChatbotTurns(row?.contact_id ?? null);

  const failedCount = useMemo(
    () => [...byMessageId.values()].filter((t) => t.status === 'failed').length,
    [byMessageId],
  );

  const {
    driftByMessage,
    shadowByMessage,
    summaryLine,
    isLoading: shadowLoading,
    isError: shadowFailed,
    isSuccess: shadowLoaded,
  } = useShadowChatbotTurns(row?.contact_id ?? null, byMessageId, shadowOn);

  return (
    <Sheet open={Boolean(row)} onOpenChange={onOpenChange}>
      {/* No description: the title is the contact, and Radix warns unless the absence is
          stated. A sentence explaining the drawer would be an on-screen explanation. */}
      <SheetContent className="w-full sm:max-w-xl flex flex-col p-0" aria-describedby={undefined}>
        <SheetHeader className="px-4 sm:px-6 py-4 border-b">
          <SheetTitle className="truncate">
            {data?.contact_display ?? row?.contact_display ?? 'Conversation'}
          </SheetTitle>
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              size="sm"
              variant={failedOnly ? 'primary' : 'outline'}
              onClick={() => setFailedOnly((v) => !v)}
              disabled={!failedCount && !failedOnly}
              aria-pressed={failedOnly}
              title={
                failedCount
                  ? 'Show only the messages whose turn failed'
                  : turnsLoading
                    ? 'Still loading the turns for this conversation'
                    : 'Nothing failed in this conversation'
              }
            >
              Failed turns only
              {failedCount > 0 && (
                <Badge variant="destructive" appearance="light" size="sm" className="ms-1.5">
                  {failedCount}
                </Badge>
              )}
            </Button>
            <Button
              size="sm"
              variant={shadowOn ? 'primary' : 'outline'}
              onClick={() => setShadowOn((v) => !v)}
              aria-pressed={shadowOn}
              title="Compare each turn with the parser version running in the shadow"
            >
              Shadow
            </Button>
            {turnsFailed && (
              <span className="text-xs text-destructive">
                Turn traces could not be loaded.
              </span>
            )}
            {turnsLoading && !turnsFailed && (
              <span className="text-xs text-muted-foreground">Loading turns…</span>
            )}
          </div>
          {/* AC-1030. One line, and only while the filter is on: what the window holds
              and how often the two parsers agreed. Each state is said in words - a
              parity of "0%" and "nothing to compare" are opposite findings. */}
          {shadowOn && (
            <div className="text-xs text-muted-foreground" data-testid="shadow-summary">
              {shadowFailed
                ? (
                    <span className="text-destructive">
                      Shadow turns could not be loaded.
                    </span>
                  )
                : shadowLoading
                  ? 'Loading the shadow window…'
                  : (summaryLine ??
                    (shadowLoaded
                      ? 'No shadow turns in this conversation. Set a parser shadow version in Settings > Chatbot.'
                      : ''))}
            </div>
          )}
        </SheetHeader>

        <div className="flex-1 min-h-0">
          <ChatTranscript
            messages={messages}
            isLoading={isLoading}
            anchorId={row?.id ?? null}
            turnsByMessageId={byMessageId}
            failedTurnsOnly={failedOnly}
            retryUnavailableReason={retryUnavailableReason}
            shadowOn={shadowOn}
            driftByMessageId={driftByMessage}
            shadowTurnsByMessageId={shadowByMessage}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}
