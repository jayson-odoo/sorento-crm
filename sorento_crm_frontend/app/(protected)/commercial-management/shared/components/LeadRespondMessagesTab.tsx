'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, RefreshCw, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import type { RespondMessageItem } from '@/app/(protected)/procurement-management/stock-inquiries/services/stockInquiryService';
import {
  getLeadRespondConversation,
  listLeadRespondContacts,
  postLeadRespondConversationReply,
} from '@/app/(protected)/commercial/leads/services/leadRespondContactsService';
import type { LeadRespondContactRow } from '@/app/(protected)/commercial/leads/types/lead.types';
import {
  formatChatDayPillMalaysia,
  formatTimeShortMalaysia,
  getMalaysiaDateKey,
} from '@/lib/helpers';
import {
  compareRespondMessages,
  getRespondMessageDisplayTimeMs,
} from '@/lib/respondConversationMessage';
import {
  getNormalizedRespondSource,
  getOutgoingBubbleClass,
  getOutgoingSenderLabel,
} from '@/lib/respondIoOutgoingMessage';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

/** Distance from scroll bottom within which we treat the list as “pinned” (latest messages). */
const SCROLL_BOTTOM_THRESHOLD_PX = 72;

/** WhatsApp-style bubble for CRM / human outgoing; automation keeps distinct colors from `getOutgoingBubbleClass`. */
function getLeadOutgoingBubbleClass(sourceNorm: string): string {
  if (
    sourceNorm === 'n8n' ||
    sourceNorm === 'workflow' ||
    sourceNorm === 'ai_agent' ||
    sourceNorm === 'agent'
  ) {
    return cn(getOutgoingBubbleClass(sourceNorm), 'shadow-sm');
  }
  return 'bg-[#DCF8C6] text-[#111827] shadow-sm';
}

function pickDefaultContactId(rows: LeadRespondContactRow[]): string | null {
  if (!rows.length) return null;
  const main = rows.find((r) => r.contact_role === 'main');
  return (main ?? rows[0])!.respond_contact_id;
}

function contactLabel(row: LeadRespondContactRow): string {
  const name = (row.contact.name || '').trim();
  const phone = row.contact.phone_number || '';
  const bits = [name || null, phone || null].filter(Boolean);
  const base = bits.join(' · ') || 'Contact';
  return row.contact_role === 'main' ? `${base} (primary)` : base;
}

function getReplyPreviewText(item: RespondMessageItem): string {
  const msg = item.replyTo?.message;
  const text = (msg?.text ?? '').trim();
  if (text) return text;
  const title = (msg?.title ?? '').trim();
  if (title) return title;
  const fileName = (msg?.attachment?.fileName ?? '').trim();
  if (fileName) return `Attachment: ${fileName}`;
  if (item.replyTo?.messageId != null) return `Reply to #${item.replyTo.messageId}`;
  return '';
}

function isImageAttachment(att?: RespondMessageItem['message'] extends infer M
  ? M extends { attachment?: infer A }
    ? A
    : never
  : never): boolean {
  if (!att) return false;
  const type = `${att.type ?? ''} ${att.mimeType ?? ''} ${att.mime ?? ''}`.toLowerCase();
  const ext = (att.ext ?? '').toLowerCase();
  return (
    type.includes('image') ||
    ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'heic', 'heif'].includes(ext)
  );
}

function isVideoAttachment(att?: RespondMessageItem['message'] extends infer M
  ? M extends { attachment?: infer A }
    ? A
    : never
  : never): boolean {
  if (!att) return false;
  const type = `${att.type ?? ''} ${att.mimeType ?? ''} ${att.mime ?? ''}`.toLowerCase();
  const ext = (att.ext ?? '').toLowerCase();
  return type.includes('video') || ['mp4', 'mov', 'webm', 'm4v', 'avi'].includes(ext);
}

