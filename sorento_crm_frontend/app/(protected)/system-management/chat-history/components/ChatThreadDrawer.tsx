'use client';

import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { useChatThread } from '../hooks/useChatHistory';
import { ChatTranscript } from './ChatTranscript';
import type { ChatMessageRow } from '../types/chatHistory.types';

interface ChatThreadDrawerProps {
  row: ChatMessageRow | null;
  onOpenChange: (open: boolean) => void;
}

export function ChatThreadDrawer({ row, onOpenChange }: ChatThreadDrawerProps) {
  const { data, isLoading } = useChatThread(row?.contact_id ?? null, row?.id);

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

        <div className="flex-1 min-h-0">
          <ChatTranscript
            messages={data?.data ?? []}
            isLoading={isLoading}
            anchorId={row?.id ?? null}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}
