'use client';

import { useMemo, useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useChatThread } from '../hooks/useChatHistory';
import { useChatbotTurns, useRetryAvailability } from '../hooks/useChatbotTurns';
import { ChatTranscript } from './ChatTranscript';
import type { ChatMessageRow } from '../types/chatHistory.types';

interface ChatThreadDrawerProps {
  row: ChatMessageRow | null;
  onOpenChange: (open: boolean) => void;
}

export function ChatThreadDrawer({ row, onOpenChange }: ChatThreadDrawerProps) {
  const [failedOnly, setFailedOnly] = useState(false);
  const { data, isLoading } = useChatThread(row?.contact_id ?? null, row?.id);

  const messages = useMemo(() => data?.data ?? [], [data]);

  const {
    byMessageId,
    isLoading: turnsLoading,
    isError: turnsFailed,
  } = useChatbotTurns(row?.contact_id ?? null);
  const { data: retry } = useRetryAvailability(Boolean(row));

  const failedCount = useMemo(
    () => [...byMessageId.values()].filter((t) => t.status === 'failed').length,
    [byMessageId],
  );

  return (
    <Sheet open={Boolean(row)} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-xl flex flex-col p-0">
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
            >
              Failed turns only
              {failedCount > 0 && (
                <Badge variant="destructive" appearance="light" size="sm" className="ms-1.5">
                  {failedCount}
                </Badge>
              )}
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
        </SheetHeader>

        <div className="flex-1 min-h-0">
          <ChatTranscript
            messages={messages}
            isLoading={isLoading}
            anchorId={row?.id ?? null}
            turnsByMessageId={byMessageId}
            failedTurnsOnly={failedOnly}
            retryUnavailableReason={retry && !retry.available ? retry.reason : null}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}
