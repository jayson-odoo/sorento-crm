'use client';

import { Paperclip } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { turnAttachments } from '../turnPresentation';
import type { ChatbotTurn } from '../types/chatbotTurn.types';

/**
 * The files this turn's `send_attachments` action would send, under the reply bubble
 * it belongs to. Console-verification surface (`documentation/agents/
 * chatbot-verification.md`): an operator reading chat history can see what n8n would
 * hand the customer without opening a file, no `attachmentType` explainer needed (Cursor
 * rule - the badge is the label, not a lesson).
 *
 * Renders nothing when the turn's response carries no such action (most turns) or none
 * of its entries pass `turnAttachments`' own shape check.
 */
export function TurnAttachments({ turn }: { turn: ChatbotTurn }) {
  const files = turnAttachments(turn);
  if (files.length === 0) return null;

  return (
    <div className="mt-1.5 max-w-[85%] space-y-1" data-testid="turn-attachments">
      {files.map((file, i) => (
        <div
          key={`${file.url}-${i}`}
          className="flex items-center gap-1.5 text-xs"
        >
          <Paperclip className="size-3.5 shrink-0 text-muted-foreground" />
          <a
            href={file.url}
            target="_blank"
            rel="noopener noreferrer"
            className="truncate underline underline-offset-2 hover:text-primary"
            title={file.filename}
          >
            {file.filename}
          </a>
          <Badge appearance="light" size="sm" className="shrink-0">
            {file.attachmentType}
          </Badge>
          <span className="shrink-0 text-muted-foreground">{file.mimeType}</span>
        </div>
      ))}
    </div>
  );
}
