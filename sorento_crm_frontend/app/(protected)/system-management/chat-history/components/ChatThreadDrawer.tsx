'use client';

import { useEffect, useRef } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useChatThread } from '../hooks/useChatHistory';
import type { ChatMessageRow } from '../types/chatHistory.types';

interface ChatThreadDrawerProps {
  row: ChatMessageRow | null;
  onOpenChange: (open: boolean) => void;
}

function LatencyBadge({ seconds }: { seconds: number }) {
  // Colour by how far past a "few seconds" the reply landed. Deliberately coarse —
  // the exact target lives in settings, this is a reading aid, not the SLA verdict.
  const variant = seconds > 30 ? 'destructive' : seconds > 10 ? 'warning' : 'success';
  return (
    <Badge variant={variant as never} className="ml-2 shrink-0">
      {seconds < 1 ? `${Math.round(seconds * 1000)}ms` : `${seconds.toFixed(1)}s`}
    </Badge>
  );
}

export function ChatThreadDrawer({ row, onOpenChange }: ChatThreadDrawerProps) {
  const { data, isLoading } = useChatThread(row?.contact_id ?? null, row?.id);
  const anchorRef = useRef<HTMLDivElement | null>(null);

  // Land on the message that was clicked. Bot replies here run to hundreds of lines,
  // so opening at the oldest message can leave the anchor several screens down.
  useEffect(() => {
    if (isLoading || !data?.data.length) return;
    const id = window.requestAnimationFrame(() =>
      anchorRef.current?.scrollIntoView({ block: 'center' }),
    );
    return () => window.cancelAnimationFrame(id);
  }, [isLoading, data, row?.id]);

  return (
    <Sheet open={Boolean(row)} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-xl flex flex-col p-0">
        <SheetHeader className="px-6 py-4 border-b">
          <SheetTitle className="truncate">
            {data?.contact_display ?? row?.contact_display ?? 'Conversation'}
          </SheetTitle>
          <p className="text-xs text-muted-foreground">
            Transcript around the selected message, oldest first.
          </p>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {isLoading && (
            <>
              <Skeleton className="h-16 w-3/4" />
              <Skeleton className="h-16 w-3/4 ml-auto" />
              <Skeleton className="h-16 w-2/3" />
            </>
          )}

          {!isLoading && data?.empty && (
            <div className="text-center py-12">
              <p className="text-sm text-muted-foreground">
                No messages stored for this contact.
              </p>
            </div>
          )}

          {!isLoading &&
            data?.data.map((m) => {
              const outgoing = m.type === 'outgoing';
              const selected = m.id === row?.id;
              return (
                <div
                  key={m.id}
                  ref={selected ? anchorRef : undefined}
                  className={`flex ${outgoing ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={[
                      'max-w-[85%] rounded-lg px-3 py-2 text-sm',
                      outgoing ? 'bg-primary/10' : 'bg-muted',
                      selected ? 'ring-2 ring-primary' : '',
                    ].join(' ')}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-[11px] text-muted-foreground">
                        {formatDateTimeInMalaysia(m.sent_at)}
                      </span>
                      {m.latency_seconds != null && (
                        <LatencyBadge seconds={m.latency_seconds} />
                      )}
                    </div>
                    <p className="whitespace-pre-wrap break-words">{m.message}</p>
                    {m.delivery_status && (
                      <span className="text-[11px] text-muted-foreground">
                        {m.delivery_status}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
        </div>
      </SheetContent>
    </Sheet>
  );
}
