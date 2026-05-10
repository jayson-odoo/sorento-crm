'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Bot, MessageCircle, User as UserIcon } from 'lucide-react';
import type { Ticket } from '../types/ticket.types';

const CHANNEL_LABEL: Record<Ticket['source_channel'], string> = {
  manual: 'Manual',
  ai_assistant: 'AI Assistant',
  whatsapp_respond: 'WhatsApp',
};

interface TicketSourceCardProps {
  ticket: Ticket;
}

/**
 * Header strip showing where the ticket came from. For AI-assistant tickets,
 * links to the originating conversation. For WhatsApp tickets, shows the
 * submitter's name + phone (the actual chat history is on the Activities
 * panel's Messages tab, which loads from the linked respond_contacts).
 */
export default function TicketSourceCard({ ticket }: TicketSourceCardProps) {
  const channel = ticket.source_channel;
  const actor = ticket.raised_by_actor;
  const Icon = channel === 'ai_assistant' ? Bot : channel === 'whatsapp_respond' ? MessageCircle : UserIcon;
  const pathname = usePathname();

  const assistantHref = (() => {
    if (channel !== 'ai_assistant' || !ticket.source_conversation_id) return null;
    const sp = new URLSearchParams();
    sp.set('ai_conversation', ticket.source_conversation_id);
    if (ticket.source_message_id) sp.set('ai_message', ticket.source_message_id);
    return `${pathname || '/'}?${sp.toString()}`;
  })();

  return (
    <Card className="p-4 flex flex-wrap items-center gap-3 text-sm">
      <Icon className="size-4 text-muted-foreground" />
      <Badge variant="secondary">{CHANNEL_LABEL[channel]}</Badge>
      {actor?.display_name && (
        <span className="font-medium">{actor.display_name}</span>
      )}
      {actor?.phone_number && (
        <span className="text-muted-foreground">{actor.phone_number}</span>
      )}
      {actor?.email && (
        <span className="text-muted-foreground">{actor.email}</span>
      )}
      {assistantHref && (
        <Link
          href={assistantHref}
          replace
          scroll={false}
          className="ms-auto text-primary hover:underline text-xs"
        >
          Open assistant conversation →
        </Link>
      )}
      {channel === 'whatsapp_respond' && (
        <span className="ms-auto text-xs text-muted-foreground">
          Reply to this contact via the Messages tab on the right.
        </span>
      )}
    </Card>
  );
}
