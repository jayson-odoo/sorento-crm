'use client';

import { Paperclip } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

/**
 * The files a turn's `send_attachments` action would send - shared by Chat History
 * (`ChatbotTurn.response.actions`) and the chatbot console (`ConsoleTurnResponse.
 * actions`), which carry the same raw `TurnResult.actions` shape from two different
 * endpoints. One extraction function and one render, so the two screens cannot read or
 * show it two different ways.
 */

/** One file `actions[].kind === 'send_attachments'` carries (backend
 * `app/services/chatbot/engine.py::_clean_attachments`): `{url, filename, mimeType,
 * attachmentType[, uploadedAt]}` and nothing else. */
export interface TurnAttachment {
  url: string;
  filename: string;
  mimeType: string;
  attachmentType: string;
  uploadedAt?: string | null;
}

function isAttachment(value: unknown): value is TurnAttachment {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as Record<string, unknown>).url === 'string' &&
    typeof (value as Record<string, unknown>).filename === 'string'
  );
}

/**
 * The files a `send_attachments` action would send, or `[]` when `actions` carries
 * none.
 *
 * `actions[].attachments_src` is backend `engine.py::_clean_attachments`'s own value -
 * either the bare file list, or (when the source it cleaned was an envelope rather than
 * a plain list) that envelope with its `attachments` key rewritten in place - so both
 * shapes are read here rather than assuming the array form. Every entry is re-checked
 * for `url` + `filename` before it renders: the field is loosely typed on the wire
 * (both `ChatbotTurnResponse.response` and `ConsoleTurnResponse.actions` say so in
 * their own docstrings) because it is the engine's shape, not either screen's.
 */
export function extractTurnAttachments(actions: unknown): TurnAttachment[] {
  if (!Array.isArray(actions)) return [];
  const action = actions.find(
    (a): a is Record<string, unknown> =>
      typeof a === 'object' && a !== null && (a as Record<string, unknown>).kind === 'send_attachments',
  );
  if (!action) return [];
  const src = action.attachments_src;
  const list = Array.isArray(src)
    ? src
    : src && typeof src === 'object'
      ? (src as Record<string, unknown>).attachments
      : null;
  return Array.isArray(list) ? list.filter(isAttachment) : [];
}

/**
 * The files a turn's `send_attachments` action would send, under the reply it belongs
 * to. Console-verification surface (`documentation/agents/chatbot-verification.md`):
 * an operator can see what n8n would hand the customer without opening a file, no
 * `attachmentType` explainer needed (Cursor rule - the badge is the label, not a
 * lesson).
 *
 * Renders nothing when `attachments` is empty.
 */
export function TurnAttachments({ attachments }: { attachments: TurnAttachment[] }) {
  if (attachments.length === 0) return null;

  return (
    <div className="mt-1.5 space-y-1" data-testid="turn-attachments">
      {attachments.map((file, i) => (
        <div key={`${file.url}-${i}`} className="flex items-center gap-1.5 text-xs">
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