export function LeadRespondMessagesTab({
  leadId,
  canPost,
  active,
}: {
  leadId: string;
  canPost: boolean;
  active: boolean;
}) {
  const qc = useQueryClient();
  const [replyText, setReplyText] = useState('');
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const [stickyDayLabel, setStickyDayLabel] = useState('');
  /** Floating date shows only while scrolled up into history (hidden when pinned to bottom). */
  const [showFloatingDate, setShowFloatingDate] = useState(false);

  const { data: contactRows = [], isLoading: contactsLoading } = useQuery({
    queryKey: ['lead-respond-contacts', leadId],
    queryFn: () => listLeadRespondContacts(leadId),
    enabled: active && !!leadId,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (!contactRows.length) {
      setSelectedContactId(null);
      return;
    }
    const ids = new Set(contactRows.map((r) => r.respond_contact_id));
    setSelectedContactId((prev) => {
      if (prev && ids.has(prev)) return prev;
      return pickDefaultContactId(contactRows);
    });
  }, [leadId, contactRows]);

  const {
    data: convo,
    isLoading: convoLoading,
    isRefetching,
    refetch,
  } = useQuery({
    queryKey: ['lead-respond-conversation', leadId, selectedContactId],
    queryFn: () =>
      getLeadRespondConversation(leadId, selectedContactId!, {
        limit: 50,
      }),
    enabled: active && !!leadId && !!selectedContactId,
    staleTime: 15_000,
    refetchInterval: active ? 15_000 : false,
  });

  const replyMutation = useMutation({
    mutationFn: (text: string) =>
      postLeadRespondConversationReply(leadId, selectedContactId!, text),
    onSuccess: async () => {
      toast.success('Sent');
      setReplyText('');
      await qc.invalidateQueries({ queryKey: ['lead-respond-conversation', leadId, selectedContactId] });
      await refetch();
      window.setTimeout(() => {
        void refetch();
      }, 1600);
    },
    onError: (e: Error) => toast.error(e.message || 'Could not send'),
  });

  const items: RespondMessageItem[] = convo?.items ?? [];
  const sortedItems = useMemo(() => {
    return [...items].sort(compareRespondMessages);
  }, [items]);

  type DayGroup = { key: string; pill: string; items: RespondMessageItem[] };
  const dayGroups = useMemo((): DayGroup[] => {
    const groups: DayGroup[] = [];
    for (const item of sortedItems) {
      const ms = getRespondMessageDisplayTimeMs(item);
      const d = new Date(ms);
      const key = ms > 0 ? getMalaysiaDateKey(d) : '';
      const pill = ms > 0 && !Number.isNaN(d.getTime()) ? formatChatDayPillMalaysia(d) : '';
      const safeKey = key || `unknown-${groups.length}`;
      const safePill = pill || '—';
      const last = groups[groups.length - 1];
      if (last && last.key === safeKey) {
        last.items.push(item);
      } else {
        groups.push({ key: safeKey, pill: safePill, items: [item] });
      }
    }
    return groups;
  }, [sortedItems]);

  const handleViewportScroll = useCallback(() => {
    const root = viewportRef.current;
    if (!root || dayGroups.length === 0) {
      setShowFloatingDate(false);
      return;
    }

    const { scrollTop, scrollHeight, clientHeight } = root;
    const distanceFromBottom = scrollHeight - clientHeight - scrollTop;
    const pinnedToBottom =
      scrollHeight <= clientHeight + 2 || distanceFromBottom <= SCROLL_BOTTOM_THRESHOLD_PX;

    setShowFloatingDate(!pinnedToBottom && sortedItems.length > 0);

    const rootRect = root.getBoundingClientRect();
    let label = dayGroups[0]?.pill ?? '';
    root.querySelectorAll<HTMLElement>('[data-day-pill-anchor]').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.top <= rootRect.top + 56) {
        const p = el.getAttribute('data-day-pill');
        if (p) label = p;
      }
    });
    setStickyDayLabel(label);
  }, [dayGroups, sortedItems.length]);

  useEffect(() => {
    const root = viewportRef.current;
    if (!root) return;
    handleViewportScroll();
    root.addEventListener('scroll', handleViewportScroll, { passive: true });
    const ro = new ResizeObserver(() => handleViewportScroll());
    ro.observe(root);
    return () => {
      root.removeEventListener('scroll', handleViewportScroll);
      ro.disconnect();
    };
  }, [handleViewportScroll]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' });
    const id = window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => handleViewportScroll());
    });
    return () => window.cancelAnimationFrame(id);
  }, [sortedItems.length, selectedContactId, handleViewportScroll]);

  const handleSend = async () => {
    const text = replyText.trim();
    if (!text || replyMutation.isPending || !selectedContactId) return;
    await replyMutation.mutateAsync(text);
  };

  const inboxUrl = convo?.inbox_url ?? null;
  const unavailable = Boolean(convo?.unavailable);

  const showListSkeleton = contactsLoading || (convoLoading && !!selectedContactId);

  return (
    <div className="flex min-h-0 flex-1 flex-col px-0 pb-0 pt-2">
      <div className="flex flex-shrink-0 items-start gap-2 px-4 pb-2">
        <Select
          value={selectedContactId ?? ''}
          onValueChange={(v) => setSelectedContactId(v || null)}
          disabled={contactRows.length === 0 || contactsLoading}
        >
          <SelectTrigger className="h-9 flex-1 border-[#e5e7eb] bg-white text-left text-sm">
            <SelectValue placeholder="Choose a contact" />
          </SelectTrigger>
          <SelectContent>
            {contactRows.map((row) => (
              <SelectItem key={row.respond_contact_id} value={row.respond_contact_id}>
                {contactLabel(row)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex shrink-0 gap-0.5">
          {inboxUrl ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-9 shrink-0 text-[#6a7282]"
              onClick={() => window.open(inboxUrl, '_blank')}
              aria-label="Open in inbox"
            >
              <ExternalLink className="size-4" />
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-9 shrink-0 text-[#6a7282]"
            disabled={!selectedContactId || isRefetching}
            onClick={() => refetch()}
            aria-label="Refresh"
          >
            <RefreshCw className={cn('size-4', isRefetching && 'animate-spin')} />
          </Button>
        </div>
      </div>

      <div className="relative min-h-0 flex-1 px-4">
        <div className="pointer-events-none absolute inset-x-4 top-0 z-20 flex justify-center pt-1">
          {showFloatingDate && stickyDayLabel ? (
            <span className="rounded-full border border-[#e5e7eb]/80 bg-background/95 px-3 py-1 text-xs font-medium text-[#6a7282] shadow-sm backdrop-blur-sm transition-opacity duration-150">
              {stickyDayLabel}
            </span>
          ) : null}
        </div>

        <ScrollArea
          className="h-full max-h-[inherit] min-h-0 flex-1"
          viewportRef={viewportRef}
          viewportClassName={cn(showFloatingDate && 'pt-10')}
        >
          <div className="flex flex-col gap-1 pb-4 pr-2 pt-1">
            {!contactsLoading && contactRows.length === 0 ? (
              <p className="text-muted-foreground py-8 text-center text-sm">No contacts on this lead.</p>
            ) : showListSkeleton ? (
              <div className="space-y-2">
                <Skeleton className="h-14 w-full rounded-xl" />
                <Skeleton className="h-14 w-full rounded-xl" />
                <Skeleton className="h-14 w-full rounded-xl" />
              </div>
            ) : unavailable ? (
              <p className="text-muted-foreground py-8 text-center text-sm">
                Chat isn&apos;t available for this contact yet.
              </p>
            ) : sortedItems.length === 0 ? (
              <p className="text-muted-foreground py-8 text-center text-sm">No messages yet.</p>
            ) : (
              <div className="flex flex-col gap-2 rounded-xl border border-dashed border-[#e5e7eb] bg-muted/30 p-3">
                {dayGroups.map((g, groupIdx) => (
                  <div key={`${g.key}-${groupIdx}`} className="flex flex-col gap-2">
                    <div
                      className="flex justify-center py-1"
                      data-day-pill-anchor
                      data-day-pill={g.pill}
                    >
                      <span className="rounded-full border border-dashed border-[#e5e7eb] bg-background/90 px-3 py-0.5 text-[11px] text-[#6a7282]">
                        {g.pill}
                      </span>
                    </div>
                    {g.items.map((item, idx) => {
                      const isOutgoing = item.traffic === 'outgoing';
                      const text = item.message?.text ?? '';
                      const title = item.message?.title ?? '';
                      const quickReplies = item.message?.replies ?? [];
                      const attachment = item.message?.attachment;
                      const attachmentUrl = (attachment?.url ?? '').trim();
                      const replyPreview = getReplyPreviewText(item);
                      const messageType = (item.message?.type ?? 'text').toLowerCase();
                      const ms = getRespondMessageDisplayTimeMs(item);
                      const tsDate = new Date(ms);
                      const timeOnly =
                        ms > 0 && !Number.isNaN(tsDate.getTime())
                          ? formatTimeShortMalaysia(tsDate)
                          : '';
                      const sourceNorm = getNormalizedRespondSource(item);
                      const senderLabel = isOutgoing ? getOutgoingSenderLabel(sourceNorm) : 'Contact';
                      const bubbleClass = isOutgoing
                        ? getLeadOutgoingBubbleClass(sourceNorm)
                        : 'border border-dashed border-[#e5e7eb] bg-white text-[#364153]';
                      return (
                        <div
                          key={item.messageId != null ? String(item.messageId) : `msg-${g.key}-${idx}`}
                          className={cn('flex', isOutgoing ? 'justify-end' : 'justify-start')}
                        >
                          <div
                            className={cn(
                              'max-w-[85%] min-w-0 rounded-xl px-3 py-2 text-sm',
                              bubbleClass,
                            )}
                          >
                            <div
                              className={cn(
                                'mb-1 text-[11px] font-medium leading-tight',
                                isOutgoing ? 'opacity-90' : 'text-[#6a7282]',
                              )}
                            >
                              {senderLabel}
                            </div>
                            {replyPreview ? (
                              <div
                                className={cn(
                                  'mb-2 rounded-md border-l-2 px-2 py-1 text-xs',
                                  isOutgoing
                                    ? 'border-[#22c55e] bg-black/5 text-[#1f2937]'
                                    : 'border-[#9ca3af] bg-[#f3f4f6] text-[#4b5563]',
                                )}
                              >
                                <div className="truncate whitespace-pre-wrap break-words">{replyPreview}</div>
                              </div>
                            ) : null}
                            <div className="flex items-end justify-end gap-2">
                              <div className="min-w-0 flex-1">
                                {messageType === 'quick_reply' ? (
                                  <div className="space-y-2">
                                    <div className="whitespace-pre-wrap break-words">{title || text || '—'}</div>
                                    {quickReplies.length > 0 ? (
                                      <div className="overflow-hidden rounded-md border border-black/10">
                                        {quickReplies.map((reply, replyIdx) => (
                                          <div
                                            key={`${item.messageId ?? idx}-reply-${replyIdx}`}
                                            className={cn(
                                              'bg-white/80 px-2 py-1.5 text-xs font-medium text-[#374151]',
                                              replyIdx > 0 && 'border-t border-black/10',
                                            )}
                                          >
                                            {reply}
                                          </div>
                                        ))}
                                      </div>
                                    ) : null}
                                  </div>
                                ) : messageType === 'attachment' && attachmentUrl ? (
                                  <div className="space-y-2">
                                    {isImageAttachment(attachment) ? (
                                      <a href={attachmentUrl} target="_blank" rel="noopener noreferrer">
                                        <img
                                          src={attachmentUrl}
                                          alt={attachment?.fileName || 'Attachment'}
                                          className="max-h-72 rounded-md object-contain"
                                          loading="lazy"
                                        />
                                      </a>
                                    ) : isVideoAttachment(attachment) ? (
                                      <video
                                        src={attachmentUrl}
                                        controls
                                        preload="metadata"
                                        className="max-h-72 w-full rounded-md"
                                      />
                                    ) : (
                                      <a
                                        href={attachmentUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-xs underline underline-offset-2"
                                      >
                                        {attachment?.fileName || 'Open attachment'}
                                      </a>
                                    )}
                                    {text ? (
                                      <div className="whitespace-pre-wrap break-words">{text}</div>
                                    ) : null}
                                  </div>
                                ) : (
                                  <div className="whitespace-pre-wrap break-words">{title || text || '—'}</div>
                                )}
                              </div>
                              {timeOnly ? (
                                <span className="shrink-0 self-end text-[10px] tabular-nums opacity-75">
                                  {timeOnly}
                                </span>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>
        </ScrollArea>
      </div>

      <div className="border-t border-[#e5e7eb] bg-[#fafafa] p-4">
        {canPost && selectedContactId && !unavailable ? (
          <div className="flex gap-2">
            <Textarea
              placeholder="Write a message…"
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void handleSend();
                }
              }}
              rows={3}
              className="resize-none flex-1 min-w-0 border-[#e5e7eb] bg-white"
            />
            <Button
              type="button"
              size="icon"
              className="size-11 shrink-0 bg-[#e7000b] hover:bg-[#c40009]"
              disabled={!replyText.trim() || replyMutation.isPending}
              onClick={() => void handleSend()}
              aria-label="Send"
            >
              <Send className="size-4 text-white" />
            </Button>
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">
            {!canPost
              ? "You can't send messages on this lead."
              : !selectedContactId
                ? 'Choose a contact to reply.'
                : unavailable
                  ? 'Sending is unavailable for this contact.'
                  : null}
          </p>
        )}
      </div>
    </div>
  );
}
