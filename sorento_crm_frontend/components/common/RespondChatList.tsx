'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  CheckCheck,
  AlertCircle,
  Clock,
  CornerUpLeft,
  FileText,
  Headphones,
  Image as ImageIcon,
  MapPin,
  Paperclip,
  Smile,
  Video,
} from 'lucide-react';
import {
  dateKeyFromMs,
  describeMessageAttachments,
  extractSelectionOptions,
  formatBubbleTime,
  formatDatePillLabel,
  getReceiptTier,
  splitMessageQuote,
  type MessageAttachmentDescriptor,
  type RespondMessageRenderable,
} from '@/lib/respondIoChatRender';
import { getRespondMessageDisplayTimeMs, getRespondMessageSortTimeMs } from '@/lib/respondIoMessage';
import {
  getNormalizedRespondSource,
  getOutgoingSenderLabel,
} from '@/lib/respondIoOutgoingMessage';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';

interface RespondChatListProps {
  items: RespondMessageRenderable[];
  contactName?: string | null;
  contactPhone?: string | null;
  emptyHint?: string;
  /** Caps message-list scroll height; chat header sits above. */
  maxHeightClass?: string;
  /**
   * If set, the bubble whose `messageId` matches gets a highlight ring + a
   * "Ticket based on this message" badge, and the list scrolls to it on mount
   * instead of to the latest message. String/number both accepted because the
   * Respond.io message id is numeric on the wire but ticket.source_message_id
   * is stored as text.
   */
  highlightMessageId?: string | number | null;
  /** Label shown above the highlighted bubble. */
  highlightLabel?: string;
  /**
   * When set, each bubble gets a "Reply" affordance that hands the message back
   * to the parent (the composer then quotes it). Omitted surfaces render exactly
   * as before.
   */
  onReply?: (item: RespondMessageRenderable) => void;
}

function AttachmentIcon({ kind }: { kind: MessageAttachmentDescriptor['kind'] }) {
  if (kind === 'image') return <ImageIcon className="size-3.5 shrink-0" />;
  if (kind === 'video') return <Video className="size-3.5 shrink-0" />;
  if (kind === 'audio') return <Headphones className="size-3.5 shrink-0" />;
  if (kind === 'file') return <FileText className="size-3.5 shrink-0" />;
  if (kind === 'sticker') return <Smile className="size-3.5 shrink-0" />;
  if (kind === 'location') return <MapPin className="size-3.5 shrink-0" />;
  return <Paperclip className="size-3.5 shrink-0" />;
}

/** Human label for an attachment: the real filename when we have one (ours end
 *  in the clean name by construction - AC-D5), else the typed placeholder. */
function attachmentDisplayName(item: MessageAttachmentDescriptor): string {
  return item.fileName || item.label;
}

/** Typed placeholder for a non-text payload. Images preview inline; everything
 *  else (including types we do not know) shows an icon + label, never a blank.
 *  With a URL the whole block opens the shared CRM attachment preview (AC-D6);
 *  without one it stays a static placeholder. */
function AttachmentBlock({
  item,
  onOpen,
}: {
  item: MessageAttachmentDescriptor;
  onOpen?: () => void;
}) {
  const name = attachmentDisplayName(item);
  const caption = item.fileName ? `${item.label} · ${item.fileName}` : item.label;
  const body = (
    <>
      {item.kind === 'image' && item.url ? (
        // Remote Respond.io media: a plain <img> (next/image needs configured hosts).
        <img
          src={item.url}
          alt={caption}
          className="max-h-48 w-full rounded object-cover"
          loading="lazy"
        />
      ) : null}
      <div className="flex items-center gap-1.5 px-0.5 pt-1 text-xs opacity-80" title={caption}>
        <AttachmentIcon kind={item.kind} />
        <span className="truncate">{caption}</span>
      </div>
    </>
  );
  const shell = 'mt-1 rounded-md border border-black/5 bg-black/5 p-1.5 dark:border-white/10 dark:bg-white/5';
  if (!onOpen) return <div className={shell}>{body}</div>;
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`Preview ${name}`}
      className={`${shell} block w-full cursor-pointer text-left hover:bg-black/10 dark:hover:bg-white/10`}
    >
      {body}
    </button>
  );
}

