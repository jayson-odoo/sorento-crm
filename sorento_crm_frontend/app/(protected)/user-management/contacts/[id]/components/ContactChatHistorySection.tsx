'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useChatThread } from '@/app/(protected)/system-management/chat-history/hooks/useChatHistory';
import { ChatTranscript } from '@/app/(protected)/system-management/chat-history/components/ChatTranscript';

interface ContactChatHistorySectionProps {
  /** Respond.io contact id — chat_histories.contact_id is this string, not the CRM id. */
  respondIoId: string | null;
}

export default function ContactChatHistorySection({ respondIoId }: ContactChatHistorySectionProps) {
  const { data, isLoading } = useChatThread(respondIoId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Chat History</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {!respondIoId ? (
          <div className="px-6 py-10 text-center">
            <p className="text-sm text-muted-foreground">
              No Respond.io ID on this contact, so there is no WhatsApp conversation to show.
            </p>
          </div>
        ) : (
          // Bounded height so a long transcript scrolls inside its own panel rather
          // than stretching the detail page. Search lives inside the transcript.
          <div className="h-[32rem]">
            <ChatTranscript
              messages={data?.data ?? []}
              isLoading={isLoading}
              emptyText="No WhatsApp messages stored for this contact yet."
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