function ReceiptTicks({ tier }: { tier: ReturnType<typeof getReceiptTier> }) {
  if (tier === 'none') return null;
  if (tier === 'sending') return <Clock className="size-3.5 opacity-70" aria-label="Sending" />;
  if (tier === 'failed') return <AlertCircle className="size-3.5 text-red-500" aria-label="Failed" />;
  if (tier === 'sent') return <Check className="size-3.5 opacity-70" aria-label="Sent" />;
  if (tier === 'delivered')
    return <CheckCheck className="size-3.5 opacity-70" aria-label="Delivered" />;
  return <CheckCheck className="size-3.5 text-sky-500" aria-label="Read" />;
}

export default function RespondChatList({
  items,
  contactName,
  contactPhone,
  emptyHint = 'No messages yet.',
  maxHeightClass = 'max-h-[60vh]',
  highlightMessageId = null,
  highlightLabel = 'Ticket based on this message',
  onReply,
}: RespondChatListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLDivElement>(null);

  // AC-D6: attachment bubbles open the SAME preview surface the rest of the CRM
  // uses (image/video/pdf inline, spreadsheets via its Excel slide, everything
  // else its download/open fallback) - never a raw-URL new tab. Chat media has
  // no `attachments` row, so items carry the CDN url only: no `downloadUrl`
  // means the modal's authenticated byte-fetch is never called, which is also
  // what keeps this working on the token-authenticated portal thread.
  const [previewItems, setPreviewItems] = useState<AttachmentPreviewItem[]>([]);
  const [previewIndex, setPreviewIndex] = useState(0);

  const openPreview = useCallback(
    (attachments: MessageAttachmentDescriptor[], clicked: number, idPrefix: string) => {
      const items = attachments
        .map((att, i) => ({ att, i }))
        .filter(({ att }) => !!att.url)
        .map(({ att, i }) => ({
          id: `${idPrefix}-att-${i}`,
          name: attachmentDisplayName(att),
          url: att.url as string,
        }));
      if (items.length === 0) return;
      const start = items.findIndex((it) => it.id === `${idPrefix}-att-${clicked}`);
      setPreviewIndex(start < 0 ? 0 : start);
      setPreviewItems(items);
    },
    [],
  );

  const normalizedHighlightId =
    highlightMessageId != null && String(highlightMessageId).trim() !== ''
      ? String(highlightMessageId)
      : null;

  const sortedItems = useMemo(() => {
    return [...items].sort((a, b) => {
      const ta = getRespondMessageSortTimeMs(a);
      const tb = getRespondMessageSortTimeMs(b);
      if (ta !== tb) return ta - tb;
      return (a.messageId ?? 0) - (b.messageId ?? 0);
    });
  }, [items]);

  useEffect(() => {
    if (normalizedHighlightId && highlightRef.current) {
      highlightRef.current.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
      return;
    }
    messagesEndRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  }, [sortedItems.length, normalizedHighlightId]);

  const contactInitial = (contactName?.trim()?.charAt(0) || '?').toUpperCase();
  const headerName = contactName?.trim() || 'Unknown contact';
  const headerPhone = contactPhone?.trim() || '';

  let lastDateKey = '';

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-3 rounded-t-md border border-b-0 bg-[#f0f2f5] dark:bg-[#202c33] px-3 py-2">
        <div className="flex size-9 items-center justify-center rounded-full bg-emerald-600 text-sm font-semibold text-white">
          {contactInitial}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {headerName}
          </div>
          {headerPhone && (
            <div className="truncate text-xs text-zinc-500 dark:text-zinc-400">{headerPhone}</div>
          )}
        </div>
      </div>

      <div
        className={`flex flex-col gap-2 overflow-y-auto rounded-b-md border bg-[#efeae2] dark:bg-[#0b141a] p-3 ${maxHeightClass}`}
      >
        {sortedItems.length === 0 && (
          <p className="py-4 text-center text-sm text-zinc-500 dark:text-zinc-400">{emptyHint}</p>
        )}
        {sortedItems.map((item, idx) => {
          const isOutgoing = item.traffic === 'outgoing';
          // Direction aware: only OUR outgoing replies carry the ">" quote
          // convention. A contact message starting with ">" renders verbatim.
          const { quoted, body: text } = splitMessageQuote(item);
          const attachments = describeMessageAttachments(item);
          const displayMs = getRespondMessageDisplayTimeMs(item);
          const key = item.messageId != null ? String(item.messageId) : `msg-${idx}`;

          const dKey = displayMs > 0 ? dateKeyFromMs(displayMs) : '';
          const dividerLabel =
            dKey && dKey !== lastDateKey ? formatDatePillLabel(displayMs) : '';
          if (dKey) lastDateKey = dKey;

          const sourceNorm = getNormalizedRespondSource(item);
          const senderLabel = isOutgoing ? getOutgoingSenderLabel(sourceNorm) : 'Contact';

          const bubbleClass = isOutgoing
            ? 'bg-[#d9fdd3] text-zinc-900 dark:bg-[#005c4b] dark:text-zinc-50'
            : 'bg-white text-zinc-900 dark:bg-[#202c33] dark:text-zinc-50';

          const options = extractSelectionOptions(item);
          const tier = getReceiptTier(item);
          const isHighlighted =
            normalizedHighlightId != null && String(item.messageId ?? '') === normalizedHighlightId;

          return (
            <div key={key} ref={isHighlighted ? highlightRef : undefined}>
              {dividerLabel && (
                <div className="sticky top-0 z-10 my-2 flex justify-center">
                  <span className="rounded-md bg-[#e1f3fb] dark:bg-[#1d282f] px-3 py-0.5 text-xs font-medium text-zinc-700 dark:text-zinc-300 shadow-sm">
                    {dividerLabel}
                  </span>
                </div>
              )}
              {isHighlighted && (
                <div className={`mb-1 flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-300 dark:bg-amber-900/40 dark:text-amber-200 dark:ring-amber-700">
                    {highlightLabel}
                  </span>
                </div>
              )}
              <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[85%] rounded-lg px-2.5 py-1.5 text-sm shadow-sm ${bubbleClass}${
                    isHighlighted ? ' ring-2 ring-amber-400 dark:ring-amber-500' : ''
                  }`}
                >
                  <div className="mb-0.5 flex items-center gap-2">
                    <span className="text-[11px] font-semibold text-emerald-700 dark:text-emerald-300">
                      {senderLabel}
                    </span>
                    {onReply && (
                      <button
                        type="button"
                        className="ms-auto inline-flex items-center gap-1 rounded px-1 py-0.5 text-[10px] text-zinc-500 hover:bg-black/5 hover:text-zinc-800 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-zinc-100"
                        onClick={() => onReply(item)}
                        aria-label="Reply to this message"
                      >
                        <CornerUpLeft className="size-3" />
                        Reply
                      </button>
                    )}
                  </div>
                  {quoted && (
                    <div className="mb-1 rounded border-s-2 border-emerald-500 bg-black/5 px-2 py-1 text-xs italic opacity-80 dark:bg-white/5">
                      <span className="line-clamp-3 whitespace-pre-wrap break-words">{quoted}</span>
                    </div>
                  )}
                  {attachments.map((att, i) => (
                    <AttachmentBlock
                      key={`${key}-att-${i}`}
                      item={att}
                      onOpen={att.url ? () => openPreview(attachments, i, key) : undefined}
                    />
                  ))}
                  {text && (
                    <div className="whitespace-pre-wrap break-words leading-snug">{text}</div>
                  )}
                  {options.length > 0 && (
                    <div className="mt-2 flex flex-col divide-y divide-zinc-200 overflow-hidden rounded border border-zinc-200 bg-white/70 dark:divide-zinc-700 dark:border-zinc-700 dark:bg-zinc-900/40">
                      {options.map((opt, i) => (
                        <div
                          key={`${key}-opt-${i}`}
                          className="px-2.5 py-1.5 text-xs text-zinc-800 dark:text-zinc-200"
                        >
                          {opt}
                        </div>
                      ))}
                    </div>
                  )}
                  {!text && options.length === 0 && attachments.length === 0 && !quoted && (
                    <div className="italic opacity-70">(no text)</div>
                  )}
                  <div className="mt-1 flex items-center justify-end gap-1 text-[10px] text-zinc-500 dark:text-zinc-300/80">
                    {displayMs > 0 && <span>{formatBubbleTime(displayMs)}</span>}
                    <ReceiptTicks tier={tier} />
                  </div>
                </div>
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      <AttachmentPreviewModal
        open={previewItems.length > 0}
        onOpenChange={(next) => {
          if (!next) setPreviewItems([]);
        }}
        items={previewItems}
        startIndex={previewIndex}
      />
    </div>
  );
}
